"""The writers of the old system's records (tasks/todo.md, Task 38): the import (integration/importer.py) checks a row,
resolves its references and compares it; the module that owns the record writes it, through its service."""
from __future__ import annotations

import sqlite3

from ..directory import service as directory
from ..journal import service as journal


def mark(c, ctx, it, values: dict, user_id: int | None, t: str) -> int:
    """A lesson record up to the cut-over: source ``legacy`` with the export's date."""
    return journal.import_mark(c, values["lesson_id"], values["user_id"], values["status"], it.extra["as_of"], user_id, t)


def result(c, ctx, it, values: dict, user_id: int | None, t: str) -> int:
    """A final grade of a term before Zəka (the transcript's history)."""
    return journal.put_history(c, None if it.action == "insert" else it.row_id, values, t)


def status_event(c, ctx, it, values: dict, user_id: int | None, t: str) -> int:
    """A status order given in the old system, with the importing account as the one who entered it: written as history;
    its effects come from the student's newest order once the whole file is in (``finish``)."""
    status, event = directory.record_status(c, {"id": user_id}, it.extra["student"], {**values, "note": it.extra["note"]}, history=True)
    if status != "ok":                                 # checked when the row was read; the registry changed meanwhile
        raise sqlite3.IntegrityError(str(event))
    return int(event)                                  # type: ignore[call-overload]  # the event's id


def status_finish(c, items: list) -> None:
    """After the file's orders are written: each student's newest order acts (Checkpoint F, AR-F1)."""
    for sid in sorted({it.extra["student"]["id"] for it in items if it.link == "status_events" and it.action == "insert"}):
        directory.apply_newest(c, sid)


WRITERS = {"attendance": mark, "results": result, "status_events": status_event}
FINISH = (status_finish,)          # run by the import after its rows are written, in the same transaction
