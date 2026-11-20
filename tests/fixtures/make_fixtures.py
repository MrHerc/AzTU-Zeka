"""Writes the synthetic import fixtures (tasks/todo.md, Task 16). Every name is made up; the real Forma №3 files the
owner gave (staff names, degrees, posts) never enter the repository. Run: python tests/fixtures/make_fixtures.py

forma3_blocks.xlsx   layout A: one sheet of teacher blocks, plus a "saat hesabı" sheet that must be skipped
forma3_sheets.xlsx   layout B: a sheet per teacher (name in E4), a second teacher, a SAAT HESABI section, an unknown teacher
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


def _sheet_xml(rows: list[list], merges: list[str]) -> str:
    out = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{MAIN}"><sheetData>']
    for r, row in enumerate(rows):
        cells = []
        for c, v in enumerate(row):
            if v in ("", None):
                continue
            ref = f"{_col(c)}{r + 1}"
            if isinstance(v, (int, float)):
                cells.append(f'<c r="{ref}"><v>{v}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>')
        out.append(f'<row r="{r + 1}">{"".join(cells)}</row>')
    out.append("</sheetData>")
    if merges:
        out.append(f'<mergeCells count="{len(merges)}">' + "".join(f'<mergeCell ref="{m}"/>' for m in merges) + "</mergeCells>")
    out.append("</worksheet>")
    return "".join(out)


def xlsx(sheets: list[tuple[str, list[list], list[str]]]) -> bytes:
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
                           + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>' for i, (n, _, _) in enumerate(sheets))
                           + "</sheets></workbook>",
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                      + "".join(f'<Relationship Id="rId{i + 1}" Type="{RELS}/worksheet" Target="worksheets/sheet{i + 1}.xml"/>'
                                                for i in range(len(sheets))) + "</Relationships>",
    }
    for i, (_, rows, merges) in enumerate(sheets):
        files[f"xl/worksheets/sheet{i + 1}.xml"] = _sheet_xml(rows, merges)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(zipfile.ZipInfo(name, STAMP), text)
    return buf.getvalue()


# ---------------------------------------------------------------- layout A
HOURS_A = ["Mühazirə", "Məşğələ", "Laboratoriya", "İmtahan", "Cəmi"]


def block_a(teacher_line: str, rows: list[list]) -> list[list]:
    """A teacher block: the teacher line, the semester row, the header, the column numbers, the rows, the total."""
    head = ["Sıra sayı", "Qruplar", "Fənlər", "Tələbələrin sayı", *HOURS_A, *HOURS_A, "İl ərzində cəmi"]
    return [[teacher_line], ["", "", "", "", "payız semestri", "", "", "", "", "yaz semestri"], head,
            [str(i + 1) for i in range(len(head))], *rows, ["", "Cəmi", "", "", 90, 45, 60]]


def forma3_blocks() -> bytes:
    #           seq  group     subject                students  payız: L   S   Lab  Ex      Σ   yaz: L   S   Lab Ex  Σ
    quliyev = [[1, "651a", "Alqoritmlər", 25, 30, 15, "", 3.3333333333, 48.33, "", "", "", "", ""],
               ["", "652a", "", 24, "", 15, "", 3.2, 18.2],
               ["", "653a 1", "", 12, "", "", 15, 1.6, 16.6],
               ["", "653a 2", "", 12, "", "", 15, 1.6, 16.6],
               [2, "651a", "Verilənlər bazaları", 25, "", "", "", "", "", 30, 15, "", 3.33, 48.33]]
    hasanova = [[1, "651a", "Fizika", 25, "", "", 30, "", 30],
                ["", "", "Dissertasiya rəhbərliyi", "", "", "", "", "", ""]]
    rows: list[list] = [["AzTU · RT kafedrası · 2026/2027-ci tədris ilinin akademik yükü (uydurma nümunə)"], []]
    merges = []
    for line, data in (("1,0 ştat - t.ü.f.d., dosent, Quliyev Elçin Rauf oğlu", quliyev),
                       ("0,5 ştat - baş müəllim, Həsənova Leyla Akif qızı", hasanova)):
        top = len(rows) + 2                                    # 1-based row of the semester labels
        merges += [f"E{top}:I{top}", f"J{top}:N{top}"]
        rows += block_a(line, data) + [[]]
    hourly = [["Saat hesabı · payız"], ["Sıra sayı", "Qruplar", "Fənlər", "Tələbələrin sayı", "Mühazirə"],
              [1, "651a", "Alqoritmlər", 25, 99]]
    return xlsx([("RT kafedrası", rows, merges), ("saat hesabı Payız", hourly, []), ("Arayış cədvəl", [["Arayış"]], [])])


# ---------------------------------------------------------------- layout B
HOURS_B = ["Mühazirə", "Məşğələ, seminar", "Laboratoriya", "Cəmi"]


def sheet_b(name: str, e4: str, data: list[list], hourly: bool = False) -> tuple[str, list[list], list[str]]:
    head = ["SIRA NÖMRƏSİ", "FƏNNİN ADI", "QRUP №-si", "Tələbələrin sayı", "Birləşmənin işarəsi", *HOURS_B, *HOURS_B,
            "İL ƏRZİNDƏ CƏMİ", "Digər dərs yüklərini aparan müəllimlər"]
    rows: list[list] = [["AzTU · MR kafedrası (uydurma nümunə)"], [], [], ["", "", "", "", e4], [],
                        ["", "", "", "", "", "PAYIZ SEMESTRİ", "", "", "", "YAZ SEMESTRİ", "", "", "", "İL ƏRZİNDƏ CƏMİ"],
                        head, [str(i + 1) for i in range(len(head))], *data, ["", "CƏMİ", "", "", "", 60, 30, 30]]
    if hourly:
        rows += [[], ["", "SAAT HESABI"], [1, "Alqoritmlər", "654a", 20, "", 30, 15]]
    return name, rows, ["F6:I6", "J6:M6"]


def forma3_sheets() -> bytes:
    #          seq  subject        group    students mark payız: L   S   Lab  Σ    yaz: L  S  Lab Σ   year  other teacher
    quliyev = [[1, "Alqoritmlər", "651a", 25, "*", 30, 15, "", 45, "", "", "", "", 45],
               ["", "", "652a", 24, "*", "", 15, "", 15, "", "", "", "", 15, "baş müəllim Həsənova Leyla Akif qızı"],
               ["", "", "653a 1", 12, "*", "", "", 15, 15],
               ["", "", "653a 2", 12, "*", "", "", 15, 15],
               [2, "Verilənlər bazaları", "651a", 25, "", "", "", "", "", 30, 15, "", 45, 45]]
    hasanova = [[1, "Fizika", "651a", 25, "", "", "", 30, 30]]
    stranger = [[1, "Fizika", "652a", 24, "", "", "", 30, 30]]
    return xlsx([sheet_b("Quliyev E.R.", "t.ü.f.d., dosent Quliyev Elçin Rauf oğlu", quliyev, hourly=True),
                 sheet_b("Həsənova L.A.", "baş müəllim Həsənova Leyla Akif qızı", hasanova),
                 sheet_b("Naməlum N.N.", "müəllim Naməlum Nazim Nadir oğlu", stranger)])


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
