"""Forma №3, a department's academic load (docs/forms/forma-3.md): sheets in, teaching-load lines out. No I/O.

Two layouts: (A) one sheet of teacher blocks, each opened by ``<ştat> - <dərəcə>, <vəzifə>, <Soyad Ad Ata adı>``;
(B) one sheet per teacher with the name in E4. The header is found by its text (``Fənlər`` / ``FƏNNİN ADI``), never
by column letter; the semester of an hour column comes from the (merged) cell above the header.

Nothing is dropped without a word: a cell, column, header or row the reader cannot use is returned in ``skipped`` with
its place and reason, and the import shows it with the conflicts.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from ...core.i18n import E
from . import domain
from .tables import Sheet

MAX_HOURS = 10_000


def norm(v: str) -> str:
    """Compared form: Azerbaijani lower case, and Latin I = İ (``FƏNNIN ADI`` typed with I still matches)."""
    return domain.key(v)


SUBJECT = tuple(norm(x) for x in ("Fənlər", "FƏNNİN ADI"))
KINDS = tuple((norm(p), k) for p, k in (("Mühazirə", "lecture"), ("Məşğələ", "seminar"), ("Laboratoriya", "lab")))
TOTALS = tuple(norm(x) for x in ("Cəmi", "Cəm", "Aktiv"))
HOURLY = norm("SAAT HESABI")
SKIP_SHEETS = tuple(norm(x) for x in ("saat hesabı", "arayış"))
TEACHER_LINE = re.compile(r"ştat\s*-", re.IGNORECASE)


@dataclass
class Line:
    """One teaching unit read from the form: a row x a class type x a semester (a lecture stream may span rows)."""
    sheet: str
    row: int                                   # the sheet's row number (1-based), for the report
    teacher: str
    subject: str
    semester: str                              # "payiz" | "yaz" (compared form)
    kind: str                                  # lecture | seminar | lab
    hours: float
    students: int | None
    groups: list[tuple[str, int | None]] = field(default_factory=list)       # (group, subgroup)


def person(text: str) -> str:
    """``t.ü.f.d., dosent Quliyev Elçin Rauf oğlu`` -> ``Quliyev Elçin Rauf oğlu``: after the last comma, from the first
    capitalised word (degree and position words are written in lower case)."""
    tail = (text or "").rsplit(",", 1)[-1].split()
    for i, w in enumerate(tail):
        if w[:1].isupper():
            return " ".join(tail[i:])
    return " ".join(tail)


def _number(v: str) -> float | None:
    """A cell's number: empty is 0; text, infinity, NaN or an absurd size is None (the cell is reported)."""
    v = (v or "").strip().replace(",", ".")
    if not v:
        return 0.0
    try:
        n = float(v)
    except ValueError:
        return None
    return n if math.isfinite(n) and 0 <= n < MAX_HOURS else None


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
    """"payiz" | "yaz" | "year" (the year total, not a unit) | None (no label found)."""
    for r in (header - 1, header - 2):
        if r < 0:
            continue
        text = norm(_label(sheet, r, c))
        if not text:                           # an unmerged label is written once, at the left of its block
            text = next((norm(x) for x in reversed(sheet.rows[r][:c]) if x.strip()), "")
        if "il ərzində" in text:
            return "year"
        if "payiz" in text:
            return "payiz"
        if "yaz" in text:
            return "yaz"
    return None


def _columns(sheet: Sheet, h: int, skipped: list) -> dict:
    header = [norm(x) for x in sheet.rows[h]]
    cols: dict = {"hours": {}}
    for c, name in enumerate(header):
        if name in SUBJECT:
            cols["subject"] = c
        elif name.startswith("qrup"):
            cols["group"] = c
        elif name.startswith(norm("Tələbələrin sayı")):
            cols["students"] = c
        elif name.startswith(norm("Digər dərs yük")):
            cols["other"] = c
        else:
            kind = next((k for prefix, k in KINDS if name.startswith(prefix)), None)
            if not kind:
                continue
            semester = _semester(sheet, h, c)
            if semester in ("payiz", "yaz"):
                cols["hours"][c] = (semester, kind)
            elif semester is None:
                skipped.append((sheet.name, h + 1, E("Sütunun semestri tapılmadı: {x}", x=sheet.rows[h][c])))
    return cols


def _cell(row: list[str], c: int | None) -> str:
    return row[c].strip() if c is not None and c < len(row) else ""


def _block(sheet: Sheet, h: int, end: int, teacher: str, skipped: list) -> list[Line]:
    cols = _columns(sheet, h, skipped)
    if "subject" not in cols or "group" not in cols:
        skipped.append((sheet.name, h + 1, E("Başlıqda fənn və ya qrup sütunu yoxdur")))
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
        if any(HOURLY in x for x in texts):
            break                                               # the hourly-paid section is not teaching units
        if any(x in TOTALS or x.startswith(TOTALS[0]) for x in texts[:max(cols["subject"], cols["group"]) + 1]):
            continue
        if _cell(row, cols["subject"]):
            subject, stream = _cell(row, cols["subject"]), {}
        if not subject:
            continue
        group = _group(_cell(row, cols["group"]))
        students = _number(_cell(row, cols.get("students")))
        hours = {}
        for c, key in cols["hours"].items():
            value = _number(_cell(row, c))
            if value is None:
                skipped.append((sheet.name, r + 1, E("Saat oxunmadı: {x}", x=_cell(row, c)[:40])))
            elif value > 0:
                hours[key] = value
        if students is None:
            skipped.append((sheet.name, r + 1, E("Tələbə sayı oxunmadı: {x}", x=_cell(row, cols.get("students"))[:40])))
        students_n = int(students) if students else None
        if not group[0]:
            if hours:
                skipped.append((sheet.name, r + 1, E("Saatı olan sətirdə qrup yazılmayıb")))
            continue
        if not hours and students_n is None:
            continue
        other = person(_cell(row, cols.get("other")))
        lectured = set()
        for (semester, kind), value in hours.items():
            line = Line(sheet.name, r + 1, other if other and kind != "lecture" else teacher, subject, semester, kind, value,
                        students_n, [group])
            out.append(line)
            if kind == "lecture":
                stream[semester] = line
                lectured.add(semester)
        for semester, line in stream.items():                  # no lecture hours of its own: it joins the stream
            if semester not in lectured and group not in line.groups:
                line.groups.append(group)
                if students_n is not None:
                    line.students = (line.students or 0) + students_n
    return out


def read(sheets: list[Sheet]) -> tuple[list[Line], list[tuple[str, int, dict]]]:
    """The form's lines, and every (sheet, row, reason) the reader could not use."""
    out: list[Line] = []
    skipped: list[tuple[str, int, dict]] = []
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
            headers = [x for x in range(r + 1, end) if any(norm(v) in SUBJECT for v in rows[x])]
            if not headers:
                skipped.append((sheet.name, r + 1, E("Müəllimin blokunda başlıq tapılmadı")))
            for j, h in enumerate(headers):                    # each header reads only the rows up to the next one
                out += _block(sheet, h, headers[j + 1] if j + 1 < len(headers) else end, teacher, skipped)
    return out, skipped
