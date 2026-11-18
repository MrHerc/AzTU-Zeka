"""Administration commands:  python backend/manage.py status | migrate | create-admin | backup | restore | import |
activation-codes  (--help for each)"""
import argparse
import os
import re
import sqlite3
import subprocess  # nosec B404 - only to catch the timeout of the ssh transfer
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zeka.core import backup, config, migrate  # noqa: E402
from zeka.legacy import store  # noqa: E402
from zeka.modules.identity import domain as identity  # noqa: E402
from zeka.modules.integration import domain as integration_rules, importer, tables  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Zəka: administration commands")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="applied and pending schema migrations")
    sub.add_parser("migrate", help="apply pending schema migrations (a copy of the database is saved first)")
    ca = sub.add_parser("create-admin", help="prod: create an administrator account (sign-in arrives with Task 10)")
    ca.add_argument("--username", required=True)
    ca.add_argument("--name", required=True, help="full name")
    bk = sub.add_parser("backup", help="encrypted backup of the database and uploads, sent to BACKUP_REMOTE (infra/backup.sh)")
    bk.add_argument("--dest", default=os.environ.get("BACKUP_DIR") or str(store.ROOT / "backups"), help="local backup directory")
    bk.add_argument("--key-file", default=os.environ.get("BACKUP_KEY_FILE", ""), help="file with one random line (BACKUP_KEY_FILE)")
    bk.add_argument("--remote", default=os.environ.get("BACKUP_REMOTE", ""), help="second host: user@host:/path or a mounted path")
    rs = sub.add_parser("restore", help="check a backup set and restore it into a new directory (infra/restore.sh)")
    rs.add_argument("set", help="zeka-YYYYMMDD-HHMMSS.enc or latest.enc")
    rs.add_argument("--to", required=True, help="new or empty directory: campus.db and uploads/ are written there")
    rs.add_argument("--key-file", default=os.environ.get("BACKUP_KEY_FILE", ""))
    im = sub.add_parser("import", help="bulk import of one CSV/XLSX file, all or nothing (Task 16)")
    im.add_argument("--kind", required=True, choices=integration_rules.KINDS)
    im.add_argument("--source", required=True, help="name of the source system, e.g. old-sis")
    im.add_argument("--file", required=True)
    im.add_argument("--dry-run", action="store_true", help="check and compare only: nothing is written")
    im.add_argument("--prefer", choices=("zeka", "source"), default="zeka",
                    help="source: overwrite rows changed in Zəka since the last import (audited)")
    ac = sub.add_parser("activation-codes", help="one-time activation codes for a faculty's students, as CSV (Task 16)")
    ac.add_argument("--faculty", required=True, help="faculty code")
    ac.add_argument("--out", required=True, help="CSV file to write (handed to the dean's office)")
    args = ap.parse_args(argv)
    if args.cmd == "import":
        return run_import(args.kind, args.source, Path(args.file), args.dry_run, args.prefer == "source")
    if args.cmd == "activation-codes":
        return run_activation_codes(args.faculty, Path(args.out))
    if args.cmd == "create-admin":
        return create_admin(args.username, args.name)
    if args.cmd == "backup":
        return run_backup(Path(args.dest), args.key_file, args.remote)
    if args.cmd == "restore":
        return run_restore(Path(args.set), Path(args.to), args.key_file)
    c = store.connect()
    try:
        if args.cmd == "status":
            s = migrate.status(c)
            print(f"database: {store.DB_PATH}")
            print("applied: " + (", ".join(f"{v:04d}" for v in s["applied"]) or "-"))
            print("pending: " + (", ".join(f"{v:04d}" for v in s["pending"]) or "-"))
        else:
            done = migrate.apply(c, backup_dir=store.DATA / "backups")
            print("applied: " + (", ".join(f"{v:04d}" for v in done) or "nothing to do"))
    except migrate.MigrationError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    finally:
        c.close()
    return 0


def run_backup(dest: Path, key_file: str, remote: str) -> int:
    try:
        m = backup.create(store.DB_PATH, store.UPLOADS, dest, key_file)
    except (backup.BackupError, sqlite3.Error, OSError) as ex:
        print(f"error: backup failed: {ex}", file=sys.stderr)
        return 2
    print(f"backup: {dest / m['db']}: {len(m['tables'])} tables, {sum(m['tables'].values())} rows, {len(m['uploads'])} uploads")
    if not remote:
        if config.prod():
            print("error: BACKUP_REMOTE is empty: in prod every backup must also be on a second host", file=sys.stderr)
            return 4
        print("BACKUP_REMOTE is not set: the backup stays on this host only")
        return _damaged(m)
    try:
        r = backup.send(dest, remote)
    except (backup.BackupError, OSError, subprocess.TimeoutExpired) as ex:
        print(f"error: sending to the second host failed: {ex}", file=sys.stderr)
        return 3
    print(f"second host: {r['sent']} file(s) sent and their SHA-256 checked there, {r['removed']} old file(s) removed")
    return _damaged(m)


def _damaged(m: dict) -> int:
    if not m.get("damaged"):
        return 0
    print(f"warning: {len(m['damaged'])} upload(s) in the data directory do not match their SHA-256 and were not backed up: "
          + ", ".join(m["damaged"][:5]), file=sys.stderr)
    return 5


def run_restore(enc: Path, target: Path, key_file: str) -> int:
    try:
        r = backup.restore(enc, target, key_file)
    except (backup.BackupError, sqlite3.Error, OSError) as ex:
        print(f"error: restore failed: {ex}", file=sys.stderr)
        return 2
    print(f"restored into {target}: {r['tables']} tables, {r['rows']} rows, {r['uploads']} uploads; integrity_check ok, "
          "row counts match the manifest")
    return 0


def create_admin(username: str, name: str) -> int:
    if not config.prod():
        print("error: create-admin is for ZEKA_MODE=prod; the demo already has its accounts", file=sys.stderr)
        return 2
    username, name = username.strip().lower(), " ".join(name.split())
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,39}", username) or not 3 <= len(name) <= 120:
        print("error: username: 3-40 of a-z 0-9 . _ - ; name: 3-120 characters", file=sys.stderr)
        return 2
    try:
        store.init()                           # migrations and the product catalogue; never people in prod
    except migrate.MigrationError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    c = store.connect()
    try:
        if store.row(c, "SELECT 1 FROM users WHERE username=?", (username,)):
            print(f"error: user {username} already exists", file=sys.stderr)
            return 2
        password = identity.temporary_password()
        uid = c.execute("INSERT INTO users(username,full_name,role,title,color,synthetic,password_hash,must_change) "
                        "VALUES(?,?,'admin','Administrator','#1a2355',0,?,1)",
                        (username, name, identity.hash_password(password))).lastrowid
        store.audit(c, None, "create_admin", "user", username)
        c.commit()
    finally:
        c.close()
    print(f"created administrator {username} (id {uid})")
    print(f"temporary password (shown once, must be changed at the first sign-in): {password}")
    return 0



def _az(v) -> str:
    return v.get("az", "") if isinstance(v, dict) else str(v)          # reasons are i18n dicts


def run_import(kind: str, source: str, path: Path, dry_run: bool, prefer_source: bool) -> int:
    """Exit 0: imported (or checked); 1: refused rows, nothing written; 2: the file or the database cannot be used."""
    try:
        store.init()
    except migrate.MigrationError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    c = store.connect()
    try:
        report = importer.run(c, kind, source, path.name, path.read_bytes(), dry_run=dry_run, prefer_source=prefer_source)
    except (OSError, tables.TableError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    finally:
        c.close()
    tail = " · dry run, nothing written" if dry_run else f" · write lock {report['lock_ms']} ms" if report["written"] else ""
    print(f"{kind} from {source}: {report['rows']} rows · new {report['inserted']} · changed {report['updated']} · "
          f"unchanged {report['unchanged']} · conflicts {len(report['conflicts'])} · refused {report['error_count']} · "
          f"{report['seconds']} s{tail}")
    for e in report["errors"]:
        print(f"  row {e['row']}: {_az(e['reason'])}")
    for x in report["conflicts"][:200]:
        print(f"  conflict, row {x['row']}: {_az(x['reason'])}" + (f" ({', '.join(x['fields'])})" if x.get("fields") else ""))
    return 1 if report["error_count"] else 0


def run_activation_codes(faculty_code: str, out: Path) -> int:
    import csv
    if out.exists():
        print(f"error: {out} exists; codes are written once, to a new file", file=sys.stderr)
        return 2
    store.init()
    c = store.connect()
    try:
        f = store.row(c, "SELECT id FROM faculties WHERE code=?", (faculty_code,))
        if not f:
            print(f"error: no faculty {faculty_code}", file=sys.stderr)
            return 2
        items = importer.issue_codes(c, None, f["id"])
        with open(out, "x", newline="", encoding="utf-8") as fh:
            os.chmod(out, 0o600)
            w = csv.writer(fh)
            w.writerow(["student_no", "full_name", "group", "username", "code", "expires_at"])
            w.writerows([[x["student_no"], x["full_name"], x["group"], x["username"], x["code"], x["expires_at"]] for x in items])
        c.commit()                                     # the codes count only once the file holding them is written
    finally:
        c.close()
    print(f"{len(items)} codes written to {out}; the earlier unused codes of these students no longer work")
    return 0


if __name__ == "__main__":
    sys.exit(main())
