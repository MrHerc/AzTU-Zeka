"""Forma №3, a department's academic load, as AzTU departments really fill it (docs/forms/forma-3.md, Task 47). No I/O:
``read(sheets) -> Form`` with posts, units, load lines, links, notes, conflicts and the arithmetic controls T1–T6.

Two layouts, told apart by the header's content, never by a sheet's name:
(A) one sheet of teacher blocks: three title rows, the staff line, the semester labels, a one-row header, data, ``Cəmi``;
(B) one sheet per teacher: the teacher in the title rows, a two-row header, sections opened by a merged label
    (``1 ŞTAT``, ``Saat hesabı`` ...), each closed by its ``CƏMİ`` row.

What the reader relies on (the rule ids are those of docs/forms/forma-3.md):
- cached cell values only (G1); a merged cell's value lives in its top-left cell and counts once (G2);
- a semester is the columns between the ``Cəmi`` columns (H3): the labels above only confirm (H4), the total row proves
  it with numbers (H6);
- a unit is a non-zero top-left contact cell; its groups are the rows its merge covers (R3, J1, J2); a subject comes from
  the row or the vertical merge over it, never from the row above (R2);
- hourly sections and blocks are read like any other and flagged (P2); a vacancy has no teacher (P3);
- every non-empty cell of a form sheet ends in exactly one place (G9); a post that fails T1–T3, or holds a blocking
  conflict, is returned but must not be applied.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace

from ...core.i18n import E, S_
from . import forma3_text as tx
from .forma3_text import col_name, key
from .tables import Sheet

norm = key                                       # kept: the importer and the syllabus compare names with it
MAX_COVER = 400_000                              # cells under merges, per sheet: a hostile file names huge ranges
TOL = 0.011                                      # T1, T3, T4
TOL_SUM = 0.02                                   # T2, T6
SEMESTERS = ("payiz", "yaz")
CONTACT = ("lecture", "seminar", "lab")


class FormError(ValueError):
    """The workbook cannot be read as a form at all; the message is an Azerbaijani catalogue key."""


# ---------------------------------------------------------------- messages (Azerbaijani catalogue keys)
MSG = {
    # conflicts
    "covered_value": S_("Birləşdirilmiş xananın örtdüyü xanada dəyər var: {x}"),
    "hours_text": S_("Saat xanasında ədəd olmayan dəyər var: {x}"),
    "merge_ambiguous": S_("Bir neçə sütunu birləşdirən saat xanasında dəyər var: dərsin növü müəyyən edilə bilmir"),
    "group_missing": S_("Auditoriya saatı olan sətirdə qrup göstərilməyib"),
    "subject_missing": S_("Saatı olan sətirdə fənnin adı yoxdur (yuxarıdakı sətrin fənni: {x})"),
    "students_text": S_("Tələbə sayı oxunmadı: {x}"),
    "students_fraction": S_("Dərs sətrində tələbə sayı tam ədəd deyil: {x}"),
    "merge_subjects": S_("Birləşdirilmiş dərs xanası müxtəlif fənlərin sətirlərini əhatə edir"),
    "merge_outside": S_("Birləşdirilmiş saat xanası bölmənin sətirlərindən kənara çıxır"),
    "staff_unreadable": S_("Ştat sətri oxunmadı: {x}"),
    "teacher_unreadable": S_("Müəllimin adı oxunmadı: {x}"),
    "label_unknown": S_("Bölmənin başlığı tanınmadı: {x}"),
    "label_absent": S_("Sətirlərdən əvvəl bölmənin başlığı (ştat və ya saat hesabı) yoxdur"),
    "header_incomplete": S_("Başlıqda hər semestr üçün «Mühazirə», «Məşğələ» və «Laboratoriya», iki «Cəmi» və «İl ərzində cəmi» sütunu olmalıdır"),
    "title_damaged": S_("Sütunun başlığı pozulub ({x}); digər başlıqlardakı ad götürüldü: {y}"),
    "title_unknown": S_("Sütunun başlığı tanınmadı: {x}"),
    "semester_labels": S_("Semestr yazıları sütunların düzülüşünə uyğun gəlmir"),
    "total_missing": S_("Bölmənin «Cəmi» sətri tapılmadı"),
    "total_text": S_("«Cəmi» sətrində ədəd olmayan dəyər var: {x}"),
    "total_error": S_("«Cəmi» sətrində xəta dəyəri var ({x}); sətirlərdən hesablanan cəm: {y}"),
    "t1": S_("{x} sütununun cəmi sətirlərin cəminə bərabər deyil: yazılıb {a}, hesablanıb {b}"),
    "t2": S_("Semestr və il cəmləri bir-birinə uyğun gəlmir: yazılıb {a}, hesablanıb {b}"),
    "t3": S_("Oxunan dərslərin saatı «Cəmi» sətrinə uyğun gəlmir: yazılıb {a}, oxunub {b}"),
    "year_conflict": S_("Tədris ili faylın tədris ilindən fərqlidir: {x} (faylda {y})"),
    "after_total": S_("«Cəmi» sətrindən sonra, növbəti bölmənin başlığından əvvəl məlumat sətri var"),
    "phd_teaching": S_("«Aspirantlara dərs» sütununda saat var: bunun cədvələ salınan dərs olub-olmadığını kafedra bildirməlidir"),
    "no_units": S_("Vərəqdə məlumat sətirləri var, lakin heç bir dərs oxunmadı"),
    "code_wrong": S_("Qrup kodu düzgün görünmür: {x}"),
    "not_in_summary": S_("Blok arayış cədvəlində yoxdur: kafedranın cəminə daxil deyil"),
    "sheet_unknown": S_("Vərəqin növü tanınmadı; oxunmadı"),
    # notes
    "outside": S_("Formanın sütunlarından kənarda dəyər var: {x}"),
    "hidden_row": S_("Gizli sətirdə dəyər var: {x}"),
    "spacer": S_("Başlıqsız sütunda dəyər var; yükə daxil edilmir: {x}"),
    "join_value": S_("«Birləşmənin işarəsi» sütununda dəyər var; nəzərə alınmır: {x}"),
    "join_merge": S_("«Birləşmənin işarəsi» sütununda boş birləşdirilmiş xana var"),
    "stray_text": S_("Saat sütununda mətn var; sətir məlumat sətri sayılmır: {x}"),
    "item_only": S_("Sətirdə yalnız sıra nömrəsi var"),
    "group_no_class": S_("Qrup yazılıb, lakin nə dərsi, nə də başqa yükü var: {x}"),
    "row_total": S_("Sətrin cəmi hesablanan cəmə bərabər deyil: yazılıb {a}, hesablanıb {b}"),
    "exam_diff": S_("İmtahan saatı tələbə sayının üçdə birinə bərabər deyil: yazılıb {a}, gözlənilən {b}"),
    "mixed_semester": S_("Sətrin dərsi olmayan semestrdə yükü var: sütun səhv seçilmiş ola bilər"),
    "label_over_title": S_("Sətrin adı sütunun başlığına uyğun gəlmir; yükün növü sətrin adına görə götürüldü: {x}"),
    "load_merge_subjects": S_("Birləşdirilmiş yük xanası bir neçə fənnin sətirlərini əhatə edir"),
    "empty_merge": S_("Saat sütunlarında boş birləşdirilmiş xana var"),
    "class_elsewhere": S_("Boş birləşdirilmiş dərs xanası: dərs bu faylda tapılmadı (başqa faylda ola bilər)"),
    "title_text": S_("Blokun başlıq sətrində gözlənilməyən mətn var: {x}"),
    "labels_absent": S_("Semestr yazıları yoxdur; semestr sütunların düzülüşünə görə təyin edildi"),
    "no_patronymic": S_("Müəllimin ata adı «oğlu» və ya «qızı» ilə yazılmayıb: {x}"),
    "person_suffix": S_("Müəllimin adından sonra mötərizədə qeyd var: {x}"),
    "sheet_name": S_("Vərəqin adındakı söz vərəqin xanalarında yoxdur: {x}"),
    "zero_load": S_("Vərəqdə yük yoxdur"),
    "students_differ": S_("Qrupun tələbə sayı sətirlərdə fərqlidir: {x} — {y}"),
    "students_missing": S_("Dərs sətrində tələbə sayı yazılmayıb: {x}"),
    "unclassified": S_("Xana heç bir qaydaya uyğun gəlmir: {x}"),
    "separator": S_("Bloklar arasında dəyər var: {x}"),
    "doctoral_title": S_("«Buraxılış işi» başlıqlı sütun doktorantura yükü kimi oxunur"),
    "supervisor": S_("Rəhbərlik sətrində başqa şəxsin adı var; yük yazıldığı blokda saxlanılır: {x}"),
    "counterpart_outside": S_("Digər müəllim bu faylda yoxdur: {x}"),
    "counterpart_contradicted": S_("Digər müəllimin vərəqində bu fənn və qrup üzrə dərs tapılmadı: {x}"),
    "counterpart_no_class": S_("Digər müəllim dərsi olmayan sətirdə yazılıb: {x}"),
    "summary_category": S_("Ştat sətrindəki iş növü arayış cədvəlindəkindən fərqlidir; arayış cədvəli əsas götürüldü: {x}"),
    "summary_position": S_("Elmi dərəcə və ya vəzifə arayış cədvəlindəkindən fərqlidir: {x}"),
    "summary_list": S_("Arayış cədvəlinin yanında əlavə siyahı var: {x} xana"),
    "summary_unlinked": S_("Arayış cədvəlinin sətri heç bir blokla əlaqələndirilmədi"),
    "sheet_totals": S_("Vərəqin ümumi cəm sətri blokların cəminə bərabər deyil: {x}"),
    "formula_range": S_("«Cəmi» sətrinin düsturları bölmənin sətirlərini düzgün əhatə etmir ({x} xana); cəm sətirlərdən hesablanıb"),
    "formula_contact": S_("Auditoriya saatı başqa xanalardan düsturla hesablanıb: {x}"),
    "duplicate_rows": S_("Eyni sətir iki dəfə yazılıb; hər ikisi saxlanıldı"),
    "after_footer": S_("Kafedra müdirinin imza sətrindən sonra dəyər var: {x}"),
    # sheets
    "sheet_hidden": S_("Gizli vərəq: oxunur və siyahıda göstərilir, lakin idxal olunmur"),
    "sheet_summary": S_("Arayış cədvəli: yalnız yoxlama üçün oxunur"),
    "sheet_list": S_("Müəllimlərin siyahısı: idxal olunmur"),
    "sheet_empty": S_("Boş vərəq"),
    "sheet_form": S_("Forma №3 vərəqi"),
}


def _m(code: str, **p) -> dict:
    return E(MSG[code], **{k: (f"{v:g}" if isinstance(v, float) else str(v))[:120] for k, v in p.items()})


# ---------------------------------------------------------------- the result (docs/forms/forma-3.md, "Oxunan məlumat")
@dataclass
class SheetInfo:
    index: int
    name: str
    state: str                                   # visible | hidden | veryHidden
    cls: str                                     # form-A | form-B | summary | list | empty | unknown
    imported: bool
    reason: dict
    rows: int = 0                                # data rows read
    units: int = 0
    hours: float = 0.0                           # contact hours


@dataclass
class Post:
    ref: str                                     # the staff-line or section-label cell: "#0!A21"
    sheet: int
    layout: str
    rows: tuple[int, int] | None = None          # first..last data row (1-based)
    total_ref: str | None = None
    ratio_ref: str | None = None
    staff_text: str = ""
    teacher_raw: str = ""
    teacher: str | None = None
    degree: str | None = None
    position: str | None = None
    fraction: float | None = None
    employment: str | None = None                # main | internal | external | substitute-unspecified | None
    pay: str = "staff"                           # staff | hourly
    vacancy: bool = False
    vacancy_area: str | None = None
    consultant: bool = False
    year_text: str = ""
    year: str | None = None
    year_conflict: bool = False
    second_post_of: str | None = None
    sheet_name_tokens: list[str] = field(default_factory=list)
    hidden: bool = False                         # on a hidden sheet: listed, never imported
    blocked: bool = False                        # a blocking conflict or a failed control: nothing of it is applied
    year_total: float | None = None
    contact_hours: float = 0.0
    units: int = 0
    controls: dict = field(default_factory=dict)  # {"T1": bool, "T2": bool, "T3": bool}


@dataclass
class Unit:
    post: str
    sheet: int
    teacher: str | None
    hourly: bool
    vacancy: bool
    fraction: float | None
    subject_raw: str
    subject_key: str
    subject_core: str
    semester: str                                # payiz | yaz
    kind: str                                    # lecture | seminar | lab
    hours: float
    groups: list[dict]                           # {code_raw, code, students, row}
    students_total: int
    joint: bool
    anchor: str
    merge: str | None
    member_rows: list[int]
    counterparts: list[dict] = field(default_factory=list)       # {name, cell}
    flags: list[dict] = field(default_factory=list)              # {flag, cell}
    hidden: bool = False


@dataclass
class LoadLine:
    post: str
    sheet: int
    semester: str | None
    kind: str
    hours: float
    subject_raw: str
    cell: str
    groups: list[dict]
    students_total: int
    anchor: str
    merge: str | None


@dataclass
class Link:
    source: str                                  # the spec's "from": a unit anchor, an empty merge or a counterpart cell
    to: str | None
    basis: str                                   # subject_core+groups+semester | empty_merge_mirror | at_name | load_merge_across_subjects
    level: str                                   # info | note


@dataclass
class Note:
    cell: str
    text: str
    code: str
    message: dict
    post: str | None = None


@dataclass
class Conflict:
    cell: str
    code: str
    message: dict
    blocking: bool
    post: str | None = None
    data: dict = field(default_factory=dict)


@dataclass
class Control:
    scope: str                                   # post | sheet | file
    ref: str
    check: str                                   # T1 … T6
    expected: float | None
    found: float | None
    ok: bool


@dataclass
class Form:
    layout: str | None = None                    # A | B
    year: str | None = None
    department: str = ""
    sheets: list[SheetInfo] = field(default_factory=list)
    posts: list[Post] = field(default_factory=list)
    units: list[Unit] = field(default_factory=list)
    load: list[LoadLine] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    controls: list[Control] = field(default_factory=list)
    cells: dict = field(default_factory=dict)    # G9: how many non-empty cells of the form sheets ended in each place
    unclassified: int = 0                        # cells no rule placed (each is also a note): must be 0

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- the grid of one sheet
class Grid:
    def __init__(self, sheet: Sheet, index: int):
        self.sheet, self.i, self.rows = sheet, index, sheet.rows
        self.h = len(self.rows)
        self.w = max((len(r) for r in self.rows), default=0)
        self.cover: dict[tuple[int, int], tuple[int, int, int, int]] = {}
        self.merges: list[tuple[int, int, int, int]] = []
        self.used: dict[tuple[int, int], str] = {}
        n = 0
        for r1, c1, r2, c2 in sheet.merges:
            r2, c2 = min(r2, self.h - 1), min(c2, self.w - 1)          # the part of a merge that can hold a value
            if r1 > r2 or c1 > c2 or (r1, c1) == (r2, c2) or r1 < 0 or c1 < 0:
                continue
            n += (r2 - r1 + 1) * (c2 - c1 + 1)
            if n > MAX_COVER:
                raise FormError(S_("Faylda birləşdirilmiş xanalar həddindən artıq çoxdur"))
            m = (r1, c1, r2, c2)
            self.merges.append(m)
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    self.cover[(r, c)] = m

    def t(self, r: int, c: int | None) -> str:
        if c is None or not 0 <= r < self.h:
            return ""
        row = self.rows[r]
        return row[c].strip() if 0 <= c < len(row) else ""

    def filled(self, r: int) -> list[int]:
        return [c for c, v in enumerate(self.rows[r]) if v.strip()] if 0 <= r < self.h else []

    def ref(self, r: int, c: int, r2: int | None = None, c2: int | None = None) -> str:
        a = f"#{self.i}!{col_name(c)}{r + 1}"
        return a if r2 is None or (r2, c2) == (r, c) else f"{a}:{col_name(c2 if c2 is not None else c)}{r2 + 1}"

    def mref(self, r: int, c: int) -> str | None:
        m = self.cover.get((r, c))
        return self.ref(m[0], m[1], m[2], m[3]) if m else None

    def use(self, r: int, c: int | None, cat: str):
        if c is not None and self.t(r, c):
            self.used.setdefault((r, c), cat)

    def use_row(self, r: int, cat: str, c1: int = 0, c2: int | None = None):
        for c in self.filled(r):
            if c1 <= c <= (self.w if c2 is None else c2):
                self.use(r, c, cat)


# ---------------------------------------------------------------- header titles (H1, H3, H5, H7 and the table of §8)
SUBJECT = tuple(key(x) for x in ("Fənlər", "FƏNNİN ADI"))
TITLES: tuple[tuple[str, str, str | None], ...] = tuple((key(p), role, kind) for p, role, kind in (
    ("İl ərzində cəmi", "year", None), ("Cəmi", "total", None),
    ("Mühazirə", "contact", "lecture"), ("Məşğələ", "contact", "seminar"), ("Laboratoriya", "contact", "lab"),
    ("Məsləhət", "load", "consultation"), ("Məqbul", "load", "credit"),
    ("İmtahan sual", "load", "exam_prep"), ("İmtahan", "load", "exam"),
    ("Kurs layihəsi", "load", "course_project"), ("Referat", "load", "essay"), ("Magistrların işi", "load", "master_work"),
    ("Magistr dissertasiyasına r", "load", "master_supervision"), ("Magistr dissertasiyasına m", "load", "master_consulting"),
    ("Tədqiqat işinin aparılması", "load", "research"), ("Layihələrin idarə olunması", "load", "project_management"),
    ("Təcrübə", "load", "practice"), ("Aspirantlara dərs", "load", "phd_teaching"), ("Doktorantura", "load", "doctoral"),
    ("DAK", "load", "state_exam"), ("Buraxılış işi", "load", "graduation"), ("Müəllimlərin dərs", "load", "class_visits"),
    ("Digər kafedranın dərs yükü", "load", "other_department"), ("Digər dərs yü", "load", "other_load")))
FIXED = tuple((key(p), role) for p, role in (("Sıra", "seq"), ("№", "seq"), ("Qrup", "group"), ("Tələbələrin sayı", "students"),
                                             ("Birləşmənin işarəsi", "join")))
SUPERVISION = ("practice", "master_work", "master_supervision", "master_consulting", "doctoral", "graduation", "research",
               "project_management")


def _title(k: str, layout: str) -> tuple[str, str | None] | None:
    """(role, kind) of a column title, matched by prefix; None for an unknown one."""
    if not k:
        return None
    if k in SUBJECT:
        return "subject", None
    for prefix, role in FIXED:
        if k.startswith(prefix):
            return role, None
    if k.startswith(key("Digər dərs yü")) and key("müəllim") in k:
        return "counter", None                                   # H7: the colleagues' names, never hours
    for prefix, role, kind in TITLES:
        if k.startswith(prefix):
            if layout == "A" and kind == "graduation":
                return role, "doctoral"                          # H5: layout A's "Buraxılış işi" column holds doctoral load
            return role, kind
    return None


@dataclass
class Col:
    c: int
    role: str                                    # contact | load
    sem: str | None
    kind: str
    title: str


@dataclass
class Cols:
    left: int = 0
    right: int = 0
    seq: int | None = None
    subject: int = -1                            # -1: the header has no such column
    group: int = -1
    students: int | None = None
    join: int | None = None
    counter: int | None = None
    year: int | None = None
    hours: dict[int, Col] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)
    spacers: list[int] = field(default_factory=list)
    problems: list[tuple[str, int, dict, bool]] = field(default_factory=list)     # (code, column, params, blocking)
    doctoral_title: int | None = None

    def of(self, sem: str | None) -> list[int]:
        return [c for c, x in self.hours.items() if x.sem == sem]

    @property
    def usable(self) -> bool:
        return self.subject >= 0 and self.group >= 0


def _band(g: Grid, h: int, cs: int) -> list[int]:
    """H1: the header row and every row its subject title's vertical merge covers."""
    m = g.cover.get((h, cs))
    return list(range(h, (m[2] if m and m[1] == m[3] else h) + 1))


def _raw_titles(g: Grid, band: list[int]) -> dict[int, str]:
    out = {}
    for c in range(g.w):
        for r in reversed(band):
            if g.t(r, c):
                out[c] = g.t(r, c)
                break
    return out


def _header_row(g: Grid, r: int) -> int | None:
    """The subject title's column when row r is a header row (it also holds the group title)."""
    cs = next((c for c in g.filled(r) if key(g.t(r, c)) in SUBJECT), None)
    if cs is None or not any(key(g.t(r, c)).startswith(key("Qrup")) for c in g.filled(r)):
        return None
    return cs


def _columns(g: Grid, band: list[int], layout: str, consensus: dict[int, str], numbers: int | None) -> Cols:
    titles = _raw_titles(g, band)
    known = {c: _title(key(v), layout) for c, v in titles.items()}
    cols = Cols()
    firm = [c for c, x in known.items() if x]
    if not firm:
        return cols
    cols.left = min(firm)
    cols.right = max(max(firm), max((c for c in consensus if c >= cols.left), default=0))
    what: dict[int, tuple[str, str | None]] = {}
    for c in range(cols.left, cols.right + 1):
        hit, raw = known.get(c), titles.get(c, "")
        if hit is None and consensus.get(c):                      # H5: a damaged title takes the name the others agree on
            numbered = numbers is None or not g.t(numbers, c) or g.t(numbers, c) == str(c - cols.left + 1)
            if numbered:
                hit = _title(consensus[c], layout)
                cols.problems.append(("title_damaged", c, {"x": raw or "—", "y": consensus[c]}, False))
        if hit is None and raw:
            cols.problems.append(("title_unknown", c, {"x": raw}, True))
        if hit:
            what[c] = hit
    for c, (role, _) in what.items():
        if role in ("seq", "subject", "group", "students", "join") and getattr(cols, role) in (None, -1):
            setattr(cols, role, c)
    start = max(x for x in (cols.students, cols.join, cols.group, cols.subject, cols.left) if x is not None) + 1
    grp = 0                                                       # H3: 0 autumn, 1 spring, 2 after the second Cəmi, 3 after the year
    for c in range(start, cols.right + 1):
        role, kind = what.get(c, ("spacer", None))
        if role == "total" and grp < 2:
            cols.totals[SEMESTERS[grp]] = c
            grp += 1
        elif role == "year" and cols.year is None:
            cols.year, grp = c, 3
        elif role == "counter":
            cols.counter = c
        elif role in ("contact", "load") and (grp < 2 or kind in ("other_department", "other_load")):
            cols.hours[c] = Col(c, role, SEMESTERS[grp] if grp < 2 else None, kind or "", titles.get(c, ""))
            if layout == "A" and key(titles.get(c, "")).startswith(key("Buraxılış işi")):
                cols.doctoral_title = c
        elif role == "spacer" and not titles.get(c):
            cols.spacers.append(c)
        elif titles.get(c) and not any(p[1] == c for p in cols.problems):
            cols.problems.append(("title_unknown", c, {"x": titles[c]}, True))
    per = Counter((x.sem, x.kind) for x in cols.hours.values() if x.role == "contact")
    if (not cols.usable or cols.year is None or len(cols.totals) != 2
            or any(per.get((s, k)) != 1 for s in SEMESTERS for k in CONTACT)):
        cols.problems.append(("header_incomplete", max(cols.subject, cols.left), {}, True))
    return cols


def _labels(g: Grid, r: int, cols: Cols) -> str:
    """H4: "ok", "absent" or "bad" for the semester labels of row r against the column groups."""
    span: dict[str, tuple[int, int]] = {}
    for c in g.filled(r):
        k = key(g.t(r, c))
        if c > cols.right or "semestr" not in k:
            continue
        sem = "payiz" if "payiz" in k else "yaz" if "yaz" in k else None
        m = g.cover.get((r, c))
        if sem and sem not in span:
            span[sem] = (m[1], m[3]) if m else (c, c)
    if not span:
        return "absent"
    if len(span) < 2 or span["payiz"][0] >= span["yaz"][0]:
        return "bad"
    for sem in SEMESTERS:
        mine = cols.of(sem)
        if 2 * sum(span[sem][0] <= c <= span[sem][1] for c in mine) <= len(mine):
            return "bad"
    return "ok"


# ---------------------------------------------------------------- the reader's state
class _Reader:
    def __init__(self):
        self.form = Form()
        self.grids: dict[int, Grid] = {}
        self.empty: list[dict] = []                               # J3: empty vertical contact merges
        self.at: list[dict] = []                                  # O1: counterpart names per row
        self.totals: dict[str, dict[int, float]] = {}             # post ref -> its total row by column (recomputed where unreadable)
        self.cols: dict[str, Cols] = {}                           # post ref -> its columns
        self.sheet_totals: dict[int, int] = {}                    # layout A: sheet -> the row of the department totals

    def note(self, g: Grid, r: int, c: int, code: str, post: Post | None = None, cell: str | None = None, **p):
        text = g.t(r, c)
        self.form.notes.append(Note(cell or g.ref(r, c), text[:200], code, _m(code, **p), post.ref if post else None))
        g.use(r, c, "note")

    def conflict(self, g: Grid, r: int, c: int, code: str, blocking: bool, post: Post | None = None, cell: str | None = None,
                 data: dict | None = None, **p):
        new = Conflict(cell or g.ref(r, c), code, _m(code, **p), blocking, post.ref if post else None, data or {})
        if new not in self.form.conflicts:                        # a row with two classes names its bad cell once
            self.form.conflicts.append(new)
        g.use(r, c, "conflict")


def _int(v: float | None) -> bool:
    return v is not None and abs(v - round(v)) < 1e-9


LABEL_KIND = ((re.compile(r"^td\b|^td-"), "doctoral"), (re.compile(r"\b(md|mr) rəhbərlik|magistr dissertasiya"), "master_supervision"),
              (re.compile(r"təcrübə"), "practice"), (re.compile(r"doktorant"), "doctoral"))
SUPERVISOR = re.compile(r"elmi rəhbər\w*\s*:?\s*([^()]+)", re.IGNORECASE)


def _row_kind(subject: str) -> str | None:
    k = key(subject)
    return next((kind for rx, kind in LABEL_KIND if rx.search(k)), None)


def _fits(label: str, column: str) -> bool:
    family = {"master_supervision": ("master_supervision", "master_consulting", "master_work"), "doctoral": ("doctoral",),
              "practice": ("practice",)}
    return column in family.get(label, (label,))


# ---------------------------------------------------------------- data rows of one post (R1–R6, J1–J5, L1–L4, T1–T4)
def _rows(R: _Reader, g: Grid, post: Post, cols: Cols, r0: int, r1: int, total: int | None):
    form, hours = R.form, cols.hours
    info: dict[int, dict] = {}
    vals: dict[int, dict[int, float]] = {}
    for r in range(r0, r1):
        filled = g.filled(r)
        if not filled:
            continue
        hidden = r in g.sheet.hidden_rows
        for c in filled:
            if c > cols.right or c < cols.left:
                R.note(g, r, c, "hidden_row" if hidden else "outside", post, x=g.t(r, c))
            elif hidden:
                form.notes.append(Note(g.ref(r, c), g.t(r, c)[:200], "hidden_row", _m("hidden_row", x=g.t(r, c)), post.ref))
        subject = g.t(r, cols.subject)
        m = g.cover.get((r, cols.subject))
        if not subject and m and m[1] == m[3] == cols.subject and m[0] >= r0:
            subject = g.t(m[0], m[1])                             # R2: the vertical merge over the row, nothing else
        d_text = g.t(r, cols.students)
        d = tx.number(d_text) if d_text else None
        if d_text and d is None:
            R.conflict(g, r, cols.students or 0, "students_text", True, post, x=d_text)
        row: dict[int, float] = {}
        texts: list[int] = []
        for c in hours:
            mm, text = g.cover.get((r, c)), g.t(r, c)
            if mm and (mm[0], mm[1]) != (r, c):
                if text:                                          # G2
                    R.conflict(g, r, c, "covered_value", True, post, x=text)
                continue
            if not text:
                continue
            v = tx.number(text)
            if v is None:
                texts.append(c)
            elif mm and mm[1] != mm[3]:
                if v:
                    R.conflict(g, r, c, "merge_ambiguous", True, post, cell=g.mref(r, c))
                g.use(r, c, "structure")
            else:
                row[c] = v
        group = g.t(r, cols.group)
        if texts and not subject and not group and not any(row.values()):
            for c in texts:                                       # R1.13: a stray text is not a data row (G1)
                R.note(g, r, c, "stray_text", post, x=g.t(r, c))
            texts = []
        for c in texts:
            R.conflict(g, r, c, "hours_text", True, post, x=g.t(r, c))
        info[r] = {"subject": subject, "group": group, "students": d, "d_text": d_text, "seq": g.t(r, cols.seq), "hidden": hidden}
        vals[r] = row
    sums: dict[int, float] = defaultdict(float)
    class_sems: dict[int, set] = defaultdict(set)                 # row -> semesters in which it has a class (own or merged)
    loaded: set[int] = set()                                      # rows that carry load (own or merged)
    units: list[Unit] = []
    loads: list[tuple[int, int, LoadLine]] = []

    def members(r: int, c: int) -> list[int]:
        mm = g.cover.get((r, c))
        if not mm:
            return [r]
        if mm[2] >= r1:
            R.conflict(g, r, c, "merge_outside", True, post, cell=g.mref(r, c))
        return [x for x in range(mm[0], min(mm[2], r1 - 1) + 1)]

    def groups_of(rows: list[int]) -> list[dict]:
        return [{"code_raw": info[x]["group"], "code": tx.group_code(info[x]["group"]),
                 "students": int(info[x]["students"]) if _int(info[x]["students"]) else None, "row": x + 1}
                for x in rows if x in info and info[x]["group"]]

    missing_said: set[int] = set()

    def need_subject(r: int, c: int):
        if info[r]["subject"] or r in missing_said:
            return
        missing_said.add(r)
        above = next((info[x]["subject"] for x in range(r - 1, r0 - 1, -1) if x in info and info[x]["subject"]), "—")
        R.conflict(g, r, c, "subject_missing", True, post, cell=g.ref(r, cols.subject), x=above)

    for r, row in vals.items():
        me = info[r]
        for c, v in row.items():
            col = hours[c]
            sums[c] += v
            if not v:
                g.use(r, c, "structure")
                continue
            rows = members(r, c)
            groups = groups_of(rows)
            need_subject(r, c)
            if col.role == "contact":
                u = Unit(post.ref, g.i, post.teacher, post.pay == "hourly", post.vacancy, post.fraction, me["subject"],
                         tx.subject_key(me["subject"]), tx.subject_core(me["subject"]), col.sem or "", col.kind, v, groups,
                         sum(x["students"] or 0 for x in groups), len(groups) > 1, g.ref(r, c), g.mref(r, c), [x + 1 for x in rows],
                         hidden=post.hidden)
                if not groups:                                    # R5
                    u.flags.append({"flag": "group_missing", "cell": g.ref(r, cols.group)})
                    R.conflict(g, r, c, "group_missing", True, post, cell=g.ref(r, cols.group))
                if not me["subject"]:
                    u.flags.append({"flag": "subject_missing", "cell": g.ref(r, cols.subject)})
                for x in rows:
                    if x not in info or not info[x]["group"]:
                        continue
                    dx = info[x]["students"]
                    if dx is None and not info[x]["d_text"]:      # G8
                        u.flags.append({"flag": "students_missing", "cell": g.ref(x, cols.students or 0)})
                        form.notes.append(Note(g.ref(x, cols.students or 0), "", "students_missing",
                                               _m("students_missing", x=info[x]["group"]), post.ref))
                    elif dx is not None and not _int(dx):         # X13
                        R.conflict(g, x, cols.students or 0, "students_fraction", True, post, x=info[x]["d_text"])
                if v % 15:
                    u.flags.append({"flag": "fractional_week" if v % 7.5 == 0 else "hours_not_multiple_of_15", "cell": u.anchor})
                if len(rows) > 1 and len({" ".join(info[x]["subject"].split()) for x in rows if x in info}) > 1:
                    R.conflict(g, r, c, "merge_subjects", True, post, cell=u.merge)          # J4
                if any(info[x]["hidden"] for x in rows if x in info):
                    u.flags.append({"flag": "hidden_row", "cell": u.anchor})
                f = g.sheet.formulas.get((r, c))
                if f is not None and (f == "" or re.search(r"[A-Z]+\$?\d", f)):
                    form.notes.append(Note(u.anchor, f[:80], "formula_contact", _m("formula_contact", x=f or "…"), post.ref))    # K5
                for x in rows:
                    class_sems[x].add(col.sem)
                units.append(u)
                g.use(r, c, "unit")
            else:
                kind = col.kind
                label = _row_kind(me["subject"]) if kind in SUPERVISION else None
                if label and not _fits(label, kind):              # H5: the row's own label decides
                    form.notes.append(Note(g.ref(r, c), g.t(r, c), "label_over_title", _m("label_over_title", x=col.title), post.ref))
                    kind = label
                count = sum(x["students"] or 0 for x in groups) if groups else int(me["students"]) if _int(me["students"]) else 0
                ll = LoadLine(post.ref, g.i, col.sem, kind, v, me["subject"], g.ref(r, c), groups, count, g.ref(r, c), g.mref(r, c))
                if kind == "phd_teaching":                        # L3
                    R.conflict(g, r, c, "phd_teaching", True, post)
                if kind == "exam" and groups and all(x["students"] is not None for x in groups) and abs(v - count / 3) > 0.05:
                    form.notes.append(Note(ll.cell, g.t(r, c), "exam_diff", _m("exam_diff", a=round(v, 3), b=round(count / 3, 3)), post.ref))
                if len(rows) > 1 and len({tx.subject_key(info[x]["subject"]) for x in rows if x in info}) > 1:
                    form.notes.append(Note(ll.merge or ll.cell, "", "load_merge_subjects", _m("load_merge_subjects"), post.ref))
                    form.links.append(Link(ll.merge or ll.cell, None, "load_merge_across_subjects", "note"))
                sup = SUPERVISOR.search(me["subject"])
                if sup and kind in SUPERVISION and (post.vacancy or not _same_person(sup.group(1), post.teacher or "")):
                    form.notes.append(Note(g.ref(r, cols.subject), "", "supervisor", _m("supervisor", x=sup.group(1).strip()), post.ref))
                loaded.update(rows)
                loads.append((r, c, ll))
                g.use(r, c, "load")
    # K7: load in a semester in which the row has no class, while it has one in the other
    for r, _, ll in loads:
        if ll.semester and class_sems.get(r) and ll.semester not in class_sems[r]:
            form.notes.append(Note(ll.cell, "", "mixed_semester", _m("mixed_semester"), post.ref))
    # counterparts (O1): a merged cell names the colleague for every row it covers
    if cols.counter is not None:
        named: dict[int, list[dict]] = {}
        for r in info:
            top = g.cover.get((r, cols.counter), (r, cols.counter))
            text = g.t(top[0], top[1])
            g.use(r, cols.counter, "unit" if class_sems.get(r) else "note")
            if text:
                named[r] = [{"name": n, "cell": g.ref(top[0], top[1])} for n in _names(text)]
                if not class_sems.get(r) and (top[0], top[1]) == (r, cols.counter):
                    form.notes.append(Note(g.ref(r, cols.counter), text[:200], "counterpart_no_class",
                                           _m("counterpart_no_class", x=text), post.ref))
        for u in units:
            seen = set()
            for x in u.member_rows:
                for n in named.get(x - 1, []):
                    if (n["name"], n["cell"]) not in seen:
                        seen.add((n["name"], n["cell"]))
                        u.counterparts.append(n)
                        R.at.append({"unit": u, "name": n["name"], "cell": n["cell"], "row": x})
    # every other cell of a data row; the per-row totals (T4)
    previous = None
    for r, me in info.items():
        row = vals[r]
        busy = any(row.values()) or r in loaded or bool(class_sems.get(r))
        cat = "unit" if class_sems.get(r) else "load" if r in loaded or any(row.values()) else "structure"
        if not busy:
            if me["group"]:                                       # R6: a group with no class and no load
                R.note(g, r, cols.group, "group_no_class", post, x=me["group"])
            elif me["seq"] and not me["subject"] and not me["d_text"]:
                R.note(g, r, cols.seq or 0, "item_only", post)
        for cc in (cols.seq, cols.subject, cols.group, cols.students):
            g.use(r, cc, cat)
        if cols.join is not None and g.t(r, cols.join):           # B7
            R.note(g, r, cols.join, "join_value", post, x=g.t(r, cols.join))
        for c in cols.spacers:
            if g.t(r, c):                                         # the untitled column is never load
                R.note(g, r, c, "spacer", post, x=g.t(r, c))
        for sem, tc in (*cols.totals.items(), ("year", cols.year)):
            mm = g.cover.get((r, tc)) if tc is not None else None
            if tc is None or (mm and (mm[0], mm[1]) != (r, tc)):
                continue
            span = range(mm[0], min(mm[2], r1 - 1) + 1) if mm else (r,)
            mine = [c for c, x in hours.items() if (x.sem == sem if sem != "year" else x.sem is not None)]
            found = sum(vals.get(x, {}).get(c, 0.0) for x in span for c in mine)
            text = g.t(r, tc)
            cell = tx.number(text) if text else 0.0               # a blank per-row total counts as 0
            if cell is None or abs(cell - found) > TOL:
                form.notes.append(Note(g.ref(r, tc), text[:60], "row_total", _m("row_total", a=text or "0", b=round(found, 3)), post.ref))
            g.use(r, tc, "total")
        sig = (me["subject"], me["group"], me["d_text"], tuple(sorted(row.items())))
        if previous == sig and any(row.values()) and me["subject"]:
            form.notes.append(Note(g.ref(r, cols.subject), "", "duplicate_rows", _m("duplicate_rows"), post.ref))
        previous = sig
    # merges with an empty top-left cell (J3, B7)
    for mm in g.merges:
        if not r0 <= mm[0] < r1 or g.t(mm[0], mm[1]):
            continue
        if mm[1] == mm[3] == cols.join:
            form.notes.append(Note(g.ref(*mm), "", "join_merge", _m("join_merge"), post.ref))
        elif mm[1] == mm[3] and mm[1] in hours and hours[mm[1]].role == "contact":
            rows = [x for x in range(mm[0], min(mm[2], r1 - 1) + 1)]
            R.empty.append({"post": post.ref, "ref": g.ref(*mm), "sem": hours[mm[1]].sem, "kind": hours[mm[1]].kind,
                            "groups": {tx.group_code(info[x]["group"]) for x in rows if x in info and info[x]["group"]},
                            "cores": {tx.subject_core(info[x]["subject"]) for x in rows if x in info}})
        elif mm[1] != mm[3] and any(c in hours for c in range(mm[1], mm[3] + 1)):
            form.notes.append(Note(g.ref(*mm), "", "empty_merge", _m("empty_merge"), post.ref))
    post.rows = (min(info) + 1, max(info) + 1) if info else None
    post.units = len(units)
    post.contact_hours = sum(u.hours for u in units)
    form.units += units
    form.load += [ll for _, _, ll in loads]
    _controls(R, g, post, cols, r0, total, sums, units, [(c, ll) for _, c, ll in loads], vals)


def _controls(R: _Reader, g: Grid, post: Post, cols: Cols, r0: int, total: int | None, sums: dict[int, float],
              units: list[Unit], loads: list[tuple[int, LoadLine]], vals: dict[int, dict[int, float]]):
    """T1 (columns), T2 (semesters, H6) and T3 (units and load cover the totals) of one post."""
    form, hours = R.form, cols.hours
    if total is None:
        R.form.conflicts.append(Conflict(post.ref, "total_missing", _m("total_missing"), True, post.ref))
        post.controls = {"T1": False, "T2": False, "T3": False}
        for check in ("T1", "T2", "T3"):
            form.controls.append(Control("post", post.ref, check, None, None, False))
        post.year_total = sum(sums.values())
        R.totals[post.ref] = dict(sums)
        return
    post.total_ref = g.ref(total, cols.subject if g.t(total, cols.subject) else cols.left)

    def cell(c: int, recomputed: float) -> tuple[float, bool]:
        """A total-row cell: (value, readable). Blank is 0; an error value is recomputed and reported (K1)."""
        text = g.t(total, c)
        g.use(total, c, "total")
        if not text:
            return 0.0, True
        if tx.is_error(text):
            R.conflict(g, total, c, "total_error", False, post, x=text, y=round(recomputed, 3))
            return recomputed, False
        v = tx.number(text)
        if v is None:
            R.conflict(g, total, c, "total_text", True, post, x=text)
            return recomputed, False
        return v, True

    tot: dict[int, float] = {}
    ok1 = True
    for c, col in hours.items():
        tot[c], readable = cell(c, sums[c])
        if readable and abs(tot[c] - sums[c]) > TOL:
            ok1 = False
            R.conflict(g, total, c, "t1", True, post, x=f"{col_name(c)} ({col.title})", a=round(tot[c], 3), b=round(sums[c], 3))
    form.controls.append(Control("post", post.ref, "T1", round(sum(tot.values()), 4), round(sum(sums.values()), 4), ok1))
    ok2 = True
    sem_total: dict[str, float] = {}
    for sem in SEMESTERS:
        want = sum(tot[c] for c in cols.of(sem))
        tc = cols.totals.get(sem)
        sem_total[sem], readable = cell(tc, want) if tc is not None else (want, False)
        if readable and abs(sem_total[sem] - want) > TOL_SUM:
            ok2 = False
            R.conflict(g, total, tc or 0, "t2", True, post, a=round(sem_total[sem], 3), b=round(want, 3))
    want = sum(sem_total.values())
    year, readable = cell(cols.year, want) if cols.year is not None else (want, False)
    if readable and abs(year - want) > TOL_SUM:
        ok2 = False
        R.conflict(g, total, cols.year or 0, "t2", True, post, a=round(year, 3), b=round(want, 3))
    form.controls.append(Control("post", post.ref, "T2", round(year, 4), round(want, 4), ok2))
    ok3 = True
    read: dict[int, float] = defaultdict(float)
    by = {(x.sem, x.kind): c for c, x in hours.items() if x.role == "contact"}
    for u in units:
        read[by[(u.semester, u.kind)]] += u.hours
    for c, ll in loads:
        read[c] += ll.hours
    for c in hours:
        if abs(read[c] - tot[c]) > TOL:
            ok3 = False
            if abs(tot[c] - sums[c]) <= TOL:                       # otherwise T1 has said it already
                R.conflict(g, total, c, "t3", True, post, a=round(tot[c], 3), b=round(read[c], 3))
    contact = sum(tot[c] for c in by.values())
    form.controls.append(Control("post", post.ref, "T3", round(contact, 4), round(sum(u.hours for u in units), 4), ok3))
    post.controls = {"T1": ok1, "T2": ok2, "T3": ok3}
    post.year_total = year
    R.totals[post.ref] = {**tot, **{cols.totals[s]: sem_total[s] for s in cols.totals}, **({cols.year: year} if cols.year is not None else {})}
    for c in g.filled(total):                                     # the label, a students sum, the helper sums at the right (A12)
        g.use(total, c, "total" if c <= cols.right else "structure")
    # K3, K4: total-row formulas whose range is not the post's rows (the values are recomputed from the rows anyway)
    odd = 0
    for c in hours:
        f = g.sheet.formulas.get((total, c))
        m = re.fullmatch(r"SUM\(\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)\)", f or "")
        if not m:
            continue
        a, b = int(m.group(2)) - 1, int(m.group(4)) - 1
        mine = [r for r in vals if vals[r].get(c)]
        odd += a < r0 or b >= total or m.group(1) != col_name(c) or m.group(3) != col_name(c) or any(not a <= r <= b for r in mine)
    if odd:
        form.notes.append(Note(post.total_ref, "", "formula_range", _m("formula_range", x=odd), post.ref))


# ---------------------------------------------------------------- names
def _near(a: str, b: str) -> bool:
    """Equal, or one letter apart (the files spell the same surname with m/n, b/m, q/k)."""
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1 or min(len(a), len(b)) < 4:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = next((n for n in range(len(a)) if a[n] != b[n]), len(a))
    return a[i:] == b[i + 1:] if len(a) < len(b) else a[i + 1:] == b[i + 1:]


def _words(name: str) -> list[str]:
    drop = {key("oğlu"), key("qızı"), *tx.GENITIVE}
    return [w for w in (key(x) for x in tx.WORD.findall(name or "")) if w not in drop and len(w) > 1]


def _names(text: str) -> list[str]:
    """O1: the people a counterpart cell names, split on commas; a piece that is only a degree or a position
    (``t.ü.f.d., dosent …``) belongs to the name after it."""
    out: list[str] = []
    carry = ""
    for piece in (x.strip() for x in text.split(",")):
        if not piece:
            continue
        piece = f"{carry}, {piece}" if carry else piece
        if tx.person(piece).raw:
            out.append(piece)
            carry = ""
        else:
            carry = piece
    return out + ([carry] if carry else [])


def _same_person(a: str, b: str) -> bool:
    """Two written names of one person: at least two words (surname and name) agree, order free, one letter forgiven."""
    wa, wb = _words(a), _words(b)
    hits = sum(any(_near(x, y) for y in wb) for x in wa)
    return hits >= 2 or (hits == 1 and len(wa) == 1 and bool(wb))


# ---------------------------------------------------------------- layout A (A1–A13)
def _sheet_a(R: _Reader, g: Grid, hidden: bool) -> list[Post]:
    headers = [(r, cs) for r in range(g.h) for cs in [_header_row(g, r)] if cs is not None]
    raw = {r: _raw_titles(g, [r]) for r, _ in headers}
    consensus: dict[int, str] = {}
    for c in {c for t in raw.values() for c in t}:
        seen = {key(t[c]) for t in raw.values() if c in t and _title(key(t[c]), "A")}
        if len(seen) == 1 and sum(c in t and _title(key(t[c]), "A") is not None for t in raw.values()) > 1:
            consensus[c] = seen.pop()
    posts: list[Post] = []
    done = -1                                                     # the last row a block has consumed
    for n, (h, _) in enumerate(headers):
        limit = headers[n + 1][0] if n + 1 < len(headers) else g.h
        label = h - 1 if h - 1 > done and any("semestr" in key(g.t(h - 1, c)) for c in g.filled(h - 1)) else None
        srow = (label if label is not None else h) - 1
        if label is None and srow > done + 1 and not g.filled(srow):
            srow -= 1                                             # the label row is there but blank: the staff line is above it
        numbers = h + 1 if h + 1 < limit and g.filled(h + 1) and all(g.t(h + 1, c).isdigit() for c in g.filled(h + 1)) else None
        cols = _columns(g, [h], "A", consensus, numbers)
        if srow <= done or not g.t(srow, cols.left):              # A4: no staff line above it: the sheet's own header
            g.use_row(h, "header")
            r = h + 1
            while r < limit and g.filled(r) and _header_row(g, r) is None:
                if any("semestr" in key(g.t(r, c)) for c in g.filled(r)):
                    g.use_row(r, "structure")
                elif all(tx.number(g.t(r, c)) is not None or tx.is_error(g.t(r, c)) for c in g.filled(r)):
                    R.sheet_totals[g.i] = r                       # the department totals: a control only (T6)
                    R.cols[f"#{g.i}"] = cols
                    g.use_row(r, "total")
                else:
                    break
                r += 1
            done = max(done, r - 1)
            continue
        text = g.t(srow, cols.left)
        st = tx.staff(text)
        post = Post(g.ref(srow, cols.left), g.i, "A", staff_text=text, hidden=hidden)
        posts.append(post)
        R.cols[post.ref] = cols
        for r in range(done + 1, srow - 3):                       # A5: between a total row and the next block's titles
            for c in g.filled(r):
                R.note(g, r, c, "separator", x=g.t(r, c))
        for r in range(max(done + 1, srow - 3), srow):            # A2: the title rows are positional
            t = g.t(r, cols.left)
            if tx.year(t):
                post.year_text, post.year = t, tx.year(t)
            elif key("kafedra") in key(t):
                R.form.department = R.form.department or " ".join(t.split())
            elif t and key("universitet") not in key(t):
                R.note(g, r, cols.left, "title_text", post, x=t)
            g.use(r, cols.left, "post")
        g.use(srow, cols.left, "post")
        for r in (*range(max(done + 1, srow - 3), srow + 1), *([label] if label is not None else []), h, *([numbers] if numbers else [])):
            for c in g.filled(r):
                if c > cols.right:                                # H1: right of the form, never a title
                    R.note(g, r, c, "outside", post, x=g.t(r, c))
        if label is not None:
            g.use_row(label, "header", c2=cols.right)
        g.use_row(h, "header", c2=cols.right)
        if numbers is not None:
            g.use_row(numbers, "header", c2=cols.right)
        _post_staff(R, g, post, st, tx.person(st.rest) if st.kind in ("staff", "hourly") else None, srow, cols.left)
        _header_problems(R, g, post, cols, h, _labels(g, label, cols) if label is not None else "absent")
        start = (numbers if numbers is not None else h) + 1
        total = None
        if cols.usable:
            total = next((r for r in range(start, limit) if any(key(g.t(r, c)).startswith(key("Cəm"))
                                                                 for c in range(cols.left, (cols.students or cols.left) + 1))), None)
        end = total if total is not None else limit
        while total is None and end > start and (not g.filled(end - 1) or (g.cover.get((end - 1, cols.left)) or (0, 0, 0, 0))[3] > (cols.students or 0)):
            end -= 1                                              # no total row: stop before the next block's merged title rows
        if cols.usable:
            _rows(R, g, post, cols, start, end, total)
        done = total if total is not None else end - 1
    for r in range(done + 1, g.h):
        for c in g.filled(r):
            R.note(g, r, c, "separator", x=g.t(r, c))
    return posts


def _post_staff(R: _Reader, g: Grid, post: Post, st: tx.Staff, who: tx.Person | None, r: int, c: int):
    """Fill a post from its staff line or section label and the person it names (A6, B2, B3, P1, P3)."""
    post.fraction, post.employment = st.fraction, st.employment
    post.pay = "hourly" if st.kind == "hourly" else "staff"
    if st.kind == "vacancy":
        post.vacancy, post.vacancy_area = True, st.area
    if who is not None:
        post.teacher_raw, post.degree, post.position = who.raw, who.degree, who.position
        post.teacher = who.name
        post.consultant = key(who.position or "") == key("məsləhətçi professor")
        if not who.ok:
            R.conflict(g, r, c, "staff_unreadable" if post.layout == "A" else "teacher_unreadable", True, post, x=who.raw or post.staff_text)
        for _ in who.flags:
            R.form.notes.append(Note(g.ref(r, c), "", "no_patronymic", _m("no_patronymic", x=who.name or ""), post.ref))
        if who.suffix:
            R.form.notes.append(Note(g.ref(r, c), "", "person_suffix", _m("person_suffix", x=who.suffix), post.ref))
    elif st.kind == "unknown" and post.layout == "A":
        R.conflict(g, r, c, "staff_unreadable", True, post, x=post.staff_text)


def _header_problems(R: _Reader, g: Grid, post: Post, cols: Cols, h: int, labels: str):
    for code, c, params, blocking in cols.problems:
        R.form.conflicts.append(Conflict(g.ref(h, c), code, _m(code, **params), blocking, post.ref))
    if labels == "bad":
        R.form.conflicts.append(Conflict(g.ref(h, cols.left), "semester_labels", _m("semester_labels"), True, post.ref))
    elif labels == "absent":
        R.form.notes.append(Note(g.ref(h, cols.left), "", "labels_absent", _m("labels_absent"), post.ref))


# ---------------------------------------------------------------- layout B (B1–B9)
FOOTER = key("kafedrasının müdiri")


def _is_ratio(g: Grid, r: int, cols: Cols) -> bool:
    """B5: the ``Aktiv`` row under a total: only the spring-total and year-total cells."""
    filled = g.filled(r)
    allowed = {cols.totals.get("yaz"), cols.year}
    if not filled or any(c not in allowed for c in filled):
        return False
    return any(key(g.t(r, c)).startswith("aktiv") for c in filled) or filled == [cols.year]


def _is_zero(g: Grid, r: int, cols: Cols) -> bool:
    """R1.12: only the total cells, all zero."""
    filled = g.filled(r)
    allowed = {*cols.totals.values(), cols.year}
    return bool(filled) and all(c in allowed and tx.number(g.t(r, c)) == 0 for c in filled)


def _is_label(g: Grid, r: int, cols: Cols) -> bool:
    """B3: the subject cell opens a one-row merge that reaches the year total; nothing else in the row."""
    text = g.t(r, cols.subject)
    if not text or g.filled(r) != [cols.subject]:
        return False
    m = g.cover.get((r, cols.subject))
    reach = cols.year if cols.year is not None else cols.right
    return bool(m and m[0] == m[2] == r and m[1] == cols.subject and m[3] >= reach) or tx.staff(text).kind in ("staff", "hourly")


def _unlabelled_total(g: Grid, cols: Cols, a: int, b: int) -> int | None:
    """B5 (2): the first row with no subject and no group whose hour cells equal the column sums above it, and that has
    every hour cell or sits directly above the ratio row."""
    sums: dict[int, float] = defaultdict(float)
    for r in range(a, b):
        cells = {c: g.t(r, c) for c in cols.hours}
        numeric = {c: tx.number(v) for c, v in cells.items() if v}
        if (not g.t(r, cols.subject) and not g.t(r, cols.group) and numeric and all(v is not None for v in numeric.values())
                and all(abs((numeric.get(c) or 0.0) - sums[c]) <= TOL for c in cols.hours)
                and (all(cells.values()) or _is_ratio(g, r + 1, cols))):
            return r
        for c, v in numeric.items():
            top = g.cover.get((r, c))
            if v is not None and (not top or (top[0], top[1]) == (r, c)):
                sums[c] += v
    return None


def _sheet_b(R: _Reader, g: Grid, hidden: bool, consensus: dict[int, str]) -> list[Post]:
    h, cs = next((r, c) for r in range(g.h) for c in [_header_row(g, r)] if c is not None)
    band = _band(g, h, cs)
    nrow = band[-1] + 1
    numbers = nrow if g.filled(nrow) and all(g.t(nrow, c).isdigit() for c in g.filled(nrow)) else None
    cols = _columns(g, band, "B", consensus, None)                # H2: the number row never maps columns here
    for r in (*band, *([numbers] if numbers is not None else [])):
        for c in g.filled(r):
            if c > cols.right:
                R.note(g, r, c, "outside", x=g.t(r, c))
        g.use_row(r, "header", c2=cols.right)
    # the title rows: the year, the teacher in the year's row, the department (B1, B2)
    year_at = next(((r, c) for r in range(h) for c in g.filled(r) if tx.year(g.t(r, c))), None)
    who_at = next(((year_at[0], c) for c in g.filled(year_at[0]) if c != year_at[1]), None) if year_at else None
    if who_at is None and g.t(3, 4):
        who_at = (3, 4)
    for r in range(h):
        if any(key("kafedra") in key(g.t(r, c)) for c in g.filled(r)) and not R.form.department:
            R.form.department = " ".join(" ".join(g.t(r, c).split()) for c in g.filled(r))
        g.use_row(r, "post")
    e4 = g.t(*who_at) if who_at else ""
    e4_staff = tx.staff(e4)
    vacancy = e4_staff if e4_staff.kind == "vacancy" else None
    who = None if vacancy else tx.person(e4)
    texts = [g.t(r, c) for r in range(g.h) for c in g.filled(r)]
    used_words = {key(w) for t in texts for w in tx.WORD.findall(tx.SPLIT_CASE.sub(" ", t))}
    squeezed = [tx.compact(t).replace(",", ".") for t in texts]

    def repeated(w: str) -> bool:
        """B2: a word of the sheet's name that some cell repeats (an initial, ``0.5`` = ``0,5``, ``saathesabı``)."""
        k = key(w).replace(",", ".")
        return (k in used_words or (len(k) <= 2 and any(x.startswith(k) for x in used_words))
                or ((len(k) >= 3 or k[:1].isdigit()) and any(k in t for t in squeezed)))

    name_tokens = [w for w in re.findall(r"[^\W_]+(?:[.,]\d+)?", g.sheet.name) if not repeated(w)]
    start = (numbers if numbers is not None else band[-1]) + 1
    foot = next((r for r in range(start, g.h) if any(FOOTER in key(g.t(r, c)) for c in g.filled(r))), None)
    end = foot if foot is not None else g.h
    if foot is not None:
        g.use_row(foot, "footer")
        for r in range(foot + 1, g.h):
            for c in g.filled(r):
                R.note(g, r, c, "after_footer", x=g.t(r, c))
    posts: list[Post] = []
    if not cols.usable:
        post = Post(g.ref(*(who_at or (h, cols.left))), g.i, "B", staff_text="", hidden=hidden)
        _header_problems(R, g, post, cols, h, "ok")
        return [post]
    labels = [r for r in range(start, end) if _is_label(g, r, cols)]
    if any(g.filled(r) for r in range(start, labels[0] if labels else end)):
        labels.insert(0, start - 1)                               # rows before any label: a section with no label
    first_staff: str | None = None
    for n, lr in enumerate(labels):
        a, b = lr + 1, labels[n + 1] if n + 1 < len(labels) else end
        implicit = lr < start
        text = "" if implicit else g.t(lr, cols.subject)
        st = tx.staff(text) if text else tx.Staff()
        post = Post(g.ref(start, cols.subject) if implicit else g.ref(lr, cols.subject), g.i, "B", staff_text=text, hidden=hidden,
                    sheet_name_tokens=name_tokens)
        posts.append(post)
        R.cols[post.ref] = cols
        if year_at:
            post.year_text, post.year = g.t(*year_at), tx.year(g.t(*year_at))
        if not implicit:
            g.use(lr, cols.subject, "post")
        if n and who is not None:
            who = replace(who, flags=[], suffix=None)             # said once per sheet
        _post_staff(R, g, post, st if st.kind != "vacancy" else tx.Staff(), who, *(who_at or (h, cols.left)))
        if vacancy:                                               # B2, P3: the sheet is a vacancy whatever the label says
            post.vacancy, post.teacher_raw = True, e4
            post.vacancy_area = (" ".join(text.split()) or None) if st.kind == "unknown" else vacancy.area
        elif implicit:
            R.form.conflicts.append(Conflict(post.ref, "label_absent", _m("label_absent"), False, post.ref))
        elif st.kind == "unknown":
            R.conflict(g, lr, cols.subject, "label_unknown", True, post, x=text)
        if st.kind == "staff" and first_staff and not vacancy:
            post.second_post_of = first_staff                     # B4: a second post of the same teacher
        if st.kind == "staff" and first_staff is None:
            first_staff = post.ref
        _header_problems(R, g, post, cols, h, _labels(g, band[0], cols))
        total = next((r for r in range(a, b) if key(g.t(r, cols.subject)).startswith(key("Cəmi")) and not g.t(r, cols.group)), None)
        if total is None:
            total = _unlabelled_total(g, cols, a, b)
        _rows(R, g, post, cols, a, total if total is not None else b, total)
        for r in range(total + 1 if total is not None else b, b):
            filled = g.filled(r)
            if not filled:
                continue
            if r == total + 1 and _is_ratio(g, r, cols):          # type: ignore[operator]
                post.ratio_ref = g.ref(r, cols.year or 0)
                g.use_row(r, "ratio")
            elif _is_zero(g, r, cols):
                g.use_row(r, "structure")
            elif g.t(r, cols.subject) or g.t(r, cols.group) or any(tx.number(g.t(r, c)) is not None for c in cols.hours):
                R.conflict(g, r, filled[0], "after_total", True, post)
                g.use_row(r, "conflict")
            else:
                for c in filled:
                    R.note(g, r, c, "stray_text", post, x=g.t(r, c))
    if who_at and name_tokens and posts:
        R.form.notes.append(Note(posts[0].ref, "", "sheet_name", _m("sheet_name", x=", ".join(name_tokens)), posts[0].ref))
    return posts


# ---------------------------------------------------------------- sheets (G3) and the file
SUMMARY = tuple(key(x) for x in ("Soyadı, adı və atasının adı", "Ümumi dərs yükü (saat)"))
LIST = tuple(key(x) for x in ("Soyadı, adı, atasının adı", "Ştat vahidi", "Tədris yükü (saat)"))


def classify(g: Grid) -> str:
    """G3: by content, never by the sheet's name."""
    if not any(g.filled(r) for r in range(g.h)):
        return "empty"
    for r in range(min(g.h, 60)):
        ks = [key(g.t(r, c)) for c in g.filled(r)]
        if _header_row(g, r) is not None:
            return "form-B" if any(k.startswith(key("Birləşmənin işarəsi")) for k in ks) or len(_band(g, r, _header_row(g, r) or 0)) > 1 else "form-A"
        if all(any(k.startswith(x) for k in ks) for x in SUMMARY):
            return "summary"
        if all(any(k.startswith(x) for k in ks) for x in LIST):
            return "list"
    return "unknown"


SECTIONS = ((key("daxili əvəzçi"), "internal"), (key("kənar əvəzçi"), "external"), (key("məsləhətçi professor"), "consultant"),
            (key("vakant"), "vacancy"), (key("ştatda olan"), "main"))
TARGET = re.compile(r"(?:'([^']+)'|([^'!+\-*/(]+))!\$?[A-Z]+\$?(\d+)$")


def _summary(R: _Reader, g: Grid, by_name: dict[str, int]):
    """A7, T6: the summary sheet gives each block its staff category and two control sums; nothing of it is imported."""
    form = R.form
    h = next(r for r in range(g.h) if all(any(key(g.t(r, c)).startswith(x) for c in g.filled(r)) for x in SUMMARY))
    name_c = next(c for c in g.filled(h) if key(g.t(h, c)).startswith(SUMMARY[0]))
    total_c = next(c for c in g.filled(h) if key(g.t(h, c)).startswith(SUMMARY[1]))
    last_c = total_c                                              # the table ends at the first untitled column after the total
    while g.t(h, last_c + 1):
        last_c += 1
    contact_c = next((c for c in g.filled(h) if c > total_c and key(g.t(h, c)).startswith("aud")), None)
    degree_c = next((c for c in g.filled(h) if key(g.t(h, c)).startswith(key("Elmi dərəcə"))), None)
    a_posts = {p.ref: p for p in form.posts if p.layout == "A" and not p.hidden}
    by_total_row = {(p.sheet, int(re.sub(r"\D", "", p.total_ref.split("!")[1])) - 1): p for p in a_posts.values() if p.total_ref}
    section: str | None = None
    linked: set[str] = set()
    extra = 0
    for r in range(h + 1, g.h):
        filled = g.filled(r)
        extra += sum(c > last_c for c in filled)
        first = next((key(g.t(r, c)) for c in filled if c <= last_c), "")
        if not first:
            continue
        hit = "hourly" if first.replace(" ", "").startswith("saathesab") else next((s for k, s in SECTIONS if k in first), None)
        if hit and not g.t(r, total_c):
            section = hit
            continue
        total = tx.number(g.t(r, total_c))
        if section == "vacancy":
            if first.startswith(key("Cəmi")) and total is not None:
                vac = [p for p in a_posts.values() if p.vacancy and p.sheet in R.sheet_totals]
                found = sum(p.year_total or 0.0 for p in vac)
                for p in vac:
                    linked.add(p.ref)
                    form.controls.append(Control("post", p.ref, "T6", round(total, 4), round(found, 4), abs(total - found) <= TOL_SUM))
            continue
        name = g.t(r, name_c)
        if total is None or not name or not g.t(r, g.filled(r)[0]).isdigit() or section is None:
            continue
        post = None
        m = TARGET.search(g.sheet.formulas.get((r, total_c)) or "")
        if m:                                                     # (1) the formula names the block's total cell
            sheet = by_name.get(m.group(1) or m.group(2).strip())
            post = by_total_row.get((sheet, int(m.group(3)) - 1)) if sheet is not None else None
        if post is None:                                          # (2) the year total and the name together
            near = [p for p in a_posts.values() if p.year_total is not None and abs(p.year_total - total) <= TOL_SUM
                    and _same_person(name, p.teacher or "")]
            post = near[0] if len(near) == 1 else None
        if post is None:
            form.notes.append(Note(g.ref(r, name_c), "", "summary_unlinked", _m("summary_unlinked")))
            continue
        linked.add(post.ref)
        ok = post.year_total is not None and abs(post.year_total - total) <= TOL_SUM
        form.controls.append(Control("post", post.ref, "T6", round(total, 4), post.year_total, ok))
        if contact_c is not None:                                 # the summary's contact hours also count doctoral supervision
            doctoral = sum(x.hours for x in form.load if x.post == post.ref and x.kind == "doctoral")
            want = tx.number(g.t(r, contact_c)) or 0.0
            form.controls.append(Control("post", post.ref, "T6", round(want, 4), round(post.contact_hours + doctoral, 4),
                                         abs(want - post.contact_hours - doctoral) <= TOL_SUM))
        said = "hourly" if post.pay == "hourly" else "consultant" if post.consultant else post.employment
        if said not in (None, "substitute-unspecified", section):
            form.notes.append(Note(post.ref, "", "summary_category", _m("summary_category", x=section), post.ref))
        if section == "hourly":
            post.pay = "hourly"
        elif section == "consultant":
            post.consultant = True
        else:
            post.employment = section
        if degree_c is not None and g.t(r, degree_c) and (post.degree or post.position):
            theirs, mine = _titles_of(g.t(r, degree_c)), _titles_of(f"{post.degree or ''} {post.position or ''}")
            if not mine <= theirs and not theirs <= mine:
                form.notes.append(Note(post.ref, "", "summary_position", _m("summary_position", x=g.t(r, degree_c)), post.ref))
    if extra:
        form.notes.append(Note(f"#{g.i}", "", "summary_list", _m("summary_list", x=extra)))
    if linked:
        for p in a_posts.values():
            if p.ref not in linked:
                form.conflicts.append(Conflict(p.ref, "not_in_summary", _m("not_in_summary"), True, p.ref))


def _titles_of(text: str) -> set[str]:
    """Degree and position words, spelling variants folded (``f-r.e.n.`` = ``f.-r.e.n.``, ``dos`` = ``dosent``)."""
    text = re.sub(r"\b(baş|məsləhətçi|fəxri|kənar)\s+", r"\1_", key(text))   # "baş müəllim" is one position, not "müəllim"
    words = {re.sub(r"[.\-–]", "", w) for w in re.split(r"[\s,]+", text) if w}
    return {"dosent" if w == "dos" else w for w in words if w}


def _sheet_controls(R: _Reader):
    """T6 (layout A): the sheet's own totals row against the sum of its blocks' total rows."""
    form = R.form
    for i, r in R.sheet_totals.items():
        g, cols = R.grids[i], R.cols[f"#{i}"]
        mine = [p for p in form.posts if p.sheet == i and p.ref in R.totals]
        stale = []
        for c in (*cols.hours, *cols.totals.values(), cols.year):
            if c is None:
                continue
            found = sum(R.totals[p.ref].get(c, 0.0) for p in mine)
            text = g.t(r, c)
            cell = tx.number(text) if text else 0.0
            if c == cols.year:
                form.controls.append(Control("sheet", g.ref(r, c), "T6", cell, round(found, 4), cell is not None and abs(cell - found) <= TOL_SUM))
            elif cell is None or abs(cell - found) > TOL_SUM:
                stale.append(col_name(c))
        if stale:
            form.notes.append(Note(g.ref(r, cols.left), "", "sheet_totals", _m("sheet_totals", x=", ".join(stale))))


def _links(R: _Reader):
    """J3, J7 and O1: suggestions between posts. Nothing here changes a unit."""
    form = R.form
    visible = [u for u in form.units if not u.hidden]
    lectures: dict[tuple, Unit] = {}
    practice: set[tuple] = set()
    for u in visible:
        for x in u.groups:
            k = (u.subject_core, key(x["code"]), u.semester)
            if u.kind == "lecture":
                lectures.setdefault(k, u)
            else:
                practice.add(k)
    for u in visible:
        keys = [(u.subject_core, key(x["code"]), u.semester) for x in u.groups]
        if u.kind == "lecture":
            if keys and not any(k in practice for k in keys):
                form.links.append(Link(u.anchor, None, "subject_core+groups+semester", "info"))
            continue
        found = next((lectures[k] for k in keys if k in lectures), None)
        if found is None:
            form.links.append(Link(u.anchor, None, "subject_core+groups+semester", "info"))
        elif found.post != u.post:
            form.links.append(Link(u.anchor, found.anchor, "subject_core+groups+semester", "info"))
    for e in R.empty:                                             # J3: an empty merge mirrors a class given in another post
        same = [u for u in visible if u.post != e["post"] and u.semester == e["sem"] and u.kind == e["kind"]
                and e["groups"] and e["groups"] & {x["code"] for x in u.groups} and u.subject_core in e["cores"]]
        same.sort(key=lambda u: e["groups"] != {x["code"] for x in u.groups})
        if same and e["groups"] == {x["code"] for x in same[0].groups}:
            form.links.append(Link(e["ref"], same[0].anchor, "empty_merge_mirror", "info"))
        elif same:
            form.links.append(Link(e["ref"], same[0].anchor, "empty_merge_mirror", "note"))
        else:
            form.links.append(Link(e["ref"], None, "empty_merge_mirror", "note"))
            form.notes.append(Note(e["ref"], "", "class_elsewhere", _m("class_elsewhere"), e["post"]))
    teachers = {p.teacher: p for p in form.posts if p.teacher and not p.hidden}
    by_teacher: dict[str, list[Unit]] = defaultdict(list)
    for u in visible:
        if u.teacher:
            by_teacher[u.teacher].append(u)
    cache: dict[str, str | None] = {}
    for a in R.at:                                                # O1: a cross-check only; the hours never move
        u, name = a["unit"], a["name"]
        if u.hidden:
            continue
        if name not in cache:
            who = tx.person(name)
            cache[name] = next((t for t in teachers if _same_person(who.name or who.raw or name, t)), None)
        t = cache[name]
        codes = {x["code"] for x in u.groups}
        hit = next((x for x in by_teacher.get(t or "", []) if x.subject_core == u.subject_core and x.semester == u.semester
                    and codes & {y["code"] for y in x.groups}), None)
        form.links.append(Link(a["cell"], hit.anchor if hit else None, "at_name", "info" if hit else "note"))
        if t is None:
            form.notes.append(Note(a["cell"], "", "counterpart_outside", _m("counterpart_outside", x=name), u.post))
        elif hit is None:
            form.notes.append(Note(a["cell"], "", "counterpart_contradicted", _m("counterpart_contradicted", x=name), u.post))


def _file_rules(R: _Reader):
    """G5 (the year), G7 (codes that look wrong), G8 (different student counts for one group)."""
    form = R.form
    years = Counter(p.year for p in form.posts if p.year)
    form.year = years.most_common(1)[0][0] if years else None
    by_ref = {p.ref: p for p in form.posts}
    for p in form.posts:
        if form.year and p.year != form.year:
            p.year_conflict = True
            form.conflicts.append(Conflict(p.ref, "year_conflict", _m("year_conflict", x=p.year_text or "—", y=form.year), True, p.ref))
    start = int(form.year[:4]) if form.year else None
    wrong: dict[str, list] = defaultdict(list)
    counts: dict[str, dict[int, str]] = defaultdict(dict)
    for u in form.units:
        if by_ref[u.post].year_conflict:
            u.flags.append({"flag": "year_conflict", "cell": u.post})
        for x in u.groups:
            cell = f"#{u.sheet}!{col_name(R.cols[u.post].group or 0)}{x['row']}"
            if tx.code_looks_wrong(x["code"], start):
                u.flags.append({"flag": "code_looks_wrong", "cell": cell})
                wrong[x["code"]].append((cell, u.post))
            if x["students"] is not None and not u.hidden:
                counts[x["code"]].setdefault(x["students"], cell)
    for ll in form.load:
        for x in ll.groups:
            cell = f"#{ll.sheet}!{col_name(R.cols[ll.post].group or 0)}{x['row']}"
            if tx.code_looks_wrong(x["code"], start):
                wrong[x["code"]].append((cell, ll.post))
            if x["students"] is not None and not by_ref[ll.post].hidden:
                counts[x["code"]].setdefault(x["students"], cell)
    for code, cells in sorted(wrong.items()):
        for cell, post in sorted(set(cells)):
            form.conflicts.append(Conflict(cell, "code_wrong", _m("code_wrong", x=code), False, post, {"code": code}))
    for code, seen in sorted(counts.items()):
        if len(seen) > 1:
            form.notes.append(Note(min(seen.values()), "", "students_differ",
                                   _m("students_differ", x=code, y=", ".join(str(n) for n in sorted(seen)))))


def read(sheets: list[Sheet]) -> Form:
    """The whole workbook: every post, unit, load line, link, note, conflict and control. Raises ``FormError`` only for a
    workbook that cannot be gridded at all; everything else is in the result."""
    R = _Reader()
    form = R.form
    grids = [Grid(s, i) for i, s in enumerate(sheets)]
    R.grids = {g.i: g for g in grids}
    classes = [classify(g) for g in grids]
    b_titles = [_raw_titles(g, _band(g, *next((r, c) for r in range(g.h) for c in [_header_row(g, r)] if c is not None)))
                for g, cl in zip(grids, classes, strict=True) if cl == "form-B"]
    b_consensus: dict[int, str] = {}
    for c in {c for t in b_titles for c in t}:
        seen = {key(t[c]) for t in b_titles if c in t and _title(key(t[c]), "B")}
        if len(seen) == 1 and sum(c in t and _title(key(t[c]), "B") is not None for t in b_titles) > 1:
            b_consensus[c] = seen.pop()
    layouts = Counter(cl[-1] for cl in classes if cl.startswith("form-"))
    form.layout = layouts.most_common(1)[0][0] if layouts else None
    for g, cl in zip(grids, classes, strict=True):
        hidden = g.sheet.state != "visible"
        code = {"form-A": "sheet_form", "form-B": "sheet_form", "summary": "sheet_summary", "list": "sheet_list", "empty": "sheet_empty",
                "unknown": "sheet_unknown"}[cl]
        info = SheetInfo(g.i, g.sheet.name, g.sheet.state, cl, cl.startswith("form-") and not hidden, _m("sheet_hidden" if hidden and cl.startswith("form-") else code))
        form.sheets.append(info)
        if cl == "unknown":
            form.conflicts.append(Conflict(f"#{g.i}", "sheet_unknown", _m("sheet_unknown"), False))
        if not cl.startswith("form-"):
            continue
        before = len(form.units)
        posts = _sheet_a(R, g, hidden) if cl == "form-A" else _sheet_b(R, g, hidden, b_consensus)
        form.posts += posts
        mine = form.units[before:]
        info.units, info.hours = len(mine), sum(u.hours for u in mine)
        info.rows = sum(p.rows[1] - p.rows[0] + 1 for p in posts if p.rows)
        if not mine and info.rows and not any(x.sheet == g.i for x in form.load):
            form.notes.append(Note(f"#{g.i}", "", "zero_load", _m("zero_load")))
        elif not mine and info.rows:
            form.conflicts.append(Conflict(f"#{g.i}", "no_units", _m("no_units"), False))
        elif not info.rows:
            form.notes.append(Note(f"#{g.i}", "", "zero_load", _m("zero_load")))
    for g, cl in zip(grids, classes, strict=True):
        if cl == "form-A" and any(R.cols[p.ref].doctoral_title is not None for p in form.posts if p.sheet == g.i and p.ref in R.cols):
            form.notes.append(Note(f"#{g.i}", "", "doctoral_title", _m("doctoral_title")))       # H5: one note per sheet
    _file_rules(R)
    by_name = {s.name: i for i, s in enumerate(sheets)}
    for g, cl in zip(grids, classes, strict=True):
        if cl == "summary" and g.sheet.state == "visible":
            _summary(R, g, by_name)
    _sheet_controls(R)
    _links(R)
    blocking = {c.post for c in form.conflicts if c.blocking and c.post}
    for p in form.posts:
        p.blocked = p.ref in blocking or p.year_conflict or not all(p.controls.values()) or not p.controls
    # G9: every non-empty cell of a form sheet has exactly one place
    tally: Counter = Counter()
    for g, cl in zip(grids, classes, strict=True):
        if not cl.startswith("form-"):
            continue
        for r in range(g.h):
            for c in g.filled(r):
                if (r, c) not in g.used:
                    form.unclassified += 1
                    R.note(g, r, c, "unclassified", x=g.t(r, c))
                tally[g.used[(r, c)]] += 1
    form.cells = dict(tally)
    shown = [u for u in form.units if not u.hidden]
    form.controls.append(Control("file", "", "T5", None, float(len(shown)), True))
    form.controls.append(Control("file", "", "T5", None, round(sum(u.hours for u in shown), 4), True))
    return form


# ---------------------------------------------------------------- the report a person reads before applying the file
MAX_LISTED = 500


def report(form: Form, known_codes: set[str] | None = None) -> dict:
    """What the import preview and ``manage.py forma3-check`` show: per post ok / blocked / hidden with its controls,
    the conflicts and notes by cell, the load-line totals. A group code the registry knows is never "looks wrong" (G7)."""
    known = known_codes or set()
    conflicts = [c for c in form.conflicts if not (c.code == "code_wrong" and key(c.data.get("code", "")) in known)]
    units: dict[str, list[Unit]] = defaultdict(list)
    for u in form.units:
        units[u.post].append(u)
    load: dict[str, dict] = {}
    for x in form.load:
        row = load.setdefault(x.kind, {"lines": 0, "hours": 0.0})
        row["lines"] += 1
        row["hours"] = round(row["hours"] + x.hours, 4)
    blocked = {p.ref for p in form.posts if p.blocked}
    shown = [u for u in form.units if not u.hidden]
    ready = [u for u in shown if u.post not in blocked]
    return {
        "layout": form.layout, "year": form.year, "department": form.department,
        "sheets": [{"index": s.index, "name": s.name, "state": s.state, "class": s.cls, "imported": s.imported, "reason": s.reason,
                    "units": s.units, "hours": round(s.hours, 4)} for s in form.sheets],
        "posts": [{"ref": p.ref, "sheet": p.sheet, "teacher": p.teacher, "vacancy": p.vacancy, "vacancy_area": p.vacancy_area,
                   "pay": p.pay, "fraction": p.fraction, "employment": p.employment, "second_post_of": p.second_post_of,
                   "status": "hidden" if p.hidden else "blocked" if p.blocked else "ok", "controls": p.controls,
                   "year_conflict": p.year_conflict, "units": len(units[p.ref]), "hours": round(sum(u.hours for u in units[p.ref]), 4),
                   "year_total": round(p.year_total, 4) if p.year_total is not None else None} for p in form.posts],
        "units": {"count": len(shown), "hours": round(sum(u.hours for u in shown), 4), "hidden": sum(u.hidden for u in form.units),
                  "ready": len(ready), "ready_hours": round(sum(u.hours for u in ready), 4), "hourly": sum(u.hourly for u in shown),
                  "vacancy": sum(u.vacancy for u in shown), "joint": sum(u.joint for u in shown)},
        "conflicts": [{"cell": c.cell, "code": c.code, "message": c.message, "blocking": c.blocking, "post": c.post}
                      for c in sorted(conflicts, key=lambda c: not c.blocking)[:MAX_LISTED]],
        "conflict_count": len(conflicts), "blocking_count": sum(c.blocking for c in conflicts),
        "notes": [{"cell": n.cell, "code": n.code, "message": n.message, "post": n.post} for n in form.notes[:MAX_LISTED]],
        "note_count": len(form.notes),
        "load": load, "load_hours": round(sum(x.hours for x in form.load), 4),
        "links": dict(Counter(f"{x.basis}:{x.level}" for x in form.links)),
        "controls": [asdict(c) for c in form.controls if c.scope != "post" or not c.ok],
        "cells": form.cells, "unclassified": form.unclassified,
    }
