"""A migration wave (tasks/todo.md, Task 38): loading the old system's files and reconciling Zəka with them.

``load`` imports one file of an import kind through Task 16's import (dry run, all or nothing, links) and logs it with
the wave, the export moment and its SHA-256. ``reconcile`` reads the wave's files again and puts each through the same
import as a dry run: a row Zəka holds as the file has it is "unchanged"; any other row is a difference with its reason.
Only the rows of the files (their links) are compared, so a row created in Zəka is never a difference.
"""
from __future__ import annotations

import hashlib
import random
from pathlib import Path

from ...legacy.store import iso, now
from ..integration import importer
from ..journal import service as journal
from . import domain, repo

# import kind -> the link kinds its rows are written under
LINKS_OF = {"users": ("users",), "orgs": ("faculties", "departments"), "terms": ("terms",), "courses": ("courses",),
            "classes": ("classes",), "enrollments": ("enrollments", "unit_teachers"), "timetable": ("timetable",), "rooms": ("rooms",),
            "attendance-opening": ("attendance_opening",), "grades": ("grades",), "attendance": ("attendance",), "results": ("results",),
            "status-events": ("status_events",), "teaching-load": ("teaching_load",)}
SAME = ("unchanged", "relink")


def load(c, wave: int, source: str, kind: str, filename: str, data: bytes, *, as_of: str | None = None,
         exported_at: str | None = None, source_file: str | None = None, source_sha256: str | None = None,
         user_id: int | None = None, dry_run: bool = False, force: bool = False, prefer_source: bool = False) -> dict:
    """One file of the wave: imported (or checked) and, once written, logged for the reconciliation."""
    sha = hashlib.sha256(data).hexdigest()

    def log(c, report):                                # in the import's own transaction: no file written but unlogged (SF-F5)
        repo.add_file(c, {"wave": wave, "source": source, "kind": kind, "filename": filename, "sha256": sha,
                          "source_file": source_file or filename, "source_sha256": source_sha256 or sha, "rows": report["rows"],
                          "as_of": as_of, "exported_at": exported_at, "imported_at": iso(now()), "imported_by": user_id})
    return importer.run(c, kind, source, filename, data, dry_run=dry_run, prefer_source=prefer_source, user_id=user_id,
                        as_of=as_of, force=force, on_written=log)


def reconcile(c, wave: int, source: str, folder: Path, sample: int = 50, user_id: int | None = None) -> dict:
    """The wave's reconciliation report: per entity the source rows and the rows linked to them, each file's SHA-256
    and export moment, the key-field checksums (source and Zəka), the absence hours per student and course, every
    difference with its reason and ``sample`` random records for a person to check. When the whole wave reconciles and
    ``user_id`` names who checked it, a student whose history (``results``) reconciles gets ``history_reconciled_at``
    (Checkpoint F, SF-F2: never from a partial wave, never without an actor)."""
    files = repo.files(c, wave, source)
    out: dict = {"wave": wave, "source": source, "files": [], "entities": {}, "differences": [], "hours": [], "sample": [],
                 "exported_at": sorted({f["exported_at"] for f in files if f["exported_at"]})}
    pool: list[dict] = []
    hours: dict[tuple[int, int], list[int]] = {}
    history: dict[int, bool] = {}
    marks: list[int] = []
    openings: list[int] = []
    for f in files:
        path = folder / f["filename"]
        data = path.read_bytes() if path.is_file() else None
        sha = hashlib.sha256(data).hexdigest() if data is not None else None
        entry = {"filename": f["filename"], "kind": f["kind"], "rows": f["rows"], "sha256": f["sha256"], "sha256_now": sha,
                 "source_file": f["source_file"], "source_sha256": f["source_sha256"], "exported_at": f["exported_at"], "as_of": f["as_of"]}
        out["files"].append(entry)
        if data is None or sha != f["sha256"]:
            out["differences"].append({"file": f["filename"], "reason": "the file is missing or changed since it was loaded"})
            continue
        dry = importer.run(c, f["kind"], source, f["filename"], data, dry_run=True, as_of=f["as_of"], detail=True)
        entry["checksums"] = dry.get("checksums")      # a file the import now refuses as a whole has none (PY-F4)
        ent = out["entities"].setdefault(f["kind"], {"source": 0, "linked": 0})
        ent["source"] += dry["rows"]
        ent["linked"] += sum(1 + i["aliases"] for i in dry.get("items", []) if i["linked"] and i["action"] != "insert")
        for e in dry["errors"]:
            out["differences"].append({"file": f["filename"], "row": e["row"], "reason": e["reason"]})
        for i in dry.get("items", []):
            if i["row_id"] is not None and i["action"] != "insert":   # the very records Zəka holds for these rows (CR-F2)
                (marks if i["link"] == "attendance" else openings if i["link"] == "attendance_opening" else []).append(i["row_id"])
            if i["action"] not in SAME:
                out["differences"].append({"file": f["filename"], "row": i["row"], "source_id": i["source_id"], "action": i["action"],
                                           "fields": i["fields"], "zeka_id": i["row_id"]})
            if f["kind"] == "results":
                uid = i["values"]["user_id"]
                history[uid] = history.get(uid, True) and i["action"] in SAME
            pool.append({"file": f["filename"], **{k: i[k] for k in ("row", "source_id", "row_id", "action", "values")}})
        for pair, (u, e) in dry.get("hours", {}).items():
            s, cid = (int(x) for x in pair.split("|"))
            acc = hours.setdefault((s, cid), [0, 0])
            acc[0] += u
            acc[1] += e
    held = journal.hours_of(c, marks, openings)       # the same records on both sides: another wave's do not count
    zeka = {(int(k.split("|")[0]), int(k.split("|")[1])): (v[0], v[1]) for k, v in held.items()}
    out["hours"] = domain.hour_differences({k: (v[0], v[1]) for k, v in hours.items()}, zeka)
    out["hour_pairs"] = len(hours)
    rng = random.Random(f"{wave}|{source}")
    out["sample"] = rng.sample(pool, min(sample, len(pool)))
    out["ok"] = not out["differences"] and not out["hours"] and all(v["source"] == v["linked"] for v in out["entities"].values())
    marked = [uid for uid, ok in history.items() if ok and not journal.history_reconciled(c, uid)] if out["ok"] and user_id else []
    for uid in marked:                                 # the history before Zəka is checked: the transcript can be issued
        journal.reconcile(c, {"id": user_id}, uid)
    if marked:
        c.commit()
    out["history_reconciled"] = len(marked)
    return out
