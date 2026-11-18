"""Reading an import file (tasks/todo.md, Task 16): CSV (UTF-8, comma, semicolon or tab) and XLSX, standard library only.

An XLSX file is an untrusted ZIP: members are read with the size caps of the Office reader and XML with a DTD is
refused (``legacy.engine``). Cell values are kept as text; the import kinds convert them.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field

from ...legacy.engine import MAX_ARCHIVE, _xml, _zip_read

MAX_ROWS = 200_000
MAX_COLS = 200
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
REF = re.compile(r"^([A-Z]{1,3})(\d{1,7})$")


class TableError(ValueError):
    """The file cannot be read; the message is an Azerbaijani catalogue key."""


@dataclass
class Sheet:
    name: str
    rows: list[list[str]]
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)     # (row1, col1, row2, col2), 0-based


def csv_rows(data: bytes) -> list[list[str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise TableError("CSV faylı UTF-8 kodlaşmasında olmalıdır") from None
    first = text.split("\n", 1)[0]
    delimiter = max(",;\t", key=first.count)
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    except csv.Error:
        raise TableError("CSV faylını oxumaq mümkün olmadı") from None
    if len(rows) > MAX_ROWS:
        raise TableError("Faylda sətir çox çoxdur")
    return [r for r in rows if any(x.strip() for x in r)]


def _cell(ref: str) -> tuple[int, int]:
    m = REF.match(ref or "")
    if not m:
        raise TableError("XLSX faylını oxumaq mümkün olmadı")
    col = 0
    for ch in m.group(1):
        col = col * 26 + ord(ch) - 64
    return int(m.group(2)) - 1, col - 1


def xlsx_sheets(data: bytes) -> list[Sheet]:
    if len(data) > MAX_ARCHIVE:
        raise TableError("XLSX faylını oxumaq mümkün olmadı")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return _sheets(z)
    except (zipfile.BadZipFile, KeyError, ValueError, IndexError, TypeError) as ex:
        if isinstance(ex, TableError):
            raise
        raise TableError("XLSX faylını oxumaq mümkün olmadı") from None


def _sheets(z: zipfile.ZipFile) -> list[Sheet]:
    budget = [MAX_ARCHIVE]
    names = set(z.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in _xml(_zip_read(z, "xl/sharedStrings.xml", budget)).iter(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    rels = {r.get("Id"): r.get("Target") for r in _xml(_zip_read(z, "xl/_rels/workbook.xml.rels", budget)).iter(PKG + "Relationship")}
    out = []
    for s in _xml(_zip_read(z, "xl/workbook.xml", budget)).iter(NS + "sheet"):
        target = (rels.get(s.get(REL)) or "").lstrip("/")
        path = target if target.startswith("xl/") else "xl/" + target
        root = _xml(_zip_read(z, path, budget))
        grid: dict[int, dict[int, str]] = {}
        for c in root.iter(NS + "c"):
            r, col = _cell(c.get("r"))
            if r >= MAX_ROWS or col >= MAX_COLS:
                raise TableError("Faylda sətir çox çoxdur")
            kind, v = c.get("t"), c.find(NS + "v")
            if kind == "s":
                value = shared[int(v.text)] if v is not None and v.text else ""
            elif kind == "inlineStr":
                value = "".join(t.text or "" for t in c.iter(NS + "t"))
            else:
                value = v.text if v is not None and v.text else ""
            if value:
                grid.setdefault(r, {})[col] = value
        width = 1 + max((max(cols) for cols in grid.values()), default=0)
        rows = [[grid.get(r, {}).get(col, "") for col in range(width)] for r in range(1 + max(grid, default=-1))]
        merges = []
        for m in root.iter(NS + "mergeCell"):
            a, _, b = (m.get("ref") or "").partition(":")
            (r1, c1), (r2, c2) = _cell(a), _cell(b or a)
            merges.append((r1, c1, r2, c2))
        out.append(Sheet(s.get("name") or "", rows, merges))
    return out


def table_rows(filename: str, data: bytes) -> list[list[str]]:
    """The rows of a CSV file or of the first sheet of an XLSX file."""
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        sheets = xlsx_sheets(data)
        return [r for r in sheets[0].rows if any(x.strip() for x in r)] if sheets else []
    if name.endswith((".csv", ".txt")):
        return csv_rows(data)
    raise TableError("Fayl CSV və ya XLSX olmalıdır")
