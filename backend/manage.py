"""Administration commands:  python backend/manage.py status | migrate"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zeka.core import migrate  # noqa: E402
from zeka.legacy import store  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Zəka: administration commands")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="applied and pending schema migrations")
    sub.add_parser("migrate", help="apply pending schema migrations (a copy of the database is saved first)")
    args = ap.parse_args(argv)
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


if __name__ == "__main__":
    sys.exit(main())
