"""Forma №3 as departments fill it (tasks/todo.md, Task 47; rule ids: docs/forms/forma-3.md). The grammars, each reading
rule on a synthetic sheet, and the golden counts of the two fixtures (tests/fixtures/make_fixtures.py). No real file,
name or cell text of a department is here."""
import copy
import json
import random
from collections import Counter
from pathlib import Path

import pytest

from tests.fixtures import make_fixtures as mk
from zeka.modules.integration import forma3, tables
from zeka.modules.integration import forma3_text as tx

FIX = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="module")
def sheets_a():
    return tables.xlsx_sheets((FIX / "forma3_blocks.xlsx").read_bytes())


@pytest.fixture(scope="module")
def sheets_b():
    return tables.xlsx_sheets((FIX / "forma3_sheets.xlsx").read_bytes())


@pytest.fixture(scope="module")
def form_a(sheets_a):
    return forma3.read(sheets_a)


@pytest.fixture(scope="module")
def form_b(sheets_b):
    return forma3.read(sheets_b)


def at(ref: str) -> tuple[int, int, int]:
    """``#0!F24`` -> (sheet, row, column), 0-based."""
    sheet, cell = ref[1:].split("!")
    letters = "".join(ch for ch in cell if ch.isalpha())
    return int(sheet), int(cell[len(letters):]) - 1, mk._num(letters)


def changed(sheets, **cells):
    """A copy of the sheets with cells set: ``changed(sheets, **{"#0!F24": "x"})``."""
    out = copy.deepcopy(sheets)
    for ref, value in cells.items():
        s, r, c = at(ref)
        while len(out[s].rows) <= r:
            out[s].rows.append([""] * len(out[s].rows[0]))
        out[s].rows[r][c] = value
    return out


def post(form, ref):
    return next(p for p in form.posts if p.ref == ref)


def unit(form, anchor):
    return next(u for u in form.units if u.anchor == anchor)


def codes(items, **where):
    return [x for x in items if all(getattr(x, k) == v for k, v in where.items())]


# ---------------------------------------------------------------- the grammars
@pytest.mark.parametrize("line, fraction, employment, kind, degree, position, name", [
    ("0,5 ştat - t.e.d., professor, Quliyev Elçin Rauf oğlu", 0.5, None, "staff", "t.e.d.", "professor", "Quliyev Elçin Rauf oğlu"),
    ("0,5 ştat əvəzçi - doktorant, Həsənova Leyla Akif qızı", 0.5, "substitute-unspecified", "staff", None, "doktorant", "Həsənova Leyla Akif qızı"),
    ("0,5 ştat kənar doktorant -Kərimov Rəşad Samir oğlu", 0.5, "external", "staff", None, "kənar doktorant", "Kərimov Rəşad Samir oğlu"),
    ("0,5 ştat Kərimov Rəşad Samir oğlu", 0.5, None, "staff", None, None, "Kərimov Rəşad Samir oğlu"),
    ("0.5 ştat - baş müəllim, Əliyeva Nigar Samir qızı", 0.5, None, "staff", None, "baş müəllim", "Əliyeva Nigar Samir qızı"),
    ("1 ştat - f.ü.f.d., dosent Kərimov Rəşad Samir oğlu", 1.0, None, "staff", "f.ü.f.d.", "dosent", "Kərimov Rəşad Samir oğlu"),
    ("1 ştat - f.-r.e.n., dosent, Kərimov Rəşad Samir oğlu", 1.0, None, "staff", "f.-r.e.n.", "dosent", "Kərimov Rəşad Samir oğlu"),
    ("0.5 ştat əvəzçi t.ü.f.d dos, Kərimov Rəşad Samir oğlu", 0.5, "substitute-unspecified", "staff", "t.ü.f.d", "dos", "Kərimov Rəşad Samir oğlu"),
    ("0,5 ştat kənar  - t.ü.f.d, dosent, Kərimov Rəşad Samir oğlu", 0.5, "external", "staff", "t.ü.f.d", "dosent", "Kərimov Rəşad Samir oğlu"),
    ("0,5 ştat daxili əvəzçi - müəllim, Kərimov Rəşad Samir oğlu", 0.5, "internal", "staff", None, "müəllim", "Kərimov Rəşad Samir oğlu"),
    ("saathesabı assistent  Məmmədov Tural Vaqif oğlu", None, None, "hourly", None, "assistent", "Məmmədov Tural Vaqif oğlu"),
    ("saat hesabı t.e.n., dos Məmmədov Tural vaqif oğlu", None, None, "hourly", "t.e.n.", "dos", "Məmmədov Tural Vaqif oğlu"),
    ("saat hesabı - müəllim, Əliyeva Nigar Samir qızı", None, None, "hourly", None, "müəllim", "Əliyeva Nigar Samir qızı"),
    ("1 ştat - t.e.d., məsləhətçi professor, Quliyev Elçin Rauf oğlu", 1.0, None, "staff", "t.e.d.", "məsləhətçi professor", "Quliyev Elçin Rauf oğlu"),
])
def test_a6_the_staff_line_grammar_reads_every_observed_form(line, fraction, employment, kind, degree, position, name):
    st = tx.staff(line)
    who = tx.person(st.rest)
    assert (st.kind, st.fraction, st.employment) == (kind, fraction, employment)
    assert (who.ok, who.degree, who.position, who.name) == (True, degree, position, name)


def test_a6_a_name_without_oglu_or_qizi_is_valid_and_only_flagged():
    russian = tx.person(tx.staff("1 ştat - baş müəllim, Həsənova Leyla Akifovna").rest)
    assert russian.ok and russian.name == "Həsənova Leyla Akifovna" and russian.flags == ["russian_patronymic"]
    short = tx.person("müəllim Kərimov Rəşad")
    assert short.ok and short.name == "Kərimov Rəşad" and short.flags == ["no_patronymic"]


@pytest.mark.parametrize("line", ["", "Kafedranın yükü", "ştat", "1 ştat - dosent", "1 ştat - dosent, Quliyev", "1 ştat - Bir İki Üç Dörd Beş"])
def test_a6_a_staff_line_the_grammar_cannot_read_is_not_guessed(line):
    st = tx.staff(line)
    assert st.kind == "unknown" or not tx.person(st.rest).ok


def test_a10_b2_a_vacancy_is_a_prefix_test_and_keeps_its_area():
    assert tx.staff("Vakansiya").kind == "vacancy" and tx.staff("Vakansiya").area is None
    assert tx.staff("VAKANSİYA (Bakalavr)  ").area == "Bakalavr"
    assert tx.staff("Vakansiya (proqramlaşdırma)").area == "proqramlaşdırma"
    assert tx.staff("Vakansiya_1 magistr").kind == "vacancy" and tx.staff("Vakansiya_1 magistr").area == "1 magistr"


@pytest.mark.parametrize("e4, degree, position, name, flags", [
    ("t.ü.f.d., dosent Quliyev Elçin Rauf oğlunun", "t.ü.f.d.", "dosent", "Quliyev Elçin Rauf oğlu", []),
    ("baş müəllim Həsənova Leyla Akif qızının", None, "baş müəllim", "Həsənova Leyla Akif qızı", []),
    ("Həsənova Leyla Akif qıznın", None, None, "Həsənova Leyla Akif qızı", []),                    # the genitive typo
    ("assistent Həsənova Leyla Akif qızı", None, "assistent", "Həsənova Leyla Akif qızı", []),     # already nominative
    ("f.-r.e.n., dosent Həsənova LeylaAkif qıznın", "f.-r.e.n.", "dosent", "Həsənova Leyla Akif qızı", []),   # two words glued
    ("t.e.n.,dosent Quliyev Elçin rauf oğlunun", "t.e.n.", "dosent", "Quliyev Elçin Rauf oğlu", []),   # no space, lower-case patronymic
    ("assisten Əliyeva Nigar Samir qızının", None, "assisten", "Əliyeva Nigar Samir qızı", []),
    ("f.r.e.n., fəxri professor  Quliyev Elçin Rauf oğlunun", "f.r.e.n.", "fəxri professor", "Quliyev Elçin Rauf oğlu", []),
    ("müəllim Kərimov Rəşad", None, "müəllim", "Kərimov Rəşad", ["no_patronymic"]),
])
def test_b2_the_teacher_cell_gives_a_nominative_name(e4, degree, position, name, flags):
    who = tx.person(e4)
    assert (who.ok, who.degree, who.position, who.name, who.flags) == (True, degree, position, name, flags)


def test_b2_a_bracketed_suffix_after_a_person_is_kept_apart():
    who = tx.person("Kərimov Rəşad (sabah qrupları) ")
    assert who.name == "Kərimov Rəşad" and who.suffix == "sabah qrupları"


@pytest.mark.parametrize("label, kind, fraction, employment", [
    ("1 ŞTAT", "staff", 1.0, None), ("1 Ştat", "staff", 1.0, None), ("0.5 ştat ", "staff", 0.5, None), ("0.5  ŞTAT", "staff", 0.5, None),
    ("0,5 ŞTAT kənar əvəzçi", "staff", 0.5, "external"), ("0,5 ŞTAT KƏNAR ƏVƏZÇİ", "staff", 0.5, "external"),
    ("0,5 ştat daxili əvəzçi", "staff", 0.5, "internal"), ("0.5 ŞTAT  daxili əvəzçi", "staff", 0.5, "internal"),
    ("Əsas iş yeri üzrə 0,5 ŞTAT", "staff", 0.5, "main"), ("ƏSAS İŞ YERİ ÜZRƏ 0,5 ŞTAT", "staff", 0.5, "main"),
    ("Əsas is yeri üzrə 0.5 ştat", "staff", 0.5, "main"),                                           # the typo "is"
    ("Saat hesabı", "hourly", None, None), ("SAAT HESABI ", "hourly", None, None), ("Saathesabı ", "hourly", None, None),
    ("SAATHESABI", "hourly", None, None), ("saathesabı ", "hourly", None, None),
    ("RİYAZİYYAT", "unknown", None, None),
])
def test_b3_the_section_label_grammar(label, kind, fraction, employment):
    st = tx.staff(label)
    assert (st.kind, st.fraction, st.employment) == (kind, fraction, employment)


def test_g7_a_group_code_has_no_subgroup_and_no_whitespace():
    assert [tx.group_code(x) for x in ("6526e 1", "6526e 2", "6126 e", "5126ax ", "M686aS ")] == ["6526e1", "6526e2", "6126e", "5126ax", "M686aS"]


@pytest.mark.parametrize("code, wrong", [
    ("6526e1", False), ("6524r", False), ("M656aS", False), ("M536a", False), ("6126e", False), ("6525dd", False),
    ("26123a", True),            # five digits
    ("616r", True),              # three digits
    ("2612a", True),             # intake year 12
    ("2682a", True), ("VB(b)a26-27y", True), ("6527a", True),
])
def test_g7_a_code_that_looks_wrong_is_told_by_the_grammar_and_the_intake_year(code, wrong):
    assert tx.code_looks_wrong(code, 2026) is wrong


def test_g6_subject_keys_fold_spelling_and_the_core_drops_prefixes_only_for_linking():
    assert len({tx.subject_key(x) for x in ("Riyazi analiz-1", "Riyazi analiz - 1", "Riyazi analiz -1", "Riyazi analiz– 1", "RIYAZI ANALİZ-1")}) == 1
    assert tx.subject_key("Riyazi analiz-1") != tx.subject_key("Riyazi analiz-2")
    core = tx.subject_core("Siqnalların emalı")
    for text in ("İFS: Siqnalların emalı", "IFS: Siqnalların emalı", "İFS Siqnalların emalı", "İFS-2024y: Siqnalların emalı",
                 "s/f. Siqnalların emalı", "RME.3--Siqnalların emalı", "Siqnalların emalı (Signal Processing)",
                 "Siqnalların emalı — Python, MATLAB, Simulink"):
        assert tx.subject_core(text) == core, text
        assert tx.subject_key(text) != tx.subject_key("Siqnalların emalı"), "the key itself never merges two spellings"
    for kept in ("Texniki xarici dil (rus dili)", "Texniki xarici dil (İngilis dili)", "Praktikum (Git, Docker, SQL)", "Proqramlaşdırma (backend)"):
        assert tx.subject_core(kept) == tx.subject_key(kept), kept
    assert tx.subject_core("Texniki xarici dil (rus dili)") != tx.subject_core("Texniki xarici dil (İngilis dili)")


def test_g5_the_year_is_read_by_pattern():
    assert tx.year("2026/27-CI TƏDRİS İLİ ÜÇÜN AKADEMİK YÜK") == tx.year("2026/2027-cı tədris ili üçün") == "2026/2027"
    assert tx.year("AZƏRBAYCAN TEXNİKİ UNİVERSİTETİ") is None


def test_g1_numbers_are_the_stored_values_and_an_error_is_not_a_number():
    assert tx.number("3.3333333333333335") == 3.3333333333333335 and tx.number("7,5") == 7.5 and tx.number("0") == 0
    assert [tx.number(x) for x in ("", "#REF!", "inf", "nan", "-1", "x", "1e30")] == [None] * 7


# ---------------------------------------------------------------- golden counts (T5) and G9
def by_kind(form, sheet=None):
    return dict(Counter((u.semester, u.kind) for u in form.units if sheet is None or u.sheet == sheet))


def test_t5_golden_counts_of_the_layout_a_fixture(form_a, sheets_a):
    f = form_a
    assert (f.layout, f.year) == ("A", "2026/2027") and "KAFEDRASI" in f.department
    assert [s.cls for s in f.sheets] == ["form-A", "form-A", "empty", "summary", "list"]
    assert [s.imported for s in f.sheets] == [True, True, False, False, False]
    main = [u for u in f.units if u.sheet == 0]
    assert (len(main), sum(u.hours for u in main)) == (19, 410)
    assert by_kind(f, 0) == {("payiz", "lecture"): 1, ("payiz", "seminar"): 5, ("payiz", "lab"): 4, ("yaz", "lecture"): 2,
                             ("yaz", "seminar"): 2, ("yaz", "lab"): 5}
    assert (len(f.units), sum(u.hours for u in f.units)) == (21, 455)
    assert (sum(u.hourly for u in f.units), sum(u.vacancy for u in f.units), sum(u.joint for u in f.units)) == (4, 5, 3)
    assert [(p.ref, p.units, p.blocked) for p in f.posts] == [("#0!A7", 5, False), ("#0!A22", 7, False), ("#0!A48", 3, False),
                                                              ("#0!A61", 2, True), ("#0!A72", 2, False), ("#1!A4", 2, True)]
    assert all(p.controls == {"T1": True, "T2": True, "T3": True} for p in f.posts)
    assert dict(Counter(x.kind for x in f.load)) == {"consultation": 7, "exam_prep": 4, "exam": 7, "practice": 2, "doctoral": 2}
    assert f.unclassified == 0


def test_t5_golden_counts_of_the_layout_b_fixture(form_b):
    f = form_b
    assert (f.layout, f.year) == ("B", "2026/2027")
    assert [s.cls for s in f.sheets] == ["form-B"] * 8 and [s.imported for s in f.sheets] == [True] * 6 + [False, True]
    shown = [u for u in f.units if not u.hidden]
    assert (len(f.units), len(shown), sum(u.hours for u in shown)) == (26, 24, 615)
    assert by_kind(f) == {("payiz", "lecture"): 7, ("payiz", "seminar"): 7, ("payiz", "lab"): 4, ("yaz", "lecture"): 3, ("yaz", "seminar"): 5}
    assert (sum(u.hourly for u in shown), sum(u.vacancy for u in shown), sum(u.joint for u in shown)) == (6, 3, 2)
    assert len(f.posts) == 12 and [p.ref for p in f.posts if p.blocked] == ["#5!B10", "#6!B10"]
    assert all(p.controls == {"T1": True, "T2": True, "T3": True} for p in f.posts)
    assert f.unclassified == 0


@pytest.mark.parametrize("which", ["a", "b"])
def test_g9_every_non_empty_cell_of_a_form_sheet_has_exactly_one_place(which, form_a, form_b, sheets_a, sheets_b):
    form, sheets = (form_a, sheets_a) if which == "a" else (form_b, sheets_b)
    cells = sum(1 for s, info in zip(sheets, form.sheets, strict=True) if info.cls.startswith("form-") for row in s.rows for v in row if v.strip())
    assert sum(form.cells.values()) == cells and form.unclassified == 0
    assert set(form.cells) <= {"unit", "load", "post", "header", "total", "ratio", "footer", "structure", "note", "conflict"}


# ---------------------------------------------------------------- sheets (G3, G4)
def test_g3_a_sheet_is_classified_by_its_content_never_by_its_name(sheets_a, sheets_b):
    renamed = copy.deepcopy(sheets_a)
    renamed[0].name, renamed[3].name, renamed[2].name = "Arayış", "Forma №3", "Forma"       # misleading names
    assert [forma3.classify(forma3.Grid(s, i)) for i, s in enumerate(renamed)] == ["form-A", "form-A", "empty", "summary", "list"]
    assert forma3.classify(forma3.Grid(sheets_b[0], 0)) == "form-B"
    odd = tables.Sheet("Qeydlər", [["Bu vərəqdə forma yoxdur"]])
    form = forma3.read([*sheets_b, odd])
    assert form.sheets[-1].cls == "unknown" and codes(form.conflicts, code="sheet_unknown")[0].blocking is False


def test_g4_a_hidden_sheet_is_read_and_listed_but_never_imported(form_b):
    info = form_b.sheets[6]
    assert (info.state, info.imported, info.units, info.hours) == ("hidden", False, 2, 45)
    assert post(form_b, "#6!B10").hidden and all(u.hidden for u in form_b.units if u.sheet == 6)
    r = forma3.report(form_b)
    assert r["units"] == {"count": 24, "hours": 615, "hidden": 2, "outside": 0, "ready": 22, "ready_hours": 540, "hourly": 6,
                          "vacancy": 3, "joint": 2}
    hidden_load = [x for x in form_b.load if x.sheet == 6]
    assert r["excluded"] == {"posts": ["#6!B10"], "units": 2, "hours": 45, "load_lines": len(hidden_load),
                             "load_hours": round(sum(x.hours for x in hidden_load), 4)}
    assert r["load_hours"] == round(sum(x.hours for x in form_b.load if x.sheet != 6), 4), "the hidden sheet's load is not in the totals"


def test_g4_a_hidden_row_with_a_value_gets_a_note(form_a):
    notes = codes(form_a.notes, code="hidden_row")
    assert [n.cell for n in notes] == ["#0!AJ41"] and not [n for n in codes(form_a.notes, code="outside") if n.cell == "#0!AJ41"]


def test_g4_a_hidden_staff_line_header_or_separator_row_is_said_too(sheets_a):
    """Checkpoint F review: only a post's hidden data rows were noted; a hidden title row, staff line or header row was read
    as if it were visible."""
    hidden = copy.deepcopy(sheets_a)
    hidden[0].hidden_rows |= {4, 6, 8, 16, 17}                   # the year title, A7's staff line, its header, its total, an empty row
    form = forma3.read(hidden)
    said = {(c.cell, c.blocking, c.post) for c in codes(form.conflicts, code="hidden_row")}
    assert said >= {("#0!A5", False, None), ("#0!A7", False, "#0!A7"), ("#0!A9", False, None)}
    assert {n.cell for n in codes(form.notes, code="hidden_row")} >= {"#0!AJ41", "#0!A17", "#0!E17"}
    assert not [x for x in (*form.notes, *form.conflicts) if x.code == "hidden_row" and x.cell[3:].lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ") == "18"]
    assert form.unclassified == 0 and not post(form, "#0!A7").blocked


def test_x20_the_xlsx_reader_gives_state_hidden_rows_and_formula_text(sheets_a, sheets_b):
    assert [s.state for s in sheets_b].count("hidden") == 1 and sheets_b[6].state == "hidden"
    assert sheets_a[0].hidden_rows == {40} and sheets_a[1].hidden_rows == set()
    assert sheets_a[3].formulas[(4, 6)] == "'Forma №3'!$AH$17"
    assert sheets_a[3].rows[4][6] == "272.3", "the cached value stays the cell's value"


# ---------------------------------------------------------------- the header and the semesters (H1–H7)
def test_h1_h2_the_two_row_header_band_and_the_number_row_are_not_data(form_b):
    first = post(form_b, "#0!B10")
    assert first.rows == (11, 16), "row 8 (kind names) and row 9 (column numbers) are header, not data"
    assert unit(form_b, "#0!F11").kind == "lecture" and unit(form_b, "#0!AA14").semester == "yaz"


def test_h3_h4_a_spring_lecture_under_the_autumn_label_is_spring(form_a, sheets_a):
    s, r, c = at("#0!A8")
    assert (r, 0, r, 18) in sheets_a[0].merges, "the fixture's autumn label reaches S, the spring lecture column"
    spring = unit(form_a, "#0!S14")
    assert (spring.semester, spring.kind, spring.hours) == ("yaz", "lecture", 30)
    assert not codes(form_a.conflicts, code="semester_labels")


def test_h4_labels_that_contradict_the_columns_refuse_the_post(sheets_a):
    wrong = changed(sheets_a, **{"#0!A8": "yaz semestri", "#0!T8": "payız semestri"})
    form = forma3.read(wrong)
    assert [c.post for c in codes(form.conflicts, code="semester_labels")] == ["#0!A7"] and post(form, "#0!A7").blocked
    gone = changed(sheets_a, **{"#0!A8": "", "#0!T8": ""})
    form = forma3.read(gone)
    assert not post(form, "#0!A7").blocked and [n.post for n in codes(form.notes, code="labels_absent")] == ["#0!A7"]
    assert unit(form, "#0!S14").semester == "yaz", "H3: the position between the Cəmi columns decides"


def test_h5_a_damaged_title_takes_the_other_blocks_title_and_is_reported(form_a):
    said = codes(form_a.conflicts, code="title_damaged")
    assert [(c.cell, c.blocking, c.post) for c in said] == [("#0!F24", False, "#0!A22")]
    eight = unit(form_a, "#0!F26")
    assert (eight.kind, eight.hours, len(eight.groups)) == ("seminar", 60, 8), "the column is never dropped"


def test_h5_a_damaged_title_with_nothing_to_agree_with_refuses_the_post(sheets_a):
    alone = changed([sheets_a[1]], **{"#0!F6": "kafedra@example.az"})
    form = forma3.read(alone)
    assert {c.code for c in form.conflicts if c.blocking} >= {"title_unknown", "header_incomplete"} and form.posts[0].blocked


def test_h5_layout_a_s_buraxilis_isi_column_is_doctoral_and_said_once(form_a):
    assert [(x.kind, x.hours, x.semester) for x in form_a.load if x.cell == "#0!AF16"] == [("doctoral", 80, "yaz")]
    assert [n.cell for n in codes(form_a.notes, code="doctoral_title")] == ["#0", "#1"]


def test_h5_the_row_s_own_label_decides_the_kind_of_a_supervision_load(sheets_b):
    moved = changed(sheets_b, **{"#0!AI15": "", "#0!AL15": "50"})         # MD supervision typed in the practice column
    form = forma3.read(moved)
    assert [(x.kind, x.hours) for x in form.load if x.cell == "#0!AL15"] == [("master_supervision", 50)]
    assert [n.cell for n in codes(form.notes, code="label_over_title")] == ["#0!AL15"]


def test_h6_t2_a_semester_total_that_does_not_add_up_blocks_the_post(sheets_a):
    form = forma3.read(changed(sheets_a, **{"#0!R17": "999"}))
    p = post(form, "#0!A7")
    assert p.controls == {"T1": True, "T2": False, "T3": True} and p.blocked
    assert [c.cell for c in codes(form.conflicts, code="t2")] == ["#0!R17", "#0!AH17"]


def test_h7_the_misspelt_other_teacher_title_is_the_counterpart_column_and_never_hours(form_b):
    lecture = unit(form_b, "#0!F11")
    assert [c["name"] for c in lecture.counterparts] == ["baş müəllim Həsənova Leyla Akif qızı"]
    assert lecture.teacher == "Quliyev Elçin Rauf oğlu", "B8, O1: the hours stay with the sheet's teacher"
    assert not [x for x in form_b.load if x.kind == "other_load"], "W/AQ «Digər dərs yükü» are hour columns, empty here"


# ---------------------------------------------------------------- blocks and sections (A2–A5, B3–B6)
def test_a2_a3_a_block_starts_at_its_structure_whatever_the_title_rows_say(form_a):
    second = post(form_a, "#0!A22")
    assert second.year == "2026/2027" and second.teacher == "Həsənova Leyla Akifovna" and second.fraction == 0.5
    assert [(n.cell, n.post) for n in codes(form_a.notes, code="title_text")] == [("#0!A19", "#0!A22")]


def test_a3_a_staff_line_without_the_word_stat_still_opens_its_own_post(form_a):
    assert [(p.ref, p.pay, p.vacancy, p.teacher) for p in form_a.posts if p.sheet == 0][2:] == [
        ("#0!A48", "staff", True, None), ("#0!A61", "hourly", False, "Məmmədov Tural"), ("#0!A72", "hourly", False, "Əliyeva Nigar Samir qızı")]
    assert {u.teacher for u in form_a.units if u.post == "#0!A61"} == {"Məmmədov Tural"}, "not folded into the block above"


def test_a4_t6_the_sheet_s_own_header_is_not_a_block_and_its_totals_are_a_control(form_a):
    assert len([p for p in form_a.posts if p.sheet == 0]) == 5
    control = next(c for c in form_a.controls if c.scope == "sheet")
    assert (control.check, control.ref, control.ok) == ("T6", "#0!AH3", True)
    assert "H" in codes(form_a.notes, code="sheet_totals")[0].message["az"], "the stale H3 is named, never imported"


def test_a5_the_total_row_ends_a_block_with_either_spelling(form_a):
    assert post(form_a, "#0!A7").total_ref == "#0!A17" and post(form_a, "#0!A48").total_ref == "#0!A56"
    assert post(form_a, "#0!A48").rows == (52, 55)


def test_a6_an_unreadable_staff_line_blocks_the_block_and_keeps_its_units(sheets_a):
    form = forma3.read(changed(sheets_a, **{"#0!A7": "Kafedranın yükü"}))
    p = post(form, "#0!A7")
    assert p.blocked and p.teacher is None and p.units == 5
    assert [c.blocking for c in codes(form.conflicts, code="staff_unreadable")] == [True]


def test_a7_the_summary_sheet_gives_the_staff_category_and_the_t6_sums(form_a):
    assert [(p.ref, p.employment, p.pay) for p in form_a.posts if p.sheet == 0] == [
        ("#0!A7", "main", "staff"), ("#0!A22", "external", "staff"), ("#0!A48", None, "staff"), ("#0!A61", None, "hourly"),
        ("#0!A72", None, "hourly")]
    t6 = [c for c in form_a.controls if c.check == "T6" and c.scope == "post"]
    assert len(t6) == 10 and all(c.ok for c in t6), "four people and the vacancy section, each by total and contact hours"
    assert [n.post for n in codes(form_a.notes, code="summary_position")] == ["#0!A22"], "müəllim vs baş müəllim"
    assert codes(form_a.notes, code="summary_list")


def test_a7_the_summary_s_hourly_section_makes_the_classes_hourly_and_says_the_difference(sheets_a):
    """Checkpoint F review: only the post turned hourly; its classes kept the staff line's pay, so the import wrote them as
    staff, and a staff line without a kind word gave no note."""
    form = forma3.read(changed(sheets_a, **{"#0!A72": "0,5 ştat - müəllim, Əliyeva Nigar Samir qızı"}))
    p = post(form, "#0!A72")
    assert (p.pay, p.fraction) == ("hourly", 0.5) and [u.hourly for u in form.units if u.post == p.ref] == [True, True]
    assert [n.post for n in codes(form.notes, code="summary_category")] == ["#0!A72"]
    form = forma3.read(changed(sheets_a, **{"#0!A7": "saat hesabı - dosent, Quliyev Elçin Rauf oğlu"}))
    p = post(form, "#0!A7")
    assert p.pay == "staff" and not any(u.hourly for u in form.units if u.post == p.ref), "the summary section wins both ways"
    assert [n.post for n in codes(form.notes, code="summary_category")] == ["#0!A7"]


def test_t6_the_vacancy_section_s_contact_cell_and_the_grand_total_are_checked(sheets_a):
    """Checkpoint F review: rt#4!H58 (vacancy contact + doctoral) and the grand totals G59, H59 were never compared (K6)."""
    def failing(**cells):
        form = forma3.read(changed(sheets_a, **{"#3!A15": "Ümumi cəm", "#3!G15": "714.97", "#3!H15": "570", **cells}))
        t6 = [c for c in form.controls if c.check == "T6"]
        assert {c.ref for c in t6 if c.scope == "file"} == {"#3!G15", "#3!H15"}
        return sorted((c.scope, c.ref) for c in t6 if not c.ok)
    assert failing() == [], "Σ year totals 714.96 within 0.02 of the typed 714.97; contact 570 = 430 + 140 (doctoral counted)"
    assert failing(**{"#3!H14": "999"}) == [("post", "#0!A48")]
    assert failing(**{"#3!G15": "99999"}) == [("file", "#3!G15")]
    assert failing(**{"#3!H15": "1"}) == [("file", "#3!H15")]


def test_a7_a_summary_row_without_a_formula_is_linked_by_total_and_name(sheets_a):
    plain = copy.deepcopy(sheets_a)
    plain[3].formulas.clear()
    form = forma3.read(plain)
    assert post(form, "#0!A22").employment == "external" and len([c for c in form.controls if c.check == "T6" and c.scope == "post"]) == 10


def test_a11_a_form_sheet_outside_the_summary_is_read_and_refused(form_a):
    stray = post(form_a, "#1!A4")
    assert stray.year_conflict and stray.blocked and stray.units == 2
    assert {c.code for c in form_a.conflicts if c.post == "#1!A4"} == {"year_conflict", "not_in_summary"}
    assert all({"flag": "year_conflict", "cell": "#1!A4"} in u.flags for u in form_a.units if u.sheet == 1)


def test_a10_a_supervision_row_that_names_someone_else_gets_a_note(form_a):
    assert [n.cell for n in codes(form_a.notes, code="supervisor")] == ["#0!C55"], "in the vacancy block; the owner's own row is silent"


def test_a12_values_right_of_the_form_are_notes_and_helper_sums_are_structure(sheets_a):
    form = forma3.read(changed(sheets_a, **{"#0!AJ10": "Nuranə"}))
    assert [n.cell for n in codes(form.notes, code="outside")] == ["#0!AJ10"]
    assert form.unclassified == 0, "AJ on the total rows (the helper sums) is structure"


def test_b3_b4_sections_second_posts_and_hourly_sub_sections(form_b):
    mine = [p for p in form_b.posts if p.sheet == 0]
    assert [(p.ref, p.pay, p.fraction, p.employment, p.second_post_of, p.units) for p in mine] == [
        ("#0!B10", "staff", 1.0, None, None, 5), ("#0!B19", "staff", 0.5, "internal", "#0!B10", 1), ("#0!B23", "hourly", None, None, None, 2)]
    assert post(form_b, "#1!B10").employment == "main" and post(form_b, "#5!B10").employment is None, "never guessed"


def test_b3_an_unknown_label_on_a_person_s_sheet_blocks_the_section(sheets_b):
    form = forma3.read(changed(sheets_b, **{"#0!B19": "İkinci iş"}))
    assert [(c.cell, c.blocking) for c in codes(form.conflicts, code="label_unknown")] == [("#0!B19", True)]
    assert post(form, "#0!B19").blocked and not post(form, "#0!B10").blocked


def test_b5_total_detection_labelled_unlabelled_and_the_empty_section(form_b):
    assert (post(form_b, "#0!B10").total_ref, post(form_b, "#0!B10").ratio_ref) == ("#0!B17", "#0!AS18")
    assert post(form_b, "#0!B19").ratio_ref == "#0!AS22", "an unlabelled ratio row"
    unlabelled = post(form_b, "#1!B10")
    assert (unlabelled.rows, unlabelled.total_ref, unlabelled.ratio_ref) == ((11, 16), "#1!A17", "#1!AS18")
    empty = post(form_b, "#1!B19")
    assert (empty.rows, empty.total_ref, empty.units) == (None, "#1!B21", 0), "the blank row before CƏMİ is not the total"


def test_b5_a_data_row_after_the_total_is_a_blocking_conflict(sheets_b):
    form = forma3.read(changed(sheets_b, **{"#0!B18": "Unudulmuş fənn", "#0!C18": "6525a", "#0!AR18": "", "#0!AS18": ""}))
    assert [(c.cell, c.blocking, c.post) for c in codes(form.conflicts, code="after_total")] == [("#0!B18", True, "#0!B10")]


def test_b6_the_footer_ends_the_sheet(form_b, sheets_b):
    form = forma3.read(changed(sheets_b, **{"#0!B31": "sonra yazılıb"}))
    assert [n.cell for n in codes(form.notes, code="after_footer")] == ["#0!B31"]
    assert form_b.cells["footer"] == 16


def test_b9_a_sheet_with_no_data_rows_is_a_teacher_with_zero_load(sheets_b):
    lonely = mk.sheet_b("Boş M.", "müəllim Kərimov Rəşad Samir oğlunun", [{"label": "0.5  ŞTAT", "gap": 2, "data": []}])
    form = forma3.read(tables.xlsx_sheets(mk.xlsx([lonely])))
    assert form.units == [] and [n.cell for n in codes(form.notes, code="zero_load")] == ["#0"] and not form.posts[0].blocked



def test_g9_a_sheet_whose_group_rows_give_nothing_is_a_conflict_not_a_zero_load(sheets_b):
    """The guard against the old reader's silent "0 lines": rows with groups and no hours are no teacher with zero load."""
    rows = [{1: "Fənn", 2: "6526a", 3: "10"}, {1: "Fənn 2", 2: "6526b", 3: "12"}, {1: "CƏMİ"}]
    form = forma3.read([layout_b_sheet(sheets_b, rows)])
    assert [(c.cell, c.blocking) for c in codes(form.conflicts, code="no_units")] == [("#0", False)]
    assert not codes(form.notes, code="zero_load")


@pytest.mark.parametrize("name, tokens", [
    ("Kərimov Rəşad 0,5 ştat", []), ("Rəşad Kərimov", []), ("Kərimov R.", []),
    ("Kərimov Rəşad saathesabı", ["saathesabı"]),   # the sheet has no hourly section
    ("Kərimov Samir", ["Samir"]),                   # the patronymic in place of the given name (B2, mr#83)
    ("Kərimov Ora", ["Ora"]),                       # a word is never found as a piece of another cell's text ("Laboratoriya")
    ("Kərimov Rəşad (sabah)", ["sabah"]),           # a bracket's word only needs some cell to repeat it
])
def test_b2_the_sheet_name_is_compared_with_the_teacher_cell_word_by_word(name, tokens):
    sheet = mk.sheet_b(name, "müəllim Kərimov Rəşad Samir oğlunun", [{"label": "0.5  ŞTAT", "gap": 2, "data": []}])
    form = forma3.read(tables.xlsx_sheets(mk.xlsx([sheet])))
    assert form.posts[0].sheet_name_tokens == tokens
    assert len(codes(form.notes, code="sheet_name")) == (1 if tokens else 0)


# ---------------------------------------------------------------- rows, classes, merges (G1, G2, R1–R6, J1–J7)
def test_j1_a_merged_lecture_is_one_class_for_every_group_it_covers(form_a, form_b):
    stream = unit(form_a, "#0!E11")
    assert (stream.merge, stream.member_rows, stream.joint) == ("#0!E11:E13", [11, 12, 13], True)
    assert [(g["code"], g["students"]) for g in stream.groups] == [("6524a1", 25), ("6524a2", 24), ("6524a3", 26)] and stream.students_total == 75
    assert [g["code"] for g in unit(form_b, "#0!F11").groups] == ["6526e1", "6526e2", "6526e3"], "G7: three groups, not subgroups"


def test_j2_a_joint_seminar_is_one_class_and_counts_once_in_the_total(form_a):
    assert [g["code"] for g in unit(form_a, "#0!F11").groups] == ["6524a1", "6524a2"]
    eight = unit(form_a, "#0!F26")
    assert (len(eight.groups), eight.students_total, eight.hours) == (8, 12, 60), "students are the class's own counts (G8)"
    assert post(form_a, "#0!A22").controls["T3"], "T3 holds only when the merged value is counted once"


def test_j3_an_empty_merge_mirrors_the_class_given_in_another_post(form_a, form_b):
    mirror = [(x.source, x.to, x.level) for x in form_a.links if x.basis == "empty_merge_mirror"]
    assert mirror == [("#0!E34:E36", "#0!E11", "info")]
    assert [(x.source, x.to, x.level) for x in form_b.links if x.basis == "empty_merge_mirror"] == [("#1!F11:F13", "#0!F11", "info")]
    assert not [u for u in form_a.units if u.anchor.startswith("#0!E3")], "an empty merge creates no unit"


def test_j3_an_empty_merge_with_no_class_anywhere_is_said(sheets_b):
    form = forma3.read([sheets_b[1]])
    assert [(x.source, x.to) for x in form.links if x.basis == "empty_merge_mirror"] == [("#0!F11:F13", None)]
    assert [n.cell for n in codes(form.notes, code="class_elsewhere")] == ["#0!F11:F13"]


def test_j4_a_class_merge_over_two_different_subjects_is_a_blocking_conflict(sheets_b):
    crossing = copy.deepcopy(sheets_b)
    crossing[1].merges.append((14, 5, 15, 5))                    # F15:F16, both "Fizika-1": allowed
    crossing[1].rows[15][5] = ""
    assert not codes(forma3.read(crossing).conflicts, code="merge_subjects")
    crossing[1].rows[15][1] = "Fizika-2"
    form = forma3.read(crossing)
    assert [c.cell for c in codes(form.conflicts, code="merge_subjects")] == ["#1!F15:F16"]


def test_j5_j6_groups_come_from_merges_only_never_from_the_rows_position(form_a, form_b):
    assert [g["code"] for g in unit(form_a, "#0!F13").groups] == ["6524a3"], "J5: a stream member's own seminar"
    assert [g["code"] for g in unit(form_b, "#1!F14").groups] == ["6525a"], "the lab rows above it are not joined"
    assert all(len(u.groups) == 1 for u in form_b.units if u.sheet == 1 and u.kind == "lab")


def test_j7_links_between_posts_are_suggestions_only(form_a, form_b):
    labs = [(x.source, x.to) for x in form_b.links if x.basis == "subject_core+groups+semester" and x.to]
    assert labs == [("#1!H11", "#0!F11"), ("#1!H12", "#0!F11"), ("#1!H13", "#0!F11")]
    alone = {x.source for x in form_b.links if x.basis == "subject_core+groups+semester" and x.to is None}
    assert {"#2!AA11", "#2!AA12"} <= alone, "a seminar with no lecture in the file is information, not a conflict"
    assert not [x for x in form_a.links if x.source == "#0!U53"], "a lab in its lecture's own post needs no link"
    assert unit(form_a, "#0!U54").subject_core == unit(form_a, "#0!S53").subject_core, "İFS: is the same course for linking"
    assert unit(form_a, "#0!U54").subject_key != unit(form_a, "#0!S53").subject_key


def test_r2_a_subject_is_never_carried_over_from_the_row_above(form_a, form_b):
    said = codes(form_a.conflicts, code="subject_missing")
    assert [(c.cell, c.blocking, c.post) for c in said] == [("#0!C66", True, "#0!A61")]
    assert [x.subject_raw for x in form_a.load if x.cell == "#0!AA66"] == [""], "the load line is returned, with no invented subject"
    assert unit(form_b, "#5!AA12").subject_raw == "" and unit(form_b, "#5!AA12").flags[0]["flag"] == "subject_missing"
    assert unit(form_a, "#0!G35").subject_raw == "Alqoritmlər", "through the vertical merge C34:C36"


def test_r3_r4_every_valued_contact_cell_is_one_unit_and_a_repeat_is_another_class(form_b):
    twice = [u for u in form_b.units if u.post == "#1!B10" and u.kind == "lecture" and [g["code"] for g in u.groups] == ["6524r"]]
    assert [(u.anchor, u.hours) for u in twice] == [("#1!F15", 30), ("#1!F16", 15)]
    assert (unit(form_b, "#0!Z14").semester, unit(form_b, "#0!AA14").kind) == ("yaz", "seminar")


def test_r5_a_row_with_hours_and_no_group_keeps_its_unit_and_blocks_the_post(form_b):
    u = unit(form_b, "#5!Z11")
    assert (u.hours, u.groups, u.flags) == (60, [], [{"flag": "group_missing", "cell": "#5!C11"}])
    assert u.students_total == 10, "the row's own student count is kept for when a person adds the group"
    assert [(c.cell, c.blocking) for c in codes(form_b.conflicts, code="group_missing")] == [("#5!C11", True)]
    assert post(form_b, "#5!B10").blocked and not post(form_b, "#5!B14").blocked, "the hourly sub-section of the sheet is not affected"


def test_r6_a_group_with_no_class_and_no_load_gets_an_information_note(form_a):
    assert [n.cell for n in codes(form_a.notes, code="group_no_class")] == ["#0!B40"]
    assert [n.cell for n in codes(form_a.notes, code="item_only")] == ["#0!A52"]


def test_g1_text_in_an_hour_cell_of_a_data_row_blocks_and_a_stray_text_row_is_a_note(sheets_b):
    form = forma3.read(changed(sheets_b, **{"#0!H12": "x"}))
    assert [(c.cell, c.blocking) for c in codes(form.conflicts, code="hours_text")] == [("#0!H12", True)]
    stray = copy.deepcopy(sheets_b)
    stray[0].rows.insert(30, [""] * len(stray[0].rows[0]))
    form = forma3.read(changed(sheets_b, **{"#0!I27": "\\"}))
    assert [n.cell for n in codes(form.notes, code="stray_text")] == ["#0!I27"] and not codes(form.conflicts, code="hours_text")
    form = forma3.read(changed(sheets_b, **{"#0!I27": "#REF!"}))
    assert [(c.cell, c.blocking) for c in codes(form.conflicts, code="hours_text")] == [("#0!I27", True)], "G1: an error value is no stray text"
    assert not codes(form.notes, code="stray_text") and post(form, "#0!B23").blocked
    rows = [{1: "Fənn", 2: "6526a", 3: "10", 5: "30", 23: "30", 44: "30"}, {5: "#REF!"}, {1: "CƏMİ", 5: "30", 23: "30", 44: "30"}]
    form = forma3.read([layout_b_sheet(sheets_b, rows)])
    assert [c.cell for c in codes(form.conflicts, code="hours_text")] == ["#0!F12"] and form.posts[0].blocked


def test_g2_a_value_under_a_merge_is_a_blocking_conflict(sheets_a):
    form = forma3.read(changed(sheets_a, **{"#0!E12": "30"}))
    assert [(c.cell, c.blocking) for c in codes(form.conflicts, code="covered_value")] == [("#0!E12", True)]


def test_j3_a_valued_merge_over_several_hour_columns_is_ambiguous(sheets_a):
    wide = copy.deepcopy(sheets_a)
    wide[0].merges.append((13, 18, 13, 19))                      # S14:T14
    form = forma3.read(wide)
    assert [c.cell for c in codes(form.conflicts, code="merge_ambiguous")] == ["#0!S14:T14"] and post(form, "#0!A7").blocked


def test_g8_students_a_blank_count_is_flagged_and_a_fraction_is_refused(form_a, sheets_a):
    assert [n.cell for n in codes(form_a.notes, code="students_missing")] == ["#0!D54"]
    assert unit(form_a, "#0!U54").groups[0]["students"] is None and {"flag": "students_missing", "cell": "#0!D54"} in unit(form_a, "#0!U54").flags
    form = forma3.read(changed(sheets_a, **{"#0!D11": "2.7"}))
    assert [(c.cell, c.blocking) for c in codes(form.conflicts, code="students_fraction")] == [("#0!D11", True)]
    differ = codes(form_a.notes, code="students_differ")
    assert any("6524a1" in n.message["az"] and "2, 25" in n.message["az"] for n in differ), "different counts are reported, never averaged"


def test_g7_a_code_that_looks_wrong_is_a_non_blocking_conflict_unless_the_registry_knows_it(sheets_a):
    form = forma3.read(changed(sheets_a, **{"#0!B15": "26123a"}))
    said = codes(form.conflicts, code="code_wrong")
    assert [(c.cell, c.blocking, c.data) for c in said] == [("#0!B15", False, {"code": "26123a"})]
    assert not post(form, "#0!A7").blocked
    assert [c["code"] for c in forma3.report(form, {"26123a"})["conflicts"] if c["code"] == "code_wrong"] == []


# ---------------------------------------------------------------- pay, vacancies, load (P1–P3, L1–L4, K7)
def test_p2_hourly_blocks_and_sections_are_real_classes_flagged_hourly(form_a, form_b):
    assert {u.anchor for u in form_a.units if u.hourly} == {"#0!F65", "#0!G65", "#0!F76", "#0!T77"}
    assert {u.post for u in form_b.units if u.hourly} == {"#0!B23", "#2!B10", "#4!B10", "#5!B14"}
    assert all(not u.hourly for u in form_b.units if u.post == "#0!B10")


def test_p3_a_vacancy_has_no_teacher_and_keeps_its_area(form_a, form_b):
    assert [(p.ref, p.vacancy_area, p.pay, p.teacher) for p in form_b.posts if p.vacancy] == [
        ("#3!B10", "RİYAZİYYAT", "staff", None), ("#4!B10", "1 magistr", "hourly", None)]
    assert all(u.teacher is None and u.vacancy for u in form_b.units if u.sheet in (3, 4))
    assert [u.vacancy for u in form_a.units if u.post == "#0!A48"] == [True] * 3


def test_l1_a_merged_load_cell_is_one_line_for_all_its_groups(form_a, form_b):
    paper = next(x for x in form_a.load if x.cell == "#0!I11")
    assert (paper.kind, paper.hours, paper.merge, [g["code"] for g in paper.groups], paper.students_total) == (
        "exam_prep", 5, "#0!I11:I13", ["6524a1", "6524a2", "6524a3"], 75)
    exam = next(x for x in form_a.load if x.cell == "#0!J26")
    assert (exam.hours, exam.students_total, len(exam.groups)) == (4, 12, 8) and not codes(form_a.notes, code="exam_diff")
    assert next(x for x in form_b.load if x.cell == "#0!L11").merge == "#0!L11:L13"


def test_l2_special_rows_are_load_lines_never_units(form_a, form_b):
    assert [(x.kind, x.hours, x.groups[0]["code"]) for x in form_a.load if x.cell == "#0!AA15"] == [("practice", 40, "6523a1")]
    md = next(x for x in form_b.load if x.cell == "#0!AI15")
    assert (md.kind, md.hours, md.groups, md.students_total) == ("master_supervision", 50, [], 2), "D without a group is a supervised count"
    assert not [u for u in form_b.units if 15 in u.member_rows and u.sheet == 0]


def test_l3_hours_for_phd_students_are_a_load_line_and_a_blocking_question(sheets_a):
    form = forma3.read(changed(sheets_a, **{"#0!N14": "30", "#0!N17": "30", "#0!R14": "30", "#0!R17": "122.96666666666667",
                                            "#0!AH14": "89.33333333333334", "#0!AH17": "302.3"}))
    assert [(c.cell, c.blocking) for c in codes(form.conflicts, code="phd_teaching")] == [("#0!N14", True)]
    assert [x.kind for x in form.load if x.cell == "#0!N14"] == ["phd_teaching"] and all(post(form, "#0!A7").controls.values())


def test_l4_an_exam_far_from_a_third_of_the_students_is_a_note(sheets_a):
    form = forma3.read(changed(sheets_a, **{"#0!J12": "9", "#0!J17": "25.966666666666665", "#0!R12": "10", "#0!AH12": "10",
                                            "#0!R17": "93.96666666666667", "#0!AH17": "273.3"}))
    assert [n.cell for n in codes(form.notes, code="exam_diff")] == ["#0!J12"] and all(post(form, "#0!A7").controls.values())


def test_k7_load_in_a_semester_without_a_class_on_that_row_is_noted(sheets_b):
    form = forma3.read(changed(sheets_b, **{"#0!AC11": "1", "#0!AC17": "2", "#0!AR11": "1", "#0!AS11": "77", "#0!AR17": "142", "#0!AS17": "263"}))
    assert [n.cell for n in codes(form.notes, code="mixed_semester")] == ["#0!AC11"] and all(post(form, "#0!B10").controls.values())
    assert [(x.semester, x.kind) for x in form.load if x.cell == "#0!AC11"] == [("yaz", "consultation")]


def test_spacer_a_value_in_the_untitled_column_is_never_load(form_b):
    assert [n.cell for n in codes(form_b.notes, code="spacer")] == ["#2!Y11"]
    assert all(post(form_b, "#2!B10").controls.values())


# ---------------------------------------------------------------- the other-teacher column (O1)
def test_o1_counterparts_are_spread_over_a_merge_and_cross_checked(form_b):
    for anchor in ("#0!F11", "#0!G11", "#0!G13", "#1!H11", "#1!H13"):
        assert len(unit(form_b, anchor).counterparts) == 1, anchor
    names = [(x.source, x.to, x.level) for x in form_b.links if x.basis == "at_name"]
    assert len(names) == 6 and all(level == "info" and to for _, to, level in names), "each colleague's sheet confirms the class"
    assert unit(form_b, "#1!H11").counterparts[0]["name"] == "t.ü.f.d., dosent Quliyev Elçin Rauf oğlu", "a degree's comma does not split a name"


@pytest.mark.parametrize("a, b, same", [
    ("Məmmədov Tural Akif oğlu", "Məmmədov Tural Akif oğlu", True),
    ("Məmmədov Tural", "Məmmədov Tural Akif oğlu", True),
    ("Tural Məmmədov", "Məmmədov Tural Akif oğlu", True),                 # the counterpart cells write the name first
    ("Mənmədov Tural Akif oğlu", "Məmmədov Tural Akif oğlu", True),       # one letter forgiven
    ("t.e.d., prof. Məmmədov Tural Akif oğlu", "Məmmədov Tural Akif oğlu", True),
    ("Məmmədov", "Məmmədov Tural Akif oğlu", True),
    ("Məmmədov Tural Akif oğlu", "Həsənov Akif Tural oğlu", False),       # same name and patronymic, another surname
    ("Məmmədov Tural Tural oğlu", "Həsənov Kamal Tural oğlu", False),     # one word of b is never matched twice
    ("Həsənov Kamal Tural oğlu", "Məmmədov Tural Tural oğlu", False),
    ("Məmmədov Kamal Rauf oğlu", "Məmmədov Tural Akif oğlu", False),      # A8: a shared surname alone joins nobody
])
def test_a8_same_person_needs_the_surname_and_one_more_word_matched_once(a, b, same):
    assert forma3._same_person(a, b) is same


def test_o1_a_counterpart_nobody_in_the_file_matches_is_a_note(sheets_b):
    form = forma3.read(changed(sheets_b, **{"#1!AT11": "Uydurmayev Anar, dosent Quliyev Elçin Rauf oğlu"}))
    assert len(unit(form, "#1!H11").counterparts) == 2
    assert {n.cell for n in codes(form.notes, code="counterpart_outside")} == {"#1!AT11"}


# ---------------------------------------------------------------- the acceptance test (T1–T4, K1)
def test_t1_a_column_total_that_differs_from_the_rows_blocks_the_post(sheets_b):
    form = forma3.read(changed(sheets_b, **{"#0!G17": "90"}))
    p = post(form, "#0!B10")
    assert p.controls["T1"] is False and p.blocked and [c.cell for c in codes(form.conflicts, code="t1")] == ["#0!G17"]
    assert not post(form, "#0!B19").blocked, "the sheet's other sections are judged on their own"


def test_t1_a_blank_total_cell_counts_as_zero(form_b, sheets_b):
    s, r, c = at("#0!M17")
    assert sheets_b[s].rows[r][c] == "" and post(form_b, "#0!B10").controls["T1"]
    form = forma3.read(changed(sheets_b, **{"#0!F17": ""}))
    assert post(form, "#0!B10").controls["T1"] is False, "a blank total over a non-zero column is a conflict"


def test_k1_an_error_value_in_a_total_row_is_recomputed_and_does_not_block(form_b):
    said = codes(form_b.conflicts, code="total_error")
    assert [(c.cell, c.blocking) for c in said] == [("#2!AN13", False), ("#2!AO13", False), ("#2!AR13", False), ("#2!AS13", False)]
    p = post(form_b, "#2!B10")
    assert p.controls == {"T1": True, "T2": True, "T3": True} and not p.blocked and round(p.year_total, 3) == 74.333


def test_t5_counts_the_department_s_posts_against_the_grid_and_the_total_rows(form_a, sheets_a):
    """Checkpoint F review: T5 was built with ok=True and no expected value, and the file totals counted a sheet the summary
    leaves out (rt#1) and the hidden sheet's load."""
    t5 = [c for c in form_a.controls if c.check == "T5"]
    assert [(c.expected, c.found, c.ok) for c in t5] == [(19.0, 19.0, True), (410.0, 410.0, True)], "#1!A4 is outside the totals"
    form = forma3.read(changed(sheets_a, **{"#0!F17": "45"}))                    # a contact total that the rows do not give
    assert [(c.expected, c.found, c.ok) for c in form.controls if c.check == "T5"] == [(19.0, 19.0, True), (425.0, 410.0, False)]


def test_t3_units_and_load_must_cover_the_totals(form_a, form_b):
    for form in (form_a, form_b):
        for c in form.controls:
            if c.check == "T3":
                assert c.ok and c.expected == c.found == sum(u.hours for u in form.units if u.post == c.ref)


def test_t3_a_unit_the_reader_lost_fails_t3_while_t1_holds(sheets_b, monkeypatch):
    """Checkpoint F review: for this reader T3 follows from T1 on any input (every valued top-left hour cell becomes exactly
    one unit or load line), so it guards the reader itself: a unit lost between the rows and the controls must block."""
    real = forma3._controls

    def losing(R, g, p, cols, r0, total, sums, units, loads, vals):
        return real(R, g, p, cols, r0, total, sums, units[1:] if p.ref == "#0!B10" else units, loads, vals)
    monkeypatch.setattr(forma3, "_controls", losing)
    form = forma3.read(sheets_b)
    p = post(form, "#0!B10")
    assert p.controls == {"T1": True, "T2": True, "T3": False} and p.blocked
    assert [c.post for c in codes(form.conflicts, code="t3")] == ["#0!B10"]


def test_t4_a_per_row_total_that_differs_is_only_a_note_and_a_merged_one_is_summed(form_a, sheets_a):
    assert not codes(form_a.notes, code="row_total"), "the merged R25:R32 is compared with the sum over its rows"
    form = forma3.read(changed(sheets_a, **{"#0!R11": "1"}))
    assert [n.cell for n in codes(form.notes, code="row_total")] == ["#0!R11"] and not post(form, "#0!A7").blocked
    blank = forma3.read(changed(sheets_a, **{"#0!R14": ""}))
    assert not codes(blank.notes, code="row_total"), "a blank per-row total whose true value is 0 says nothing"


def test_a_block_without_a_total_row_is_blocked(sheets_a):
    form = forma3.read(changed(sheets_a, **{"#0!A17": ""}))
    assert post(form, "#0!A7").blocked and [c.cell for c in codes(form.conflicts, code="total_missing")] == ["#0!A7"]


# ---------------------------------------------------------------- hostile input
def test_merges_that_cover_too_many_cells_are_refused_not_expanded():
    rows = [["x"] * 150 for _ in range(2000)]
    with pytest.raises(forma3.FormError):
        forma3.read([tables.Sheet("S", rows, [(0, 0, 1999, 149), (0, 0, 1999, 149)])])


def layout_b_sheet(sheets_b, rows_data, merges=()):
    """Sheet #0 of the layout-B fixture cut after its section label (row 10), with the given data rows ({column: value})."""
    s = copy.deepcopy(sheets_b[0])
    width = 46
    s.rows = [r[:] + [""] * (width - len(r)) for r in s.rows[:10]]
    for d in rows_data:
        row = [""] * width
        for c, v in d.items():
            row[c] = v
        s.rows.append(row)
    s.merges = [m for m in s.merges if m[0] < 10] + list(merges)
    s.formulas = {}
    return s


def test_many_bad_rows_are_read_in_linear_time(sheets_b):
    """Checkpoint F review: a conflict was compared with every conflict before it and a row without a subject looked back
    over every row above, so 20 000 bad rows took over a minute while the request held a handler slot."""
    import time
    rows = [{2: f"6526a{i % 9}", 3: "x", 5: "30"} for i in range(20_000)]       # no subject, an unreadable student count
    sheet = layout_b_sheet(sheets_b, rows)
    t = time.monotonic()
    form = forma3.read([sheet])
    assert time.monotonic() - t < 20
    assert len(codes(form.conflicts, code="subject_missing")) == len(codes(form.conflicts, code="students_text")) == 20_000
    assert codes(form.conflicts, code="subject_missing")[1].message["az"].endswith("—)"), "no subject above: the message says so"


def test_a_sheet_with_a_header_and_nothing_else_does_not_crash():
    form = forma3.read([tables.Sheet("S", [["Sıra sayı", "Qruplar", "Fənlər"]])])
    assert form.units == [] and form.posts == [] and form.unclassified == 0


@pytest.mark.parametrize("fixture", ["sheets_a", "sheets_b"])
def test_a_damaged_form_never_raises_anything_but_formerror(fixture, request):
    """A hostile or half-edited workbook ends in conflicts or a ``FormError`` (a translated 400), never in a crash, and
    still leaves no cell without a place (G9)."""
    base = request.getfixturevalue(fixture)
    rnd = random.Random(47)
    values = ["", "x", "0", "-5", "1e30", "nan", "#REF!", "Cəmi", "CƏMİ", "Fənlər", "QRUP №-si", "1 ŞTAT", "Saat hesabı", "Vakansiya",
              "payız semestri", "Mühazirə", "İl ərzində cəmi", "kafedrasının müdiri", "Aktiv ", "2.7", "6524a1"]
    for _ in range(60):
        sheets = copy.deepcopy(base)
        for _ in range(rnd.choice((1, 2, 5, 20))):
            sh = rnd.choice([x for x in sheets if x.rows])
            op, r = rnd.random(), rnd.randrange(len(sh.rows))
            if op < 0.5 and sh.rows[r]:
                sh.rows[r][rnd.randrange(len(sh.rows[r]))] = rnd.choice(values)
            elif op < 0.6:
                del sh.rows[r]
            elif op < 0.7:
                sh.rows.insert(r, [rnd.choice(values) for _ in range(rnd.randrange(50))])
            elif op < 0.8 and sh.merges:
                del sh.merges[rnd.randrange(len(sh.merges))]
            elif op < 0.9:
                c = rnd.randrange(50)
                sh.merges.append((r, c, r + rnd.randrange(4), c + rnd.randrange(4)))
            else:
                sh.rows[r] = []
        try:
            form = forma3.read(sheets)
        except forma3.FormError:
            continue
        forma3.report(form)
        assert form.unclassified == sum(n.code == "unclassified" for n in form.notes)


def test_forma3_check_prints_cells_and_counts_and_no_name(capsys):
    """``manage.py forma3-check``: a department checks its file before uploading; the default output holds no person's
    name and no cell text; the exit code says whether a post is blocked."""
    import manage
    assert manage.main(["forma3-check", str(FIX / "forma3_blocks.xlsx")]) == 1
    out = capsys.readouterr().out
    assert "dərslər: 19 (410 auditoriya saatı); tətbiq oluna bilən: 17" in out and "yoxlamalar T1–T3: 6/6" in out
    assert "kafedranın cəminə daxil olmayan: 1 ştat/bölmə (#1!A4) — 2 dərs (45 saat)" in out and "yoxlama T5: 2/2" in out
    assert "BLOK #0!C66  subject_missing" in out and "BLOK #0!A61: 2 dərs" in out and "heç bir qaydaya düşməyən xana: 0" in out
    for word in ("Quliyev", "Həsənova", "Məmmədov", "Əliyeva", "Elektronika", "verdiyim"):
        assert word not in out, word
    assert manage.main(["forma3-check", str(FIX / "forma3_blocks.xlsx"), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["posts"][0]["teacher"] == "Quliyev Elçin Rauf oğlu", "--json is the full report"
    assert manage.main(["forma3-check", str(FIX / "users_10k.csv")]) == 2 and "error:" in capsys.readouterr().err


def test_the_report_lists_posts_conflicts_notes_and_load_totals(form_a):
    r = forma3.report(form_a)
    assert [p["status"] for p in r["posts"]] == ["ok", "ok", "ok", "blocked", "ok", "blocked"]
    assert r["load"]["practice"] == {"lines": 2, "hours": 80} and r["blocking_count"] == 3 and r["unclassified"] == 0
    assert r["conflicts"][0]["blocking"] and {"cell", "code", "message", "blocking", "post"} == set(r["conflicts"][0])
