"""SQL of a migration wave's file log (tasks/todo.md, Task 38)."""
from __future__ import annotations

from ...legacy.store import row, rows


def add_file(c, v: dict) -> int:
    return c.execute("INSERT INTO migration_files(wave,source,kind,filename,sha256,source_file,source_sha256,rows,as_of,exported_at,"
                     "imported_at,imported_by) VALUES(:wave,:source,:kind,:filename,:sha256,:source_file,:source_sha256,:rows,:as_of,"
                     ":exported_at,:imported_at,:imported_by)", v).lastrowid


def files(c, wave: int, source: str) -> list[dict]:
    """The wave's files from one source, each by its last load, in load order."""
    return rows(c, "SELECT * FROM migration_files WHERE id IN (SELECT MAX(id) FROM migration_files WHERE wave=? AND source=? "
                   "GROUP BY filename) ORDER BY id", (wave, source))


def last_file(c, wave: int, source: str, filename: str):
    return row(c, "SELECT * FROM migration_files WHERE wave=? AND source=? AND filename=? ORDER BY id DESC LIMIT 1",
               (wave, source, filename))
