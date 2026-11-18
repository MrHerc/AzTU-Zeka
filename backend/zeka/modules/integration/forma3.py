"""Forma №3, a department's academic load (docs/forms/forma-3.md): sheets in, teaching-load lines out. No I/O.

Two layouts: (A) one sheet of teacher blocks, each opened by ``<ştat> - <dərəcə>, <vəzifə>, <Soyad Ad Ata adı>``;
(B) one sheet per teacher with the name in E4. The header is found by its text (``Fənlər`` / ``FƏNNİN ADI``), never
by column letter; the semester of an hour column comes from the (merged) cell above the header.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import domain
from .tables import Sheet

SUBJECT = ("fənlər", "fənnin adı")
KINDS = (("mühazirə", "lecture"), ("məşğələ", "seminar"), ("laboratoriya", "lab"))
TOTALS = ("cəmi", "cəm", "aktiv")
SKIP_SHEETS = ("saat hesabı", "arayış")
TEACHER_LINE = re.compile(r"ştat\s*-", re.IGNORECASE)


@dataclass
class Line:
    """One teaching unit read from the form: a row x a class type x a semester (a lecture stream may span rows)."""
    sheet: str
    row: int                                   # the sheet's row number (1-based), for the report
    teacher: str
    subject: str
    semester: str                              # "payız" | "yaz"
    kind: str                                  # lecture | seminar | lab
    hours: float
    students: int | None
    groups: list[tuple[str, int | None]] = field(default_factory=list)       # (group, subgroup)


def norm(v: str) -> str:
    return domain.norm(v)


def person(text: str) -> str:
    """``t.ü.f.d., dosent Quliyev Elçin Rauf oğlu`` -> ``Quliyev Elçin Rauf oğlu``: after the last comma, from the first
    capitalised word (degree and position words are written in lower case)."""
    tail = (text or "").rsplit(",", 1)[-1].split()
    for i, w in enumerate(tail):
        if w[:1].isupper():
            return " ".join(tail[i:])
    return " ".join(tail)


def _number(v: str) -> float:
    try:
        return float((v or "").strip().replace(",", ".") or 0)
    except ValueError:
        return 0.0


def _group(v: str) -> tuple[str, int | None]:
    """``6526e 1`` -> (``6526e``, 1): a trailing 1 or 2 is the subgroup."""
    m = re.fullmatch(r"(.+?)\s+([12])", (v or "").strip())
    return (m.group(1), int(m.group(2))) if m else ((v or "").strip(), None)


def _label(sheet: Sheet, r: int, c: int) -> str:
    for r1, c1, r2, c2 in sheet.merges:
        if r1 <= r <= r2 and c1 <= c <= c2:
            return sheet.rows[r1][c1] if r1 < len(sheet.rows) and c1 < len(sheet.rows[r1]) else ""
    return sheet.rows[r][c] if c < len(sheet.rows[r]) else ""


def _semester(sheet: Sheet, header: int, c: int) -> str | None:
    for r in (header - 1, header - 2):
        if r < 0:
            continue
        text = norm(_label(sheet, r, c))
        if not text:                           # an unmerged label is written once, at the left of its block
            text = next((norm(x) for x in reversed(sheet.rows[r][:c]) if x.strip()), "")
        if "il ərzində" in text:
            return None
        if "payız" in text:
            return "payız"
        if "yaz" in text:
            return "yaz"
    return None


def _columns(sheet: Sheet, h: int) -> dict:
    header = [norm(x) for x in sheet.rows[h]]
    cols: dict = {"hours": {}}
    for c, name in enumerate(header):
        if name in SUBJECT:
            cols["subject"] = c
        elif name.startswith("qrup"):
            cols["group"] = c
        elif name.startswith("tələbələrin sayı"):
            cols["students"] = c
        elif name.startswith("digər dərs yük"):
            cols["other"] = c
        else:
            kind = next((k for prefix, k in KINDS if name.startswith(prefix)), None)
            semester = _semester(sheet, h, c) if kind else None
            if kind and semester:
                cols["hours"][c] = (semester, kind)
    return cols


def _cell(row: list[str], c: int | None) -> str:
    return row[c].strip() if c is not None and c < len(row) else ""


def _block(sheet: Sheet, h: int, end: int, teacher: str) -> list[Line]:
    cols = _columns(sheet, h)
    if "subject" not in cols or "group" not in cols:
        return []
    out: list[Line] = []
    subject = ""
    stream: dict[str, Line] = {}                                # semester -> the lecture of this subject
    start = h + 1
    if start < end and all(not x.strip() or re.fullmatch(r"\d+", x.strip()) for x in sheet.rows[start]):
        start += 1                                              # the row of column numbers 1, 2, 3 ...
    for r in range(start, end):
        row = sheet.rows[r]
        texts = [norm(x) for x in row]
        if any("saat hesabı" in x for x in texts):
            break                                               # the hourly-paid section is not teaching units
        if any(x in TOTALS or x.startswith("cəmi") for x in texts[:max(cols["subject"], cols["group"]) + 1]):
            continue
        if _cell(row, cols["subject"]):
            subject, stream = _cell(row, cols["subject"]), {}
        if not subject:
            continue
        group = _group(_cell(row, cols["group"]))
        students_text = _cell(row, cols.get("students"))
        students = int(_number(students_text)) if students_text else None
        hours = {key: _number(_cell(row, c)) for c, key in cols["hours"].items()}
        if not group[0] or not any(v > 0 for v in hours.values()) and students is None:
            continue
        other = person(_cell(row, cols.get("other")))
        lectured: set[str] = set()
        for (semester, kind), value in hours.items():
            if value <= 0:
                continue
            line = Line(sheet.name, r + 1, other if other and kind != "lecture" else teacher, subject, semester, kind, value,
                        students, [group])
            out.append(line)
            if kind == "lecture":
                stream[semester] = line
                lectured.add(semester)
        for semester, line in stream.items():                  # no lecture hours of its own: it joins the stream
            if semester not in lectured and group not in line.groups:
                line.groups.append(group)
                line.students = (line.students or 0) + (students or 0) if students is not None else line.students
    return out


def _header_rows(sheet: Sheet, start: int, end: int) -> list[int]:
    return [r for r in range(start, end) if any(norm(x) in SUBJECT for x in sheet.rows[r])]


def read(sheets: list[Sheet]) -> list[Line]:
    out: list[Line] = []
    for sheet in sheets:
        if any(s in norm(sheet.name) for s in SKIP_SHEETS):
            continue
        rows = sheet.rows
        starts = [(r, person(next(x for x in row if TEACHER_LINE.search(x))))
                  for r, row in enumerate(rows) if any(TEACHER_LINE.search(x) for x in row)]
        if not starts and len(rows) > 3 and len(rows[3]) > 4 and rows[3][4].strip():
            starts = [(3, person(rows[3][4]))]                 # layout B: the name in E4
        for i, (r, teacher) in enumerate(starts):
            end = starts[i + 1][0] if i + 1 < len(starts) else len(rows)
            for h in _header_rows(sheet, r + 1, end)[:1]:
                out += _block(sheet, h, end, teacher)
    return out
