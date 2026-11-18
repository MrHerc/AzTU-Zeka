"""Forward-only schema migrations for the SQLite database.

Files: ``backend/migrations/NNNN_name.sql``; NNNN = task number x 10 (tasks/todo.md, Task 4). Each file runs once, in
number order, inside its own transaction together with its row in ``schema_migrations``, so a failing file leaves
neither a half-applied schema nor a log entry. An applied file is never edited: the engine refuses to start when a
checksum changed, when the database knows a version that has no file (the database is newer than the code) or when
two files share a number. Before the first pending file of a run, a copy of the database is written to ``backup_dir``.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import datetime
from pathlib import Path

DIR = Path(__file__).resolve().parents[2] / "migrations"
NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
KEEP_BACKUPS = 5
LOG = """CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, name TEXT NOT NULL,
  checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"""


class MigrationError(RuntimeError):
    """The migration files and the database disagree; the server must not start."""


def discover(directory: Path = DIR) -> list[tuple[int, str, Path]]:
    """(version, name, path) of every migration file, in number order."""
    found: dict[int, tuple[int, str, Path]] = {}
    for p in sorted(directory.glob("*.sql")):
        m = NAME.match(p.name)
        if not m:
            raise MigrationError(f"{p.name}: the name must be NNNN_name.sql (lower case, digits, underscores)")
        version = int(m.group(1))
        if version in found:
            raise MigrationError(f"two migrations share number {m.group(1)}: {found[version][2].name}, {p.name}")
        found[version] = (version, m.group(2), p)
    return [found[v] for v in sorted(found)]


def checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def status(conn: sqlite3.Connection, directory: Path = DIR) -> dict:
    """Applied and pending versions; raises MigrationError on any inconsistency."""
    conn.execute(LOG)
    files = {v: (name, path) for v, name, path in discover(directory)}
    applied = {r[0]: r[1] for r in conn.execute("SELECT version, checksum FROM schema_migrations")}
    unknown = sorted(set(applied) - set(files))
    if unknown:
        raise MigrationError(f"the database has migration(s) {unknown} that this code does not have: it is newer than the code")
    changed = [f"{v:04d}_{files[v][0]}.sql" for v in sorted(applied) if checksum(files[v][1]) != applied[v]]
    if changed:
        raise MigrationError(f"applied migration file(s) were edited: {changed}; add a new migration instead")
    return {"applied": sorted(applied), "pending": [v for v in sorted(files) if v not in applied]}


def _has_tables(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name<>'schema_migrations' LIMIT 1").fetchone() is not None


def _backup(conn: sqlite3.Connection, backup_dir: Path, version: int) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"pre-{version:04d}-{datetime.now():%Y%m%d-%H%M%S-%f}.db"
    dest = sqlite3.connect(target)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    for old in sorted(backup_dir.glob("pre-*.db"), key=lambda p: p.stat().st_mtime)[:-KEEP_BACKUPS]:
        old.unlink()
    return target


def apply(conn: sqlite3.Connection, directory: Path = DIR, backup_dir: Path | None = None) -> list[int]:
    """Apply every pending migration in number order; returns the versions applied."""
    pending = status(conn, directory)["pending"]
    if pending and backup_dir is not None and _has_tables(conn):
        _backup(conn, backup_dir, pending[0])
    paths = {v: (name, path) for v, name, path in discover(directory)}
    done = []
    for v in pending:
        name, path = paths[v]
        sql = path.read_text(encoding="utf-8")
        stamp = datetime.now().isoformat(timespec="seconds")
        # name matches [a-z0-9_]+ and checksum is hex, so the literals below cannot break out of their quotes
        script = (f"BEGIN;\n{sql}\n;\nINSERT INTO schema_migrations(version,name,checksum,applied_at) "
                  f"VALUES({v},'{name}','{checksum(path)}','{stamp}');\nCOMMIT;")
        try:
            conn.executescript(script)  # nosec B608 - see the comment above
        except sqlite3.Error as ex:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise MigrationError(f"{path.name} failed and was rolled back: {ex}") from ex
        done.append(v)
    return done
