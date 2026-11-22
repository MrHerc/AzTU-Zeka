"""Reading an import file (tasks/todo.md, Task 16): CSV (UTF-8, comma, semicolon or tab) and XLSX, standard library only.

An XLSX file is an untrusted ZIP: members are read with the size caps of the Office reader and XML with a DTD is
refused (``legacy.engine``); the cells a file may expand to are capped (a few bytes can name cell GR199999), and every
way a damaged archive fails is a refusal, never a 500. Cell values are kept as text; the import kinds convert them.
Rows keep their number in the file, so a report names the line the person sees.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from xml.etree.ElementTree import ParseError

from ...legacy.engine import MAX_ARCHIVE, _xml, _zip_read

MAX_ROWS = 200_000
MAX_COLS = 200
MAX_CELLS = 4_000_000                 # rows x columns over all sheets, once filled out
MAX_SHEETS = 200
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
PKG = "{http://schemas.openxmlformats.org/package/2006/relationships}"
REF = re.compile(r"^([A-Z]{1,3})(\d{1,7})$")
BROKEN = (zipfile.BadZipFile, KeyError, ValueError, IndexError, TypeError, ParseError, RuntimeError, NotImplementedError,
          zlib.error, EOFError)


class TableError(ValueError):
    """The file cannot be read; the message is an Azerbaijani catalogue key."""


@dataclass
class Sheet:
    name: str
    rows: list[list[str]]
    merges: list[tuple[int, int, int, int]] = field(default_factory=list)     # (row1, col1, row2, col2), 0-based
    state: str = "visible"                                                    # visible | hidden | veryHidden
    hidden_rows: set[int] = field(default_factory=set)                        # 0-based rows with hidden="1"
    # (row, col) -> the cell's formula text without "="; "" for a cell that repeats a shared formula. Values are
    # always the cached ones: a formula is never evaluated, it only explains where a number comes from (Task 47).
    formulas: dict[tuple[int, int], str] = field(default_factory=dict)


def _filled(row) -> bool:
    return any(x.strip() for x in row)


def csv_rows(data: bytes) -> list[tuple[int, list[str]]]:
    """(line number, cells) of every non-empty row."""
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
    return [(n + 1, r) for n, r in enumerate(rows) if _filled(r)]


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
    except TableError:
        raise
    except BROKEN:
        raise TableError("XLSX faylını oxumaq mümkün olmadı") from None


def _sheets(z: zipfile.ZipFile) -> list[Sheet]:
    budget = [MAX_ARCHIVE]
    names = set(z.namelist())
    shared = []
    if "xl/sharedStrings.xml" in names:
        for si in _xml(_zip_read(z, "xl/sharedStrings.xml", budget)).iter(NS + "si"):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
    rels = {r.get("Id"): r.get("Target") for r in _xml(_zip_read(z, "xl/_rels/workbook.xml.rels", budget)).iter(PKG + "Relationship")}
    out: list[Sheet] = []
    seen: set[str] = set()
    cells = 0
    for s in _xml(_zip_read(z, "xl/workbook.xml", budget)).iter(NS + "sheet"):
        target = (rels.get(s.get(REL)) or "").lstrip("/")
        path = target if target.startswith("xl/") else "xl/" + target
        if path in seen or len(seen) >= MAX_SHEETS:
            raise TableError("XLSX faylını oxumaq mümkün olmadı")      # one sheet listed twice multiplies the work
        seen.add(path)
        root = _xml(_zip_read(z, path, budget))
        grid: dict[int, dict[int, str]] = {}
        formulas: dict[tuple[int, int], str] = {}
        hidden = {int(x.get("r")) - 1 for x in root.iter(NS + "row")
                  if x.get("hidden") in ("1", "true") and (x.get("r") or "").isdigit()}
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
            f = c.find(NS + "f")
            if f is not None:
                formulas[(r, col)] = (f.text or "")[:500]
        width = 1 + max((max(cols) for cols in grid.values()), default=0)
        height = 1 + max(grid, default=-1)
        cells += width * height
        if cells > MAX_CELLS:                                          # checked before the rows are filled out
            raise TableError("XLSX faylı çox böyükdür (boş xanalar da sayılır)")
        rows = [[grid.get(r, {}).get(col, "") for col in range(width)] for r in range(height)]
        merges = []
        for m in root.iter(NS + "mergeCell"):
            a, _, b = (m.get("ref") or "").partition(":")
            (r1, c1), (r2, c2) = _cell(a), _cell(b or a)
            merges.append((r1, c1, r2, c2))
        state = s.get("state") if s.get("state") in ("hidden", "veryHidden") else "visible"
        out.append(Sheet(s.get("name") or "", rows, merges, state, {r for r in hidden if r < height}, formulas))
    return out


def table_rows(filename: str, data: bytes) -> list[tuple[int, list[str]]]:
    """(row number in the file, cells) of the non-empty rows of a CSV file or of the one sheet of an XLSX file."""
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        sheets = [s for s in xlsx_sheets(data) if any(_filled(r) for r in s.rows)]
        if len(sheets) > 1:
            raise TableError("XLSX faylında məlumat yalnız bir vərəqdə olmalıdır")
        return [(n + 1, r) for n, r in enumerate(sheets[0].rows) if _filled(r)] if sheets else []
    if name.endswith((".csv", ".txt")):
        return csv_rows(data)
    raise TableError("Fayl CSV və ya XLSX olmalıdır")
