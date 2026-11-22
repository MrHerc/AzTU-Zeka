"""Writes the synthetic import fixtures (tasks/todo.md, Tasks 16 and 47). Every name is made up; the real Forma №3 files
the owner gave (staff names, degrees, posts) never enter the repository. Run: python tests/fixtures/make_fixtures.py

forma3_blocks.xlsx   layout A as a department fills it: a sheet of teacher blocks with its own header and totals row, a
                     second form sheet of another year, an empty sheet, the summary sheet and a list sheet
forma3_sheets.xlsx   layout B: a sheet per teacher with a two-row header and labelled sections, vacancies, a hidden sheet
                     Both carry every case of docs/forms/forma-3.md that the tests name (tests/unit/test_forma3.py).
users_10k.csv        10 000 students in the OneRoster users format, in the demo groups
attendance_lessons.csv, attendance_opening.csv, grades.csv, status_events.csv   an old system's exports (Task 38)
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
STAMP = (2026, 11, 18, 0, 0, 0)
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


class F:
    """A formula cell: its text (without "=") and the cached value a reader sees."""

    def __init__(self, formula: str, cached):
        self.formula, self.cached = formula, cached


def _sheet_xml(rows: list[list], merges: list[str], hidden: frozenset = frozenset()) -> str:
    out = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{MAIN}"><sheetData>']
    for r, row in enumerate(rows):
        cells = []
        for c, v in enumerate(row):
            if v in ("", None):
                continue
            ref = f"{_col(c)}{r + 1}"
            f = ""
            if isinstance(v, F):
                f, v = f"<f>{escape(v.formula)}</f>", v.cached
            if isinstance(v, (int, float)):
                cells.append(f'<c r="{ref}">{f}<v>{v}</v></c>')
            elif str(v).startswith("#") and str(v).endswith(("!", "?")):          # a stored error value: #REF!, #NAME?
                cells.append(f'<c r="{ref}" t="e">{f}<v>{escape(str(v))}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>')
        if cells or r + 1 in hidden:
            out.append(f"""<row r="{r + 1}"{' hidden="1"' if r + 1 in hidden else ''}>{''.join(cells)}</row>""")
    out.append("</sheetData>")
    if merges:
        out.append(f'<mergeCells count="{len(merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in merges) + "</mergeCells>")
    out.append("</worksheet>")
    return "".join(out)


def xlsx(sheets: list) -> bytes:
    """``sheets``: (name, rows, merges) tuples or ``Cells``."""
    sheets = [x if isinstance(x, Cells) else Cells(x[0]).fill(x[1], x[2]) for x in sheets]
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                               '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                               '<Default Extension="xml" ContentType="application/xml"/>'
                               '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                               + "".join(f'<Override PartName="/xl/worksheets/sheet{i + 1}.xml" '
                                         'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                                         for i in range(len(sheets))) + "</Types>",
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       f'<Relationship Id="rId1" Type="{RELS}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{MAIN}" xmlns:r="{RELS}"><sheets>'
                           + "".join(f'<sheet name="{escape(x.name)}" sheetId="{i + 1}" ' + ('state="hidden" ' if x.state == "hidden" else "") +
                                     f'r:id="rId{i + 1}"/>' for i, x in enumerate(sheets))
                           + "</sheets></workbook>",
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      + "".join(f'<Relationship Id="rId{i + 1}" Type="{RELS}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                                                for i in range(len(sheets))) + "</Relationships>",
    }
    for i, x in enumerate(sheets):
        files[f"xl/worksheets/sheet{i + 1}.xml"] = _sheet_xml(x.rows(), x.merges, frozenset(x.hidden))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(zipfile.ZipInfo(name, STAMP), text)
    return buf.getvalue()


def _num(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n - 1


class Cells:
    """One sheet written cell by cell: ``put("E12", 30)``, ``merge("E12:E14")``; rows are 1-based as a person sees them."""

    def __init__(self, name: str, state: str = "visible"):
        self.name, self.state = name, state
        self.v: dict[tuple[int, int], object] = {}
        self.merges: list[str] = []
        self.hidden: set[int] = set()

    def fill(self, rows: list[list], merges: list[str]):
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                if v not in ("", None):
                    self.v[(r + 1, c)] = v
        self.merges += merges
        return self

    def put(self, col: str, row: int, value):
        if value not in ("", None):
            self.v[(row, _num(col))] = value

    def row(self, row: int, cells: dict):
        for col, value in cells.items():
            self.put(col, row, value)

    def get(self, col: str, row: int):
        v = self.v.get((row, _num(col)))
        return v.cached if isinstance(v, F) else v

    def merge(self, a: str, row: int, b: str | None = None, row2: int | None = None):
        self.merges.append(f"{a}{row}:{b or a}{row2 or row}")

    def rows(self) -> list[list]:
        height = max((r for r, _ in self.v), default=0)
        width = 1 + max((c for _, c in self.v), default=0)
        return [[self.v.get((r, c), "") for c in range(width)] for r in range(1, height + 1)]


def _sum(sh: Cells, cols: list[str], rows) -> float:
    """What a SUM over the cells gives: a merged value stands once, in its top-left cell."""
    return sum(v for r in rows for c in cols for v in [sh.get(c, r)] if isinstance(v, (int, float)))


# ---------------------------------------------------------------- layout A (docs/forms/forma-3.md, A1–A13)
A_TITLES = ["Sıra sayı", "Qruplar", "Fənlər", "Tələbələrin sayı", "Mühazirə", "Məşğələ", "Laboratoriya", "Məsləhət",
            "İmtahan suallarının hazırlanması", "İmtahan", "Kurs layihəsi (işi)", "Magistrların işi", "Təcrübə", "Aspirantlara dərs",
            "DAK (DİK), İŞ", "Referat", "Müəllimlərin dərslərdə iştirakı", "CƏMİ", "Mühazirə", "Məşğələ", "Laboratoriya", "Məsləhət",
            "İmtahan suallarının hazırlanması", "İmtahan", "Kurs layihəsi (işi)", "Magistrların işi", "Təcrübə", "Aspirantlara dərs",
            "DAK (DİK), İŞ və rəy", "Referat", "Müəllimlərin dərslərdə iştirakı", "Buraxılış işi", "CƏMİ", "İl ərzində cəmi",
            "Digər kafedranın dərs yükü"]
A_AUTUMN = [_col(i) for i in range(4, 17)]                     # E..Q
A_SPRING = [_col(i) for i in range(18, 32)]                    # S..AF
UNIVERSITY = "AZƏRBAYCAN TEXNİKİ UNİVERSİTETİ"
DEPARTMENT_A = '"NÜMUNƏ RADİOTEXNİKA" KAFEDRASI'


def _year_a(year: str = "2026/27") -> str:
    return f"{year}-CI TƏDRİS İLİ ÜÇÜN AKADEMİK YÜK"


def block_a(sh: Cells, top: int, staff: str, data: list[dict], merges=(), titles=None, damaged: dict | None = None,
            total_label: str = "Cəmi:", row_total_merge: tuple[int, int] | None = None) -> int:
    """A teacher block from row ``top``: three title rows, the staff line, the semester labels (the autumn one reaches S,
    the spring lecture column, as in the real files), the header, the column numbers, the data rows and the total row.
    ``merges``: (column, first data row index, last). Returns the total row."""
    r = top
    for text in titles or (UNIVERSITY, _year_a(), DEPARTMENT_A):
        sh.put("A", r, text)
        sh.merge("A", r, "AI")
        r += 1
    sh.put("A", r, staff)
    sh.merge("A", r, "AI")
    sh.row(r + 1, {"A": "payız semestri", "T": "yaz semestri "})
    sh.merge("A", r + 1, "S")
    sh.merge("T", r + 1, "AI")
    for i, title in enumerate(A_TITLES):
        sh.put(_col(i), r + 2, (damaged or {}).get(_col(i), title))
        sh.put(_col(i), r + 3, str(i + 1))
    first = r + 4
    for i, row in enumerate(data):
        sh.row(first + i, row)
    for col, i, j in merges:
        sh.merge(col, first + i, col, first + j)
    total = first + len(data)
    spans = [range(first + row_total_merge[0], first + row_total_merge[1] + 1)] if row_total_merge else []
    for rr in range(first, total):
        span = next((x for x in spans if rr in x), None)
        if span and rr != span[0]:
            continue
        rows = span or [rr]
        if not any(sh.get(c, x) is not None for x in rows for c in ("B", "C")):
            continue
        aut, spr = _sum(sh, A_AUTUMN, rows), _sum(sh, A_SPRING, rows)
        sh.row(rr, {"R": aut, "AG": spr, "AH": aut + spr})
        if span:
            for col in ("R", "AG", "AH"):
                sh.merge(col, span[0], col, span[-1])
    sh.put("A", total, total_label)
    sh.merge("A", total, "D")
    for col in (*A_AUTUMN, *A_SPRING, "AI"):
        sh.put(col, total, _sum(sh, [col], range(first, total)) or 0)
    aut, spr = _sum(sh, A_AUTUMN, [total]), _sum(sh, A_SPRING, [total])
    sh.row(total, {"R": aut, "AG": spr, "AH": aut + spr, "AJ": _sum(sh, ["E", "F", "G", "S", "T", "U"], [total])})
    return total


def forma3_blocks() -> bytes:
    sh = Cells("Forma №3")
    for i, title in enumerate(A_TITLES):                       # the sheet's own header: no staff line above it (A4)
        sh.put(_col(i), 1, "Doktorantura (Dissertantura)" if _col(i) == "AF" else title)
    sh.row(2, {"A": "payız semestri", "T": "yaz semestri "})
    sh.merge("A", 2, "S")
    sh.merge("T", 2, "AI")
    totals = []
    # 1: a lecture stream of three groups, a joint seminar of two, a merged exam-paper cell, a practice row, a TD row
    totals.append(block_a(sh, 4, "1 ştat - t.ü.f.d., dosent, Quliyev Elçin Rauf oğlu", [
        {"A": 1, "B": "6524a1", "C": "Alqoritmlər", "D": 25, "E": 30, "F": 15, "H": 1, "I": 5, "J": 8.3},
        {"B": "6524a2", "D": 24, "H": 1, "J": 8},
        {"B": "6524a3", "D": 26, "F": 15, "H": 1, "J": 8.666666666666666},
        {"A": 2, "B": "6524a1", "C": "Verilənlər bazaları", "D": 25, "S": 30, "T": 15, "V": 1, "W": 5, "X": 8.333333333333334},
        {"A": 3, "B": "6523a1", "C": "İstehsalat təcrübəsi", "D": 20, "AA": 40},
        {"A": 4, "C": "TD-20 10.10.2024 Uydurmayev Anar (Elmi rəhbər: Quliyev Elçin Rauf oğlu)", "AF": 80},
    ], merges=[("C", 0, 2), ("E", 0, 2), ("F", 0, 1), ("I", 0, 2)]))
    # 2: the first title row is not the university line (A2); no oğlu/qızı (A6); a damaged title (H5); one seminar for
    #    eight groups with merged load and per-row totals; an empty merge that mirrors block 1's lecture (J3); 6526e 1/2/3
    eight = [("6524a1", 2), ("6524a2", 2), ("6524a3", 1), ("6523a1", 3), ("6523a2", 1), ("6525e", 1), ("6525r", 1), ("6524r", 1)]
    data = [{"B": g, "D": d} for g, d in eight]
    data[0].update({"A": 1, "C": "Texniki xarici dil (rus dili)", "F": 60, "H": 1, "J": 4})
    data += [{"A": 2, "B": "6524a1", "C": "Alqoritmlər", "D": 25, "G": 15}, {"B": "6524a2", "D": 24, "G": 15}, {"B": "6524a3", "D": 26, "G": 15},
             {"A": 3, "B": "6526e 1", "C": "Fizika", "D": 30, "U": 15}, {"B": "6526e 2", "D": 31, "U": 15}, {"B": "6526e 3", "D": 8, "U": 15},
             {"A": 4, "B": "6524a4", "C": "Fizika", "D": 20}, {"AJ": "Anar"}]
    totals.append(block_a(sh, totals[-1] + 2, "0,5 ştat əvəzçi - baş müəllim, Həsənova Leyla Akifovna", data,
                          merges=[("C", 0, 7), ("F", 0, 7), ("H", 0, 7), ("J", 0, 7), ("C", 8, 10), ("E", 8, 10), ("C", 11, 13)],
                          titles=("payız semestri", _year_a(), DEPARTMENT_A), damaged={"F": "kafedra@example.az"}, row_total_merge=(0, 7)))
    sh.hidden.add(totals[-1] - 1)                              # the row that holds only a name at the right (G4)
    # 3: a vacancy (A10): an item number alone, an İFS: prefix, a teaching row without a student count (G8)
    totals.append(block_a(sh, totals[-1] + 3, "Vakansiya", [
        {"A": 1},
        {"A": 2, "B": "6525e", "C": "İFS: Siqnalların emalı", "D": 20, "S": 30, "U": 15, "V": 1, "W": 5, "X": 6.66},
        {"A": 3, "B": "6525r", "C": "Siqnalların emalı", "U": 15},
        {"A": 4, "C": "TD-20 10.10.2024 Uydurmayeva Aysel (Elmi rəhbər: Quliyev Elçin Rauf oğlu)", "AF": 80},
    ], total_label="Cəm"))
    # 4: an hourly block written without the space (A9); a load row with no subject outside any merge (R2): blocked
    totals.append(block_a(sh, totals[-1] + 2, "saathesabı assistent  Məmmədov Tural", [
        {"A": 1, "B": "6524r", "C": "Elektronika", "D": 12, "F": 30, "G": 15},
        {"A": 2, "B": "6523a2", "D": 26, "AA": 40},
    ]))
    # 5: an hourly block with the space and a dash; 20 hours is not a multiple of 15
    totals.append(block_a(sh, totals[-1] + 2, "saat hesabı - müəllim, Əliyeva Nigar Samir qızı", [
        {"A": 1, "B": "6525e", "C": "Elektronika", "D": 20, "F": 30},
        {"A": 2, "B": "6525r", "C": "Elektronika", "D": 15, "T": 20},
    ]))
    for col in (*A_AUTUMN, "R", *A_SPRING, "AG", "AH"):       # the department totals (T6); one of them is stale
        sh.put(col, 3, _sum(sh, [col], totals))
    sh.put("C", 3, sh.get("AH", 3))
    sh.put("H", 3, sh.get("H", 3) + 7)
    other = Cells("verdiyim")                                   # form content of another year, in no total (A11)
    block_a(other, 1, "Vakansiya", [{"B": "M656a", "C": "Rəqəmsal siqnal emalı", "D": 10, "E": 30, "F": 15, "H": 1, "I": 5, "J": 3.3}],
            titles=(UNIVERSITY, _year_a("2025/26"), DEPARTMENT_A), total_label="Cəm")
    empty = Cells("saat hesabı Payız")                          # a template with merges and no value (G3)
    empty.merges += ["A1:AI1", "A2:S2"]
    summary = Cells("Arayış cədvəl")
    summary.row(1, {"A": "№", "B": "Soyadı, adı və atasının adı", "F": "Elmi dərəcəsi, vəzifəsi", "G": "Ümumi dərs yükü (saat)",
                    "H": "Aud,", "I": "Aud,", "J": "Qeyd", "M": "Uydurmayev Anar Samir oğlu"})
    summary.row(2, {"H": "yükü,", "I": "yükü,", "M": "Uydurmayeva Aysel Anar qızı"})
    summary.row(3, {"H": "(saat)", "I": "(%)"})

    def person(row: int, n: int, name: str, title: str, total_row: int, contact: float):
        summary.row(row, {"A": str(n), "B": name, "F": title, "G": F(f"'Forma №3'!$AH${total_row}", sh.get("AH", total_row)),
                          "H": contact})

    summary.put("B", 4, "Ştatda olan professor-müəllim heyəti")
    person(5, 1, "Quliyev Elçin Rauf oğlu", "t.ü.f.d., dosent", totals[0], 105 + 80)
    summary.row(6, {"A": "Cəmi:", "G": sh.get("AH", totals[0])})
    summary.put("A", 7, "0,5  ştat kənar əvəzçiliklə")
    person(8, 1, "Həsənova Leyla Akifovna", "müəllim", totals[1], 150)
    summary.put("A", 9, "Saat hesabı")
    person(10, 1, "Məmmədov Tural", "assistent", totals[3], 45)
    person(11, 2, "Əliyeva Nigar Samir qızı", "müəllim", totals[4], 50)
    summary.put("A", 12, "Vakant qalan yük")
    summary.row(13, {"A": "1", "B": "Bakalavr", "G": sh.get("AH", totals[2]), "H": 60})
    summary.row(14, {"A": "CƏMİ:", "G": round(sh.get("AH", totals[2]), 2) + 0.01, "H": 60 + 80})      # typed, within the tolerance (K6)
    listing = Cells("Лист2")
    listing.row(1, {"A": "№", "B": "Soyadı, adı, atasının adı", "C": "Ştat vahidi", "D": "İş yeri", "E": "Tədris yükü (saat)"})
    listing.row(2, {"A": "1", "B": "Quliyev Elçin Rauf oğlu", "C": "1 ştat dosent", "D": "Əsas iş yeri", "E": sh.get("AH", totals[0])})
    return xlsx([sh, other, empty, summary, listing])


# ---------------------------------------------------------------- layout B (docs/forms/forma-3.md, B1–B9)
B_LOAD = ["Məsləhət", "Məqbul", "İmtahan", "İmtahan suallarının hazırlanması", "Kurs layihəsi (işi)", "Referat (magistraturada)",
          "Magistr dissertasiyasına rəhbərlik", "Magistr dissertasiyasına məsləhət", "{x}", "Təcrübəyə rəhbərlik", "Doktorantura",
          "DAK / İEŞ", "Buraxılış işi", "Müəllimlərin dərsi. iştirakı", "Digər dərs yükü"]
B_ROW8 = (["Mühazirə", "Məşğələ, seminar", "Laboratoriya", *[t.replace("{x}", "Tədqiqat işinin aparılması") for t in B_LOAD], "Cəmi", ""]
          + ["Mühazirə", "Məşğələ, seminar", "Laboratoriya", *[t.replace("{x}", "Layihələrin idarə olunması") for t in B_LOAD], "Cəmi"])
B_AUTUMN = [_col(i) for i in range(5, 23)]                     # F..W
B_SPRING = [_col(i) for i in range(25, 43)]                    # Z..AQ
AT_TITLE = "Digər dərs yüklərini aparan müəllimlər"
AT_TYPO = "Digər dərs yülərini aparan müəllimlər "             # as 41 of the real sheets spell it (H7)


def sheet_b(name: str, teacher: str, sections: list[dict], year: str = "2026/2027", state: str = "visible",
            at_title: str = AT_TITLE) -> Cells:
    """A teacher's sheet: title rows 1–5, the header band 7–8 (kind names in row 8), the column numbers in row 9,
    then sections. A section: ``label``, ``data`` (rows), ``merges`` (column, first, last), ``total`` ("labelled",
    "unlabelled"), ``ratio`` ("aktiv", "bare", None), ``gap`` (blank rows before the total), ``errors`` (total cells that
    hold #REF!), ``blank`` (zero total cells left empty)."""
    sh = Cells(name, state)
    sh.row(1, {"B": "Azərbaycan Respublikası Elm və Təhsil Nazirliyi", "AR": "FORMA №3"})
    sh.row(2, {"G": '"Nümunə riyaziyyat"', "AM": "kafedrasının"})
    sh.put("B", 3, "Azərbaycan Texniki        Universiteti")
    sh.row(4, {"E": teacher, "AE": f"{year}-ci tədris ili üçün"})
    sh.put("U", 5, "AKADEMİK  YÜKÜ")
    sh.merges += ["AR1:AT1", "B1:B2", "G2:AL2", "AM2:AQ2", "B3:B5", "E4:AB4", "AE4:AR4", "U5:AA5"]
    sh.row(7, {"A": "SIRA NÖMRƏSİ", "B": "FƏNNİN ADI", "C": "QRUP №-si", "D": "Tələbələrin sayı", "E": "Birləşmənin işarəsi",
               "F": "PAYIZ SEMESTRİ", "Z": "YAZ SEMESTRİ", "AS": "İL ƏRZİNDƏ CƏMİ", "AT": at_title})
    for i, title in enumerate(B_ROW8):
        sh.put(_col(5 + i), 8, title)
    for i in range(46):
        sh.put(_col(i), 9, str(i + 1))
    sh.merges += ["A7:A8", "B7:B8", "C7:C8", "D7:D8", "E7:E8", "F7:X7", "Z7:AR7", "AS7:AS8", "AT7:AT8"]
    r = 10
    for sec in sections:
        sh.put("B", r, sec["label"])
        sh.merge("B", r, "AS")
        first = r + 1
        for i, row in enumerate(sec["data"]):
            sh.row(first + i, row)
        for col, i, j in sec.get("merges", ()):
            sh.merge(col, first + i, col, first + j)
        last = first + len(sec["data"])
        for rr in range(first, last):
            if sh.get("B", rr) is None and sh.get("C", rr) is None:
                continue
            aut, spr = _sum(sh, B_AUTUMN, [rr]), _sum(sh, B_SPRING, [rr])
            sh.row(rr, {"X": aut or None, "AR": spr or 0, "AS": aut + spr})
        total = last + sec.get("gap", 0)
        if sec.get("total", "labelled") == "labelled":
            sh.put("B", total, "CƏMİ")
            sh.merge("B", total, "C")
        for col in (*B_AUTUMN, *B_SPRING):
            value = _sum(sh, [col], range(first, last))
            if col in sec.get("errors", ()):
                sh.put(col, total, "#REF!")
            elif value or col not in sec.get("blank", ()):
                sh.put(col, total, value or 0)
        aut, spr = _sum(sh, B_AUTUMN, range(first, last)), _sum(sh, B_SPRING, range(first, last))
        broken = bool(sec.get("errors"))
        sh.row(total, {"X": aut or 0, "AR": "#REF!" if broken else spr or 0, "AS": "#REF!" if broken else aut + spr})
        r = total + 1
        if sec.get("ratio") == "aktiv":
            sh.row(r, {"AR": "Aktiv ", "AS": 0.63})
            r += 1
        elif sec.get("ratio") == "bare":
            sh.put("AS", r, 0.83)
            r += 1
    sh.row(r + 3, {"C": "Nümunə riyaziyyat kafedrasının müdiri", "AM": "Uydurmayev Anar"})
    sh.merge("C", r + 3, "AC")
    return sh


def forma3_sheets() -> bytes:
    hasanova = "baş müəllim Həsənova Leyla Akif qızı"
    quliyev = "t.ü.f.d., dosent Quliyev Elçin Rauf oğlu"
    first = sheet_b("Quliyev E.R.", "t.ü.f.d., dosent Quliyev Elçin Rauf oğlunun", [
        # a lecture stream of 6526e 1/2/3 (three groups, not subgroups), a joint seminar of two, a merged exam-paper cell
        {"label": "1 ŞTAT", "ratio": "aktiv", "blank": ("M", "AG"), "data": [
            {"B": "Riyazi analiz-1", "C": "6526e 1", "D": 30, "F": 30, "G": 30, "I": 1, "K": 10, "L": 5, "AT": hasanova},
            {"C": "6526e 2", "D": 31, "I": 1, "K": 10.333333333333334},
            {"C": "6526e 3", "D": 8, "G": 30, "I": 1, "K": 2.6666666666666665},
            {"B": "Riyazi analiz - 2", "C": "6526e 1", "D": 30, "Z": 30, "AA": 15, "AC": 1, "AE": 10, "AF": 5},
            {"B": "MD rəhbərlik ", "D": 2, "AI": 50},
            {"B": "Elmi pedaqoji təcrübə ", "D": 3, "AL": 30},
        ], "merges": [("B", 0, 2), ("F", 0, 2), ("G", 0, 1), ("L", 0, 2), ("AT", 0, 2)]},
        {"label": "0,5 ştat daxili əvəzçi", "ratio": "bare", "data": [                 # a second post (B4)
            {"B": "Xətti cəbr", "C": "6525a", "D": 25, "F": 30, "I": 1, "K": 8.333333333333334, "L": 5}]},
        {"label": "SAAT HESABI ", "data": [                                            # an hourly sub-section (P2)
            {"B": "Xətti cəbr", "C": "6524r", "D": 12, "G": 30},
            {"B": "Xətti cəbr", "C": "M656a", "D": 10, "G": 15}]},
    ], at_title=AT_TYPO)
    second = sheet_b("Həsənova L.A.", "baş müəllim Həsənova Leyla Akif qızının", [
        # labs of the stream above under an empty lecture merge (J3); the same subject written again is another class (R4);
        # an unlabelled total directly above the ratio row (B5)
        {"label": "Əsas iş yeri üzrə 0,5 ŞTAT", "total": "unlabelled", "ratio": "aktiv", "data": [
            {"B": "Riyazi analiz-1", "C": "6526e 1", "D": 30, "H": 15, "AT": quliyev},
            {"C": "6526e 2", "D": 31, "H": 15},
            {"C": "6526e 3", "D": 8, "H": 15},
            {"B": "Fizika-1", "C": "6525a", "D": 25, "F": 30, "G": 15, "I": 1, "K": 8.333333333333334, "L": 5},
            {"B": "Fizika-1", "C": "6524r", "D": 12, "F": 30},
            {"B": "Fizika-1", "C": "6524r", "D": 12, "F": 15},
        ], "merges": [("B", 0, 2), ("F", 0, 2), ("AT", 0, 2)]},
        {"label": "Saathesabı ", "gap": 1, "data": []},                                # an empty section, a blank row before CƏMİ
    ])
    third = sheet_b("Kərimov R. (sabah)", "müəllim Kərimov Rəşad", [                  # a whole hourly sheet; #REF! totals (K1)
        {"label": "Saat hesabı", "errors": ("AN", "AO"), "data": [
            {"B": "Big data", "C": "M656a", "D": 10, "Y": 30, "AA": 30, "AC": 1, "AE": 3.3333333333333335, "AF": 5},
            {"B": "Big data", "C": "M666a", "D": 12, "AA": 30, "AC": 1, "AE": 4}]}])
    vacancy = sheet_b("Vakansiya", "VAKANSİYA (Bakalavr)  ", [                         # the area is the label (P3)
        {"label": "RİYAZİYYAT", "data": [
            {"B": "Diskret riyaziyyat", "C": "6325r", "D": 20, "Z": 30, "AA": 30, "AC": 1, "AE": 6.666666666666667, "AF": 5}]}])
    vacancy2 = sheet_b("Vakansiya_1", "Vakansiya_1 magistr", [                         # hourly vacancy: the area is in E4
        {"label": "saathesabı ", "data": [{"B": "Ədədi üsullar", "C": "M656a", "D": 10, "F": 30}]}])
    broken = sheet_b("Əliyeva N.S.", "assisten Əliyeva Nigar Samir qızının", [
        {"label": "0.5  ŞTAT", "data": [                                               # a row without a group (R5), one without a subject (R2)
            {"B": "Calculus II", "D": 10, "Z": 60, "AF": 5},
            {"C": "6524r", "D": 12, "AA": 15}]},
        {"label": "Saat hesabı", "data": [{"B": "Ehtimal nəzəriyyəsi", "C": "6525a", "D": 25, "G": 30}]}])
    hidden = sheet_b("Məmmədov T.", "Məmmədov Tural Vaqif oğlunun", [                  # hidden, another year: listed only (G4)
        {"label": "0,5 ŞTAT ", "data": [{"B": "Xətti cəbr", "C": "6525a", "D": 25, "F": 30, "G": 15}]}], year="2025/2026", state="hidden")
    stranger = sheet_b("Naməlum N.N.", "müəllim Naməlum Nazim Nadir oğlunun", [       # a teacher the registry does not hold
        {"label": "1 Ştat", "data": [{"B": "Fizika-1", "C": "6526e 1", "D": 30, "H": 15}]}])
    return xlsx([first, second, third, vacancy, vacancy2, broken, hidden, stranger])


# ---------------------------------------------------------------- users
GIVEN = ["Aydan", "Elvin", "Leyla", "Murad", "Nigar", "Orxan", "Sevinc", "Tural", "Ülviyyə", "Kənan"]
FAMILY = ["Abbasov", "Babayeva", "Cəfərov", "Dadaşova", "Əsgərov", "Fərzəliyeva", "Hüseynov", "İsmayılova", "Kərimov", "Lətifova"]


def users_10k() -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["sourcedId", "username", "givenName", "familyName", "role", "identifier", "group"])
    for i in range(10_000):
        w.writerow([f"u{i:05d}", f"s{i:05d}", GIVEN[i % 10], FAMILY[(i // 10) % 10], "student", f"T-{i:05d}",
                    ("İT-25-1", "İT-25-2", "KM-25-1")[i % 3]])
    return out.getvalue()


# ---------------------------------------------------------------- an old system's exports (Task 38, content/mappings/sample-sis.json)
# Students ETL-S1..ETL-S6 of group ETL-1, class ETL-K1 of course ETL-C1, course ETL-C2 (no lesson records), the term
# T-2026: tests/migration/test_etl.py builds them. The cut-over (--as-of) is 2026-11-10; the lessons are 2–6 November.
ETL_MARKS = {"ETL-S1": "iiqii", "ETL-S2": "iiiii", "ETL-S3": "qqüii", "ETL-S4": "igiiq", "ETL-S5": "iiiüi", "ETL-S6": "qiiii"}


def _csv(rows: list[list]) -> str:
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(rows)
    return out.getvalue()


def attendance_lessons() -> str:
    """Lesson-level records in the old system's own shape: a class code, a student code, DD.MM.YYYY, one letter a mark,
    and a teacher column Zəka does not take."""
    rows: list[list] = [["Vahid", "Tələbə", "Tarix", "Başlama", "Saat", "Qeyd", "Müəllim"]]
    for sid, marks in ETL_MARKS.items():
        for day, mark in zip((2, 3, 4, 5, 6), marks, strict=True):
            rows.append(["ETL-K1", sid, f"{day:02d}.11.2026", "09:00", 2, mark, "Ə. Uydurmaov"])
    return _csv(rows)


def attendance_opening() -> str:
    """Totals per student and course up to the cut-over: the form of an old system that keeps no lesson records."""
    rows: list[list] = [["Semestr", "Fənn", "Tələbə", "Keçilmiş saat", "Üzrsüz", "Üzrlü"]]
    rows += [["T-2026", "ETL-C2", sid, 20, i % 3 * 2, i % 2 * 2] for i, sid in enumerate(ETL_MARKS)]
    return _csv(rows)


def etl_grades() -> str:
    """Scores on the old system's 100-point scale for a component worth 10 in Zəka."""
    rows: list[list] = [["Fənn", "Tələbə", "Komponent", "Bal (100)"]]
    rows += [["ETL-C1", sid, "Kollokvium 1", 50 + 8 * i] for i, sid in enumerate(ETL_MARKS)]
    return _csv(rows)


def status_events() -> str:
    """Two orders: a leave from 12 November (given on 9 November, before the export), and an admission the dean's office
    already entered in Zəka."""
    return _csv([["Tələbə", "Növ", "Əmr №", "Əmr tarixi", "Qüvvəyə minmə tarixi", "Qrup"],
                 ["ETL-S6", "Akademik məzuniyyət", "ETL-77/AM", "09.11.2026", "12.11.2026", ""],
                 ["ETL-S5", "Qəbul", "ETL-25/Q", "25.08.2025", "01.09.2025", ""]])


def main():
    (HERE / "forma3_blocks.xlsx").write_bytes(forma3_blocks())
    (HERE / "forma3_sheets.xlsx").write_bytes(forma3_sheets())
    (HERE / "users_10k.csv").write_text(users_10k(), encoding="utf-8")
    for name, text in (("attendance_lessons.csv", attendance_lessons()), ("attendance_opening.csv", attendance_opening()),
                       ("grades.csv", etl_grades()), ("status_events.csv", status_events())):
        (HERE / name).write_text(text, encoding="utf-8")
    print("written:", ", ".join(p.name for p in sorted(HERE.glob("*.*")) if p.suffix in (".xlsx", ".csv")))


if __name__ == "__main__":
    main()
