"""Backup and restore (tasks/todo.md, Task 8): encrypted sets, a second host, retention, restore checks.

The tests back up a copy of the seeded demo database plus a few uploads into temporary directories; the second host is
either a directory or ``host:/path`` over a fake ``ssh`` that runs the command here.
"""
import errno
import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from zeka.core import backup

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not shutil.which("openssl"), reason="the backup encrypts with the openssl command")
POSIX = pytest.mark.skipif(os.name != "posix", reason="shell scripts, file modes and the fake ssh need a POSIX system")


@pytest.fixture
def key(tmp_path):
    k = tmp_path / "backup.key"
    k.write_text(secrets.token_urlsafe(48) + "\n")
    k.chmod(0o600)
    return k


@pytest.fixture
def data(tmp_path, db):
    """A data directory: a copy of the freshly seeded demo database and three uploads."""
    d = tmp_path / "data"
    (d / "uploads").mkdir(parents=True)
    out = sqlite3.connect(d / "campus.db")
    db.backup(out)
    out.close()
    for body in (b"syllabus.pdf bytes", b"arayis.docx bytes", os.urandom(50_000)):
        (d / "uploads" / f"{hashlib.sha256(body).hexdigest()}.bin").write_bytes(body)
    return d


@pytest.fixture
def ticking(monkeypatch):
    """clock.local() one day later on every call: each backup gets its own name, retention sees whole days."""
    t = [datetime(2026, 9, 1, 3, 0, 0)]

    def local():
        t[0] += timedelta(days=1)
        return t[0]

    monkeypatch.setattr(backup.clock, "local", local)
    return t


def make(data, dest, key):
    return backup.create(data / "campus.db", data / "uploads", dest, key)


def hashes(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.bin")}


def test_a_restore_into_a_clean_directory_has_the_same_rows_and_uploads(data, key, tmp_path):
    m = make(data, tmp_path / "backups", key)
    out = tmp_path / "restored"
    r = backup.restore(tmp_path / "backups" / m["db"], out, key)
    assert backup.table_counts(out / "campus.db") == backup.table_counts(data / "campus.db") == m["tables"]
    assert hashes(out / "uploads") == hashes(data / "uploads") and len(hashes(data / "uploads")) == 3
    assert r["uploads"] == 3 and r["rows"] > 1000 and m["tables"]["users"] > 100
    assert sorted(p.name for p in out.iterdir()) == ["campus.db", "uploads"]        # no -wal/-shm left behind
    if os.name == "posix":
        assert out.stat().st_mode & 0o777 == 0o700


def test_the_backup_files_hold_no_plaintext(data, key, tmp_path):
    make(data, tmp_path / "backups", key)
    for p in (tmp_path / "backups").rglob("*.enc"):
        raw = p.read_bytes()
        assert raw.startswith(b"Salted__") and b"syllabus.pdf bytes" not in raw and b"SQLite format 3" not in raw


@pytest.mark.parametrize("problem", ["missing", "empty", "short", "readable"])
def test_without_a_usable_key_the_backup_fails_and_writes_nothing(data, key, tmp_path, problem):
    if problem == "missing":
        key = tmp_path / "no-such-key"
    elif problem == "empty":
        key.write_text("")
    elif problem == "short":
        key.write_text("password123\n")
    elif os.name == "posix":
        key.chmod(0o644)
    else:
        pytest.skip("file modes are POSIX")
    with pytest.raises(backup.BackupError):
        make(data, tmp_path / "backups", key)
    assert not (tmp_path / "backups").exists()


def test_a_failure_while_encrypting_leaves_no_plaintext_behind(data, key, tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "CIPHER", ["-no-such-cipher"])
    with pytest.raises(backup.BackupError):
        make(data, tmp_path / "backups", key)
    left = [p for p in (tmp_path / "backups").rglob("*") if p.is_file()]
    assert left == [], left


def test_openssl_gone_on_windows_is_a_backup_error_too(data, key, tmp_path, monkeypatch):
    """Windows reports a write to a pipe whose reader exited as OSError EINVAL, not BrokenPipeError (CI, windows-latest)."""
    class WindowsPipe(io.BytesIO):
        def write(self, b):
            raise OSError(errno.EINVAL, "Invalid argument")

    monkeypatch.setattr(backup, "CIPHER", ["-no-such-cipher"])
    monkeypatch.setattr(backup.gzip, "GzipFile", lambda fileobj, **kw: WindowsPipe())
    with pytest.raises(backup.BackupError):
        make(data, tmp_path / "backups", key)
    assert [p for p in (tmp_path / "backups").rglob("*") if p.is_file()] == []


def test_a_backup_under_a_commit_every_20_ms_is_not_restarted(data, key, tmp_path, ticking):
    c = sqlite3.connect(data / "campus.db")
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE bench(id INTEGER PRIMARY KEY, blob BLOB)")
    c.executemany("INSERT INTO bench(blob) VALUES(randomblob(8192))", [()] * 2000)        # about 16 MB more
    c.commit()
    c.close()
    t = time.perf_counter()
    make(data, tmp_path / "idle", key)
    idle = time.perf_counter() - t
    stop, commits = threading.Event(), [0]

    def writer():
        w = sqlite3.connect(data / "campus.db", timeout=15)
        while not stop.is_set():
            w.execute("INSERT INTO bench(blob) VALUES(randomblob(64))")
            w.commit()
            commits[0] += 1
            time.sleep(0.02)
        w.close()

    th = threading.Thread(target=writer)
    th.start()
    try:
        t = time.perf_counter()
        m = make(data, tmp_path / "busy", key)
        busy = time.perf_counter() - t
    finally:
        stop.set()
        th.join()
    assert commits[0] >= 3, "the writer really committed while the backup ran"
    assert busy < 3 * idle, (busy, idle)
    backup.restore(tmp_path / "busy" / m["db"], tmp_path / "restored", key)          # integrity_check inside


def test_a_changed_manifest_a_changed_set_or_another_key_is_refused(data, key, tmp_path):
    m = make(data, tmp_path / "backups", key)
    enc, man = tmp_path / "backups" / m["db"], tmp_path / "backups" / m["db"].replace(".enc", ".json")
    other = tmp_path / "other.key"
    other.write_text(secrets.token_urlsafe(48))
    other.chmod(0o600)
    with pytest.raises(backup.BackupError, match="changed or belongs to another key"):
        backup.restore(enc, tmp_path / "r1", other)
    doc = json.loads(man.read_text())
    doc["tables"]["users"] += 1
    man.write_text(json.dumps(doc))
    with pytest.raises(backup.BackupError, match="changed"):
        backup.restore(enc, tmp_path / "r2", key)
    man.write_text(json.dumps({**doc, "tables": m["tables"]}))
    raw = bytearray(enc.read_bytes())
    raw[-40] ^= 0xFF
    enc.write_bytes(bytes(raw))
    with pytest.raises(backup.BackupError, match="does not match its manifest"):
        backup.restore(enc, tmp_path / "r3", key)
    for d in ("r1", "r2", "r3"):
        assert not (tmp_path / d / "campus.db").exists()


def test_a_restore_never_writes_into_a_directory_that_has_files(data, key, tmp_path):
    m = make(data, tmp_path / "backups", key)
    live = tmp_path / "live"
    live.mkdir()
    (live / "campus.db").write_bytes(b"the running database")
    with pytest.raises(backup.BackupError, match="not empty"):
        backup.restore(tmp_path / "backups" / m["db"], live, key)
    assert (live / "campus.db").read_bytes() == b"the running database"


def test_the_second_host_mirrors_the_kept_sets_and_a_bad_copy_is_sent_again(data, key, tmp_path, ticking, monkeypatch):
    dest, remote = tmp_path / "backups", tmp_path / "second-host"
    (remote / "uploads").mkdir(parents=True)                    # made once on the mounted disk
    for _ in range(12):                                         # 12 days: retention drops the oldest
        make(data, dest, key)
        backup.send(dest, str(remote))
    local = sorted(p.name for p in dest.glob("zeka-*"))
    assert sorted(p.name for p in remote.glob("zeka-*")) == local and len(local) < 24
    assert sorted(p.name for p in remote.glob("uploads/*.enc")) == sorted(p.name for p in dest.glob("uploads/*.enc"))
    newest = sorted(dest.glob("zeka-*.enc"))[-1]
    backup.restore(remote / newest.name, tmp_path / "from-second-host", key)
    real = shutil.copyfile

    def damaged(src, dst):
        real(src, dst)
        with open(dst, "r+b") as f:
            f.seek(20)
            f.write(b"\0")

    monkeypatch.setattr(backup.shutil, "copyfile", damaged)
    m = make(data, dest, key)
    with pytest.raises(backup.BackupError, match="does not match"):
        backup.send(dest, str(remote))
    assert not (remote / m["db"]).exists(), "a file gets its final name only after its hash matched"
    monkeypatch.setattr(backup.shutil, "copyfile", real)
    assert backup.send(dest, str(remote))["sent"] == 2                  # the next night sends it again
    backup.restore(remote / m["db"], tmp_path / "repaired", key)


def test_an_unmounted_second_disk_fails_instead_of_filling_the_same_disk(data, key, tmp_path):
    make(data, tmp_path / "backups", key)
    with pytest.raises(backup.BackupError, match="mounted"):
        backup.send(tmp_path / "backups", str(tmp_path / "mnt" / "backup"))
    assert not (tmp_path / "mnt").exists()


def test_losing_the_local_backups_never_wipes_the_history_on_the_second_host(data, key, tmp_path, ticking):
    dest, remote = tmp_path / "backups", tmp_path / "second-host"
    (remote / "uploads").mkdir(parents=True)
    for _ in range(5):
        make(data, dest, key)
        backup.send(dest, str(remote))
    history = sorted(p.name for p in remote.glob("zeka-*"))
    uploads = sorted(p.name for p in remote.glob("uploads/*.enc"))
    shutil.rmtree(dest)                                          # the primary's backup volume is lost
    make(data, dest, key)
    backup.send(dest, str(remote))
    assert set(history) <= {p.name for p in remote.glob("zeka-*")}
    assert sorted(p.name for p in remote.glob("uploads/*.enc")) == uploads
    backup.restore(remote / history[0], tmp_path / "oldest", key)


def test_a_damaged_upload_is_reported_and_left_out_of_the_set(data, key, tmp_path):
    bad = data / "uploads" / f"{'0' * 64}.bin"
    bad.write_bytes(b"half written")
    m = make(data, tmp_path / "backups", key)
    assert m["damaged"] == ["0" * 64] and "0" * 64 not in m["uploads"] and len(m["uploads"]) == 3
    backup.restore(tmp_path / "backups" / m["db"], tmp_path / "restored", key)


def test_a_broken_manifest_is_a_backup_error(data, key, tmp_path, ticking):
    m = make(data, tmp_path / "backups", key)
    (tmp_path / "backups" / m["db"].replace(".enc", ".json")).write_text("{not json")
    with pytest.raises(backup.BackupError, match="cannot be read"):
        make(data, tmp_path / "backups", key)


@POSIX
@pytest.mark.skipif(not shutil.which("sha256sum"), reason="the second host checks with sha256sum")
def test_over_ssh_the_files_arrive_and_are_checked_there(data, key, tmp_path, ticking, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "ssh"
    fake.write_text('#!/bin/sh\n# fake ssh: drop the options and the host, run the command on this machine\n'
                    'while [ "$1" = "-o" ]; do shift 2; done\nshift\n[ -n "$FAIL_SSH" ] && exit 255\n'
                    'if [ -n "$CUT_SSH" ]; then case "$1" in *"tar -C"*) head -c 3000 | sh -c "$1"; exit $?;; esac; fi\n'
                    'exec sh -c "$1"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    dest, remote = tmp_path / "backups", tmp_path / "over ssh"            # a space: the remote path is quoted
    for _ in range(9):
        make(data, dest, key)
        r = backup.send(dest, f"backup@vault.example.az:{remote}")
    assert r["sent"] == 2                                                   # the new set only: uploads are already there
    assert sorted(p.name for p in remote.glob("zeka-*")) == sorted(p.name for p in dest.glob("zeka-*"))
    (remote / sorted(dest.glob("zeka-*.json"))[0].name).unlink()           # a lost file is sent again
    make(data, dest, key)
    assert backup.send(dest, f"backup@vault.example.az:{remote}")["sent"] >= 3
    m = make(data, dest, key)
    monkeypatch.setenv("CUT_SSH", "1")                                     # the connection drops in the middle
    with pytest.raises(backup.BackupError, match="failed"):
        backup.send(dest, f"backup@vault.example.az:{remote}")
    assert not (remote / m["db"]).exists()
    monkeypatch.delenv("CUT_SSH")
    assert backup.send(dest, f"backup@vault.example.az:{remote}")["sent"] == 2
    backup.restore(remote / m["db"], tmp_path / "over-ssh", key)
    monkeypatch.setenv("FAIL_SSH", "1")
    with pytest.raises(backup.BackupError, match="ssh backup@vault.example.az failed"):
        backup.send(dest, f"backup@vault.example.az:{remote}")


def test_retention_keeps_seven_days_and_four_weeks():
    start = datetime(2026, 1, 1, 2, 0)
    stamps = [start + timedelta(days=d, hours=h) for d in range(60) for h in (0, 12)]    # two sets a day for 60 days
    kept = backup.keep(stamps)
    last = max(stamps)
    days = sorted({s.date() for s in kept})
    assert all(s.hour == 14 for s in kept), "the newest set of a day is kept"
    assert days[-7:] == [last.date() - timedelta(days=i) for i in range(6, -1, -1)]
    assert len({s.isocalendar()[:2] for s in kept}) == 4 and len(kept) <= 11
    assert backup.keep([]) == set()


@POSIX
def test_the_scripts_back_up_and_restore_and_prod_needs_a_second_host(data, key, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ZEKA_", "BACKUP_"))}
    env.update(ZEKA_DATA=str(data), BACKUP_DIR=str(tmp_path / "backups"), BACKUP_KEY_FILE=str(key), PYTHON=sys.executable,
               PYTHONIOENCODING="utf-8")
    run = subprocess.run(["bash", str(ROOT / "infra" / "backup.sh")], env=env, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr
    run = subprocess.run(["bash", str(ROOT / "infra" / "restore.sh"), "backups/latest.enc", str(tmp_path / "restored")],
                         env=env, capture_output=True, text=True, timeout=120, cwd=tmp_path)
    assert run.returncode == 0 and "integrity_check ok" in run.stdout, run.stderr
    assert hashes(tmp_path / "restored" / "uploads") == hashes(data / "uploads")
    time.sleep(1.1)                                              # a set is named by the second
    prod = subprocess.run(["bash", str(ROOT / "infra" / "backup.sh")], env={**env, "ZEKA_MODE": "prod"},
                          capture_output=True, text=True, timeout=120)
    assert prod.returncode == 4 and "BACKUP_REMOTE" in prod.stderr
    time.sleep(1.1)
    bad = subprocess.run(["bash", str(ROOT / "infra" / "backup.sh")], env={**env, "BACKUP_REMOTE": "/proc/no/such/host"},
                         capture_output=True, text=True, timeout=120)
    assert bad.returncode == 3, bad.stderr
