"""Administration commands:  python backend/manage.py status | migrate | create-admin --username U --name "Full Name\""""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zeka.core import config, migrate  # noqa: E402
from zeka.legacy import store  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Zəka: administration commands")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="applied and pending schema migrations")
    sub.add_parser("migrate", help="apply pending schema migrations (a copy of the database is saved first)")
    ca = sub.add_parser("create-admin", help="prod: create an administrator account (sign-in arrives with Task 10)")
    ca.add_argument("--username", required=True)
    ca.add_argument("--name", required=True, help="full name")
    args = ap.parse_args(argv)
    if args.cmd == "create-admin":
        return create_admin(args.username, args.name)
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
        uid = c.execute("INSERT INTO users(username,full_name,role,title,color,synthetic) VALUES(?,?,'admin','Administrator','#1a2355',0)",
                        (username, name)).lastrowid
        store.audit(c, None, "create_admin", "user", username)
        c.commit()
    finally:
        c.close()
    print(f"created administrator {username} (id {uid})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
