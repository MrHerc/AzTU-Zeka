"""The rules of a migration wave (tasks/todo.md, Task 38). No I/O.

A mapping (``content/mappings/<source>.json``) says, for each export file of the old system, the import kind it becomes,
which of its columns is which canonical column, which columns are left out and why, the transforms of a column (a name,
a group code, a date, a grade scale, a value list) and the constants every row gets. Applying it gives the rows of the
import kind and a report in which every column and every row is accounted for: mapped, left out with its reason, or
refused with its reason.
"""
from __future__ import annotations

from ...core.i18n import E
from ..integration import domain as imports

AZ_UPPER = str.maketrans({"i": "İ", "ı": "I"})
AZ_LOWER = str.maketrans({"I": "ı", "İ": "i"})
DEFAULT_HOURS = 2                                     # one pair, as the journal counts a lesson without its hours


def az_name(v: str) -> str:
    """``MƏMMƏDOVA aysel`` -> ``Məmmədova Aysel``: each word capitalised the Azerbaijani way, spaces collapsed."""
    out = []
    for word in " ".join((v or "").split()).split(" "):
        parts = [p[:1].translate(AZ_UPPER).upper() + p[1:].translate(AZ_LOWER).lower() for p in word.split("-")]
        out.append("-".join(parts))
    return " ".join(out).strip()


def group_code(v: str) -> str:
    """``651 a`` / ``651–a`` -> ``651A``: the group code as the registry writes it."""
    return "".join((v or "").replace("–", "-").replace("—", "-").split()).translate(AZ_UPPER).upper()


def _scale(v: str, spec: str) -> str:
    """``scale:10:100``: a score on the old system's scale written on Zəka's (2 decimals)."""
    try:
        _, low, high = spec.split(":")
        n = float((v or "").strip().replace(",", "."))
        return f"{round(n * float(high) / float(low), 2):g}"
    except ValueError:
        raise ValueError(spec) from None


def transform(name: str, v: str, values: dict[str, str] | None) -> str:
    """One column's transform; ValueError when the value cannot be read."""
    if name == "name":
        return az_name(v)
    if name == "group":
        return group_code(v)
    if name == "date":
        day = imports.a_date(v or "")
        if not day:
            raise ValueError(v)
        return day
    if name.startswith("scale:"):
        return _scale(v, name)
    if name == "values":
        hit = {imports.key(k): x for k, x in (values or {}).items()}.get(imports.key(v or ""))
        if hit is None:
            raise ValueError(v)
        return hit
    raise ValueError(name)


def check_spec(spec: dict) -> list[str]:
    """What is wrong with one file's mapping (an unknown kind or column, a transform of a column not mapped)."""
    kind = spec.get("kind")
    if kind not in imports.KINDS or kind == "teaching-load":
        return [f"unknown kind {kind!r}"]
    known = set(imports.COLUMNS[kind]) | ({"courseSourcedId", "termSourcedId"} if kind == "attendance" else set())
    problems = [f"unknown column {c!r}" for c in list(spec.get("columns", {}).values()) + list(spec.get("constants", {})) if c not in known]
    targets = set(spec.get("columns", {}).values()) | set(spec.get("constants", {}))
    problems += [f"transform of a column not mapped: {c!r}" for c in spec.get("transforms", {}) if c not in targets]
    return problems


def apply(spec: dict, header: list[str], rows: list[tuple[int, list[str]]]) -> tuple[str, list[str], list[dict], dict]:
    """(import kind, its header, its rows, the report) of one export file. A lesson-level attendance export without the
    class or the start of each lesson becomes opening balances per student and course (``aggregate``)."""
    columns, ignore = spec.get("columns", {}), spec.get("ignore", {})
    by_key = {imports.key(k): (k, v) for k, v in columns.items()}
    left = {imports.key(k): k for k in ignore}
    index: dict[str, int] = {}
    unexplained = []
    for i, h in enumerate(header):
        hit = by_key.get(imports.key(h))
        if hit:
            index[hit[1]] = i
        elif imports.key(h) not in left and h.strip():
            unexplained.append(h)
    missing = [k for k, v in columns.items() if v not in index]
    report: dict = {"file": spec.get("file"), "rows": len(rows), "mapped": sorted(index), "ignored": ignore,
                    "unexplained": unexplained, "missing": missing, "refused": []}
    out: list[dict] = []
    for n, r in rows:
        x = {col: (r[i] if i < len(r) else "").strip() for col, i in index.items()} | dict(spec.get("constants", {}))
        try:
            for col, name in spec.get("transforms", {}).items():
                if x.get(col):
                    x[col] = transform(name, x[col], spec.get("values", {}).get(col))
        except ValueError:
            report["refused"].append({"row": n, "reason": E("«{field}» sahəsinin dəyəri oxunmadı: {value}", field=col, value=x.get(col, ""))})
            continue
        out.append({"_row": n, **x})
    kind = spec["kind"]
    if kind == "attendance" and not {"classSourcedId", "start"} <= set(index) | set(spec.get("constants", {})):
        out, refused = aggregate_opening(out)
        report["refused"] += refused
        report["aggregated"] = True
        kind = "attendance-opening"
    head = list(imports.COLUMNS[kind])
    return kind, head, [{k: v for k, v in x.items() if k in head} | {"_row": x["_row"]} for x in out], report


def aggregate_opening(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Lesson records without their class or start, summed per student and course into opening balances: the hours held,
    missed without and with an excuse (a lesson without its hours is one pair)."""
    sums: dict[tuple[str, str, str], dict] = {}
    refused = []
    for x in rows:
        status = imports.MARKS.get(imports.key(x.get("status", "")))
        hours = imports.an_int(x.get("hours") or str(DEFAULT_HOURS), 1, 12)
        if not status or hours is None or not x.get("courseSourcedId") or not x.get("termSourcedId"):
            refused.append({"row": x["_row"], "reason": E("Dərs qeydi cəmlənmədi: fənn, semestr, qeyd və saat lazımdır")})
            continue
        k = (x["termSourcedId"], x["courseSourcedId"], x.get("userSourcedId", ""))
        s = sums.setdefault(k, {"_row": x["_row"], "termSourcedId": k[0], "courseSourcedId": k[1], "userSourcedId": k[2],
                                "heldHours": 0, "unexcusedHours": 0, "excusedHours": 0, "asOf": x.get("asOf", "")})
        s["heldHours"] += hours
        s["unexcusedHours"] += hours if status == "absent" else 0
        s["excusedHours"] += hours if status == "excused" else 0
    for s in sums.values():
        s.update({k: str(s[k]) for k in ("heldHours", "unexcusedHours", "excusedHours")})
    return list(sums.values()), refused


def explained(report: dict) -> bool:
    """Every column is mapped or left out with a reason, and every mapped column is in the file."""
    return not report["unexplained"] and not report["missing"]


def chunks(rows: list, size: int) -> list[list]:
    """A load larger than one import file holds, in files of at most ``size`` rows (each one atomic)."""
    return [rows[i:i + size] for i in range(0, len(rows), size)] or [[]]


def hour_differences(source: dict[tuple[int, int], tuple[int, int]], zeka: dict[tuple[int, int], tuple[int, int]]) -> list[dict]:
    """Student × course pairs whose unexcused or excused hours differ between the files and Zəka's imported records."""
    return [{"student_id": s, "course_id": cid, "source": list(v), "zeka": list(zeka.get((s, cid), (0, 0)))}
            for (s, cid), v in sorted(source.items()) if tuple(zeka.get((s, cid), (0, 0))) != tuple(v)]
