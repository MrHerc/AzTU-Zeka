"""Encrypted backups of the database and the uploads (tasks/todo.md, Task 8).

A backup directory holds:
    zeka-YYYYMMDD-HHMMSS.enc      the database: one consistent copy (Connection.backup in a single step), gzip, openssl
    zeka-YYYYMMDD-HHMMSS.json     manifest: SHA-256 of the .enc, row count of every table, every upload the set needs,
                                  and an HMAC over all of it made with the backup key (a changed manifest is refused)
    uploads/<sha256>.enc          each upload once (uploads are content-addressed and never change), gzip, openssl
    uploads/index.tsv             "<sha256 of the upload> <sha256 of its .enc>" for the hash check on the second host
    latest.enc                    link to the newest set

Encryption: ``openssl enc -aes-256-cbc -pbkdf2 -iter 10000 -md sha256`` with ``-pass file:KEY``. The key file holds one
random line of at least 32 characters (``openssl rand -base64 48``); a weak passphrase is refused. Plaintext never
leaves the private temporary directory, which is removed on success and on failure.

Retention: the newest set of each of the last 7 days that have a set, the newest set of each of the last 4 ISO
weeks, and the newest set of each hour of the 24 hours before the newest set (hourly backups). Uploads no kept set
needs are deleted. The second host (``BACKUP_REMOTE``) mirrors the directory: either a local path (a mounted disk of
another machine) or ``user@host:/path`` over ssh (tar stream in, ``sha256sum -c`` there).
"""
from __future__ import annotations

import errno
import gzip
import hashlib
import hmac
import io
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess  # nosec B404 - openssl and ssh with fixed argument lists, never a shell
import tarfile
import tempfile
import zlib
from datetime import datetime, timedelta
from pathlib import Path

from . import clock

KEY_MIN = 32
CIPHER = ["-aes-256-cbc", "-pbkdf2", "-iter", "10000", "-md", "sha256"]   # fixed: a set must decrypt years later
SET = re.compile(r"^zeka-(\d{8}-\d{6})\.(enc|json)$")
UPLOAD = re.compile(r"^[0-9a-f]{64}\.enc$")
CHUNK = 1 << 20


class BackupError(RuntimeError):
    """The backup or the restore cannot be trusted; the message says why."""


def read_key(key_file) -> bytes:
    if not key_file:
        raise BackupError("no key file: set BACKUP_KEY_FILE (one random line, e.g. openssl rand -base64 48)")
    try:
        key = Path(key_file).read_bytes().splitlines()[0].strip()
    except (OSError, IndexError):
        raise BackupError(f"key file {key_file} cannot be read or is empty") from None
    if os.name == "posix" and Path(key_file).stat().st_mode & 0o077:
        raise BackupError(f"key file {key_file} is readable by other users; chmod 600 it")
    if len(key) < KEY_MIN:
        raise BackupError(f"the key in {key_file} is shorter than {KEY_MIN} characters; make one with openssl rand -base64 48")
    return key


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def _sign(key: bytes, manifest: dict) -> str:
    body = json.dumps({k: v for k, v in manifest.items() if k != "hmac"}, sort_keys=True).encode()
    return hmac.new(hashlib.sha256(b"zeka-backup-manifest" + key).digest(), body, hashlib.sha256).hexdigest()


def _need(tool: str) -> None:
    if not shutil.which(tool):
        raise BackupError(f"the {tool} command is not installed")


def _pipe_gone(ex: OSError) -> bool:
    """A write to a pipe whose reader exited: BrokenPipeError on POSIX, OSError EINVAL on Windows."""
    return isinstance(ex, BrokenPipeError) or ex.errno == errno.EINVAL


def encrypt(src: Path, dst: Path, key_file) -> None:
    """gzip + openssl, streamed: no compressed plaintext is written to disk."""
    _need("openssl")
    broken = False
    with subprocess.Popen(["openssl", "enc", "-e", *CIPHER, "-pass", f"file:{key_file}", "-out", str(dst)],  # nosec B603 B607
                          stdin=subprocess.PIPE, stderr=subprocess.PIPE) as p:
        try:
            with open(src, "rb") as f:
                try:
                    with gzip.GzipFile(fileobj=p.stdin, mode="wb", mtime=0) as z:
                        shutil.copyfileobj(f, z, CHUNK)
                except OSError as ex:
                    if not _pipe_gone(ex):
                        raise
                    broken = True                          # openssl stopped reading: its message follows
                finally:
                    try:
                        p.stdin.close()                    # type: ignore[union-attr]
                    except OSError as ex:
                        if not _pipe_gone(ex):
                            raise
            err = p.stderr.read()                          # type: ignore[union-attr]
            p.wait()
        except BaseException:
            p.kill()
            p.wait()
            dst.unlink(missing_ok=True)                    # never leave a truncated set behind
            raise
    if p.returncode or broken:
        dst.unlink(missing_ok=True)
        raise BackupError(f"openssl failed on {src.name}: {err.decode(errors='replace').strip()}")


def decrypt(src: Path, dst: Path, key_file) -> None:
    _need("openssl")
    with subprocess.Popen(["openssl", "enc", "-d", *CIPHER, "-pass", f"file:{key_file}", "-in", str(src)],  # nosec B603 B607
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
        try:
            with open(dst, "wb") as out, gzip.GzipFile(fileobj=p.stdout, mode="rb") as z:
                shutil.copyfileobj(z, out, CHUNK)
        except (OSError, EOFError, zlib.error) as ex:
            p.kill()
            p.wait()
            dst.unlink(missing_ok=True)
            raise BackupError(f"{src.name} does not decrypt with this key or is damaged ({ex})") from None
        err = p.stderr.read()                              # type: ignore[union-attr]
        p.wait()
    if p.returncode:
        dst.unlink(missing_ok=True)
        raise BackupError(f"{src.name} does not decrypt with this key: {err.decode(errors='replace').strip()}")


def snapshot(db_path: Path, dst: Path) -> None:
    """One consistent copy in a single step: a stepwise copy restarts on every commit of another connection."""
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=15)
    out = sqlite3.connect(dst)
    try:
        src.backup(out)                                     # pages=-1: everything in one step, under one read transaction
    finally:
        out.close()
        src.close()


def table_counts(db: Path) -> dict[str, int]:
    c = sqlite3.connect(db)            # read-write: the last connection to close removes the -wal and -shm files
    try:
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {n: c.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}  # nosec B608 - names from sqlite_master
    finally:
        c.close()


def keep(stamps: list[datetime], daily: int = 7, weekly: int = 4, hourly: int = 24) -> set[datetime]:
    """The newest set of each of the last ``daily`` days and of each of the last ``weekly`` ISO weeks that have a set,
    and the newest of each clock hour within ``hourly`` hours of the newest set (hourly backups: RPO one hour)."""
    out: set[datetime] = set()
    days: set = set()
    weeks: set = set()
    hours: set = set()
    newest = max(stamps, default=None)
    for s in sorted(stamps, reverse=True):
        hour = s.replace(minute=0, second=0, microsecond=0)
        if newest and newest - s < timedelta(hours=hourly) and hour not in hours:
            hours.add(hour)
            out.add(s)
        if s.date() not in days and len(days) < daily:
            days.add(s.date())
            out.add(s)
        week = s.isocalendar()[:2]
        if week not in weeks and len(weeks) < weekly:
            weeks.add(week)
            out.add(s)
    return out


def _index(dest: Path) -> dict[str, str]:
    path = dest / "uploads" / "index.tsv"
    if not path.exists():
        return {}
    return dict(line.split() for line in path.read_text(encoding="ascii").splitlines() if line.strip())


def _write_index(dest: Path, index: dict[str, str]) -> None:
    tmp = dest / "uploads" / "index.tsv.tmp"
    tmp.write_text("".join(f"{k} {v}\n" for k, v in sorted(index.items())), encoding="ascii")
    tmp.replace(dest / "uploads" / "index.tsv")


def _manifest(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["db_sha256"], doc["uploads"]                    # noqa: B018  both keys must be there
    except (OSError, ValueError, KeyError, TypeError) as ex:
        raise BackupError(f"{path.name} cannot be read: {ex}") from None
    return doc


def sets(dest: Path) -> dict[datetime, str]:
    """{time: name without extension} of every complete set (its manifest exists)."""
    out = {}
    for p in dest.glob("zeka-*.json"):
        m = SET.match(p.name)
        if m and (dest / f"zeka-{m.group(1)}.enc").exists():
            out[datetime.strptime(m.group(1), "%Y%m%d-%H%M%S")] = p.stem
    return out


def create(db_path: Path, uploads: Path, dest: Path, key_file) -> dict:
    """Write one set into ``dest`` and prune it; returns the manifest."""
    key = read_key(key_file)                                # before anything is written
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "uploads").mkdir(exist_ok=True)
    stamp = f"{clock.local():%Y%m%d-%H%M%S}"
    name = f"zeka-{stamp}"
    if (dest / f"{name}.json").exists():
        raise BackupError(f"{name} already exists; run the backup again in a second")
    work = Path(tempfile.mkdtemp(prefix=".tmp-", dir=dest))   # 0700: the plaintext copy is readable by this user only
    try:
        plain = work / "campus.db"
        snapshot(db_path, plain)
        counts = table_counts(plain)
        encrypt(plain, work / f"{name}.enc", key_file)
        plain.unlink()
        index = _index(dest)
        found = sorted(p.name[:-4] for p in uploads.glob("*.bin") if re.fullmatch(r"[0-9a-f]{64}", p.name[:-4])) if uploads.exists() else []
        needed, damaged = [], []
        for digest in found:
            if digest in index and (dest / "uploads" / f"{digest}.enc").exists():
                needed.append(digest)
                continue
            if sha256(uploads / f"{digest}.bin") != digest:    # a half-written or damaged upload would break every restore
                damaged.append(digest)
                continue
            enc = work / f"{digest}.enc"
            encrypt(uploads / f"{digest}.bin", enc, key_file)
            index[digest] = sha256(enc)
            enc.replace(dest / "uploads" / f"{digest}.enc")
            needed.append(digest)
        _write_index(dest, index)
        manifest = {"format": 1, "created_at": clock.local().isoformat(timespec="seconds"), "db": f"{name}.enc",
                    "db_sha256": sha256(work / f"{name}.enc"), "tables": counts, "uploads": needed, "damaged": damaged}
        manifest["hmac"] = _sign(key, manifest)
        (work / f"{name}.json").write_text(json.dumps(manifest, indent=1, sort_keys=True), encoding="utf-8")
        (work / f"{name}.enc").replace(dest / f"{name}.enc")
        (work / f"{name}.json").replace(dest / f"{name}.json")    # last and atomic: a set exists once its manifest does
    finally:
        shutil.rmtree(work, ignore_errors=True)
    latest = dest / "latest.enc"
    latest.unlink(missing_ok=True)
    try:
        latest.symlink_to(f"{name}.enc")
    except OSError:                                         # no symlinks (Windows without the privilege): name the set
        pass
    prune(dest)
    return manifest


def prune(dest: Path) -> list[str]:
    """Delete the sets retention does not keep and the uploads no kept set needs; returns the deleted names."""
    all_sets = sets(dest)
    kept = keep(list(all_sets))
    gone, needed = [], set()
    for when, name in all_sets.items():
        if when in kept:
            needed.update(_manifest(dest / f"{name}.json")["uploads"])
            continue
        for ext in ("json", "enc"):
            (dest / f"{name}.{ext}").unlink(missing_ok=True)
            gone.append(f"{name}.{ext}")
    index = _index(dest)
    for p in (dest / "uploads").glob("*.enc"):
        if p.name[:-4] not in needed:
            p.unlink()
            index.pop(p.name[:-4], None)
            gone.append(f"uploads/{p.name}")
    _write_index(dest, index)
    return gone


def _files(dest: Path) -> dict[str, str]:
    """{relative path: sha256} the second host must hold: every kept set and every upload."""
    out = {}
    for name in sets(dest).values():
        out[f"{name}.json"] = sha256(dest / f"{name}.json")
        out[f"{name}.enc"] = _manifest(dest / f"{name}.json")["db_sha256"]
    for digest, enc in _index(dest).items():
        out[f"uploads/{digest}.enc"] = enc
    return out


def _allowed(rel: str) -> bool:
    head, _, tail = rel.rpartition("/")
    return (head == "" and bool(SET.match(tail))) or (head == "uploads" and bool(UPLOAD.match(tail)))


def _removals(have: set[str], files: dict[str, str]) -> list[str]:
    """Names to delete on the second host. Retention runs over the sets of both sides, so a lost or new local directory
    never wipes the history there; uploads are pruned only when every set kept there is also known here."""
    def stamp(rel: str) -> datetime:
        return datetime.strptime(SET.match(rel).group(1), "%Y%m%d-%H%M%S")  # type: ignore[union-attr]

    remote = {stamp(r) for r in have if "/" not in r}
    local = {stamp(r) for r in files if "/" not in r}
    kept = keep(list(remote | local))
    out = [r for r in have if "/" not in r and stamp(r) not in kept]
    if remote & kept <= local:
        out += [r for r in have if r.startswith("uploads/") and r not in files]
    return sorted(out)


def send(dest: Path, remote: str) -> dict:
    """Mirror ``dest`` to the second host. A file gets its final name there only after its SHA-256 matched, so a cut or
    damaged transfer is sent again on the next run."""
    files = _files(dest)
    m = re.match(r"^([^/:]+):(.+)$", remote)
    if m and not re.match(r"^[A-Za-z]:[\\/]", remote):
        return _send_ssh(dest, m.group(1), m.group(2), files)
    root = Path(remote)
    if not (root / "uploads").is_dir():        # never create it: an unmounted disk would quietly become a local copy
        raise BackupError(f"{root / 'uploads'} does not exist: is the second disk mounted? Create the folder once on it")
    have = {f"{d}{p.name}" for d, base in (("", root), ("uploads/", root / "uploads")) for p in base.iterdir()
            if p.is_file() and _allowed(f"{d}{p.name}")}
    sent = sorted(rel for rel in files if rel not in have)
    for rel in sent:
        tmp = root / f"{rel}.part"
        shutil.copyfile(dest / rel, tmp)
        if sha256(tmp) != files[rel]:
            tmp.unlink()
            raise BackupError(f"the copy of {rel} on the second host does not match")
        tmp.replace(root / rel)
    removed = _removals(have, files)
    for rel in removed:
        (root / rel).unlink()
    return {"sent": len(sent), "removed": len(removed)}


def _ssh(host: str, command: str, stdin=None) -> bytes:
    _need("ssh")
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", host, command], stdin=stdin or subprocess.DEVNULL,  # nosec B603 B607
                           capture_output=True, timeout=3600)
    except subprocess.TimeoutExpired:
        raise BackupError(f"ssh {host}: no answer within an hour") from None
    if r.returncode:
        raise BackupError(f"ssh {host} failed ({r.returncode}): {r.stderr.decode(errors='replace').strip()[-400:]}")
    return r.stdout


def _send_ssh(dest: Path, host: str, path: str, files: dict[str, str]) -> dict:
    q = shlex.quote(path)
    listing = _ssh(host, f"mkdir -p {q}/uploads && cd {q} && ls -1 && ls -1 uploads | sed 's|^|uploads/|'").decode()
    have = {line.strip() for line in listing.splitlines() if _allowed(line.strip())}
    sent = sorted(rel for rel in files if rel not in have)
    if sent:
        sums = "".join(f"{files[rel]}  {rel}\n" for rel in sent).encode()
        with tempfile.TemporaryFile(dir=dest) as buf:          # on disk, not in memory: the first run sends every upload
            with tarfile.open(fileobj=buf, mode="w") as tar:
                for rel in sent:
                    tar.add(dest / rel, arcname=rel)
                info = tarfile.TarInfo(".sha256")
                info.size = len(sums)
                tar.addfile(info, io.BytesIO(sums))
            buf.seek(0)
            # unpacked into .incoming, checked there, then moved into place: a cut transfer leaves no file with a final name
            _ssh(host, f"cd {q} && rm -rf .incoming && mkdir .incoming && tar -C .incoming -xf - && cd .incoming && "
                       "sha256sum -c --quiet --strict .sha256 && "
                       'for f in $(cut -c67- .sha256); do mv -f -- "$f" "../$f" || exit 1; done && cd .. && rm -rf .incoming',
                 stdin=buf)
    removed = _removals(have, files)                        # every name passed _allowed(): safe inside the command
    if removed:
        _ssh(host, f"cd {q} && rm -f -- " + " ".join(removed))
    return {"sent": len(sent), "removed": len(removed)}


def restore(enc: Path, target: Path, key_file) -> dict:
    """Check the manifest, restore into an empty ``target`` (database + uploads), run integrity_check, compare counts."""
    key = read_key(key_file)
    enc = enc.resolve()
    m = SET.match(enc.name)
    if not m:
        raise BackupError(f"{enc.name}: not a backup set (zeka-YYYYMMDD-HHMMSS.enc)")
    manifest_path = enc.with_suffix(".json")
    manifest = _manifest(manifest_path)
    if not hmac.compare_digest(str(manifest.get("hmac", "")), _sign(key, manifest)):
        raise BackupError(f"{manifest_path.name} was changed or belongs to another key")
    if sha256(enc) != manifest["db_sha256"]:
        raise BackupError(f"{enc.name} does not match its manifest")
    if target.exists() and any(target.iterdir()):
        raise BackupError(f"{target} is not empty: restore into a new directory, then move it into place")
    try:
        return _restore_into(enc, manifest, target, key_file)
    except BaseException:
        (target / "campus.db").unlink(missing_ok=True)     # a failed restore leaves nothing that looks usable
        shutil.rmtree(target / "uploads", ignore_errors=True)
        raise


def _restore_into(enc: Path, manifest: dict, target: Path, key_file) -> dict:
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(target, 0o700)                                 # before any plaintext is written into it
    (target / "uploads").mkdir(exist_ok=True)
    db = target / "campus.db"
    decrypt(enc, db, key_file)
    c = sqlite3.connect(db)
    try:
        check = c.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        c.close()
    if check != "ok":
        raise BackupError(f"integrity_check: {check}")
    counts = table_counts(db)
    if counts != manifest["tables"]:
        diff = {t: (counts.get(t), n) for t, n in manifest["tables"].items() if counts.get(t) != n}
        raise BackupError(f"row counts differ from the manifest: {diff}")
    for digest in manifest["uploads"]:
        out = target / "uploads" / f"{digest}.bin"
        src = enc.parent / "uploads" / f"{digest}.enc"
        if not src.exists():
            raise BackupError(f"upload {digest} is missing from {src.parent}")
        decrypt(src, out, key_file)
        if sha256(out) != digest:
            raise BackupError(f"upload {digest} is damaged")
    return {"tables": len(counts), "rows": sum(counts.values()), "uploads": len(manifest["uploads"])}
