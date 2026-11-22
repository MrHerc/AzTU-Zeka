"""The texts of Forma №3 (docs/forms/forma-3.md, Task 47): the staff line of a layout-A block, the teacher cell and the
section label of a layout-B sheet, group codes, subject keys, numbers and the year. No I/O.

Rule ids (A6, B2, B3, G5, G6, G7) are those of docs/forms/forma-3.md. Raw text is always kept next to a parsed value.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

from . import domain

MAX_HOURS = 1_000_000                            # a department's year total is tens of thousands


def key(v: str) -> str:
    """Compared form: Azerbaijani lower case, Latin I = İ, spaces collapsed."""
    return domain.key(v)


def compact(v: str) -> str:
    return key(v).replace(" ", "")


def number(v: str) -> float | None:
    """A cell's number, or None for empty, text, an error value, infinity, NaN, a negative or an absurd size."""
    v = (v or "").strip().replace(",", ".")
    try:
        n = float(v)
    except ValueError:
        return None
    return n if math.isfinite(n) and 0 <= n < MAX_HOURS else None


def is_error(v: str) -> bool:
    """A stored spreadsheet error (``#REF!``, ``#NAME?``, ``#DIV/0!`` ...)."""
    return (v or "").strip().startswith("#")


# ---------------------------------------------------------------- the year (G5)
YEAR = re.compile(r"(\d{4})\s*/\s*(\d{4}|\d{2})")


def year(text: str) -> str | None:
    """``2026/27-CI TƏDRİS İLİ`` and ``2026/2027-ci tədris ili`` -> ``2026/2027``."""
    m = YEAR.search(text or "")
    if not m:
        return None
    a, b = m.group(1), m.group(2)
    return f"{a}/{b if len(b) == 4 else a[:2] + b}"


# ---------------------------------------------------------------- people (A6, B2)
POSITIONS = tuple(sorted((key(x) for x in (
    "məsləhətçi professor", "fəxri professor", "professor", "dosent", "dos", "baş müəllim", "müəllim", "assistent", "assisten",
    "kənar doktorant", "doktorant", "kafedra müdiri")), key=lambda x: -len(x.split())))
KINDS = {key("əvəzçi"): "substitute", key("kənar"): "external", key("daxili"): "internal"}
GENITIVE = {key("oğlunun"): "oğlu", key("qızının"): "qızı", key("qıznın"): "qızı", key("oğlu"): "oğlu", key("qızı"): "qızı"}
WORD = re.compile(r"[^\W\d_]+(?:['’ʼ-][^\W\d_]+)*")
SPLIT_CASE = re.compile(r"(?<=[a-zəöüışçğ])(?=[A-ZƏÖÜİŞÇĞ])")
RUSSIAN = tuple(key(x) for x in ("ovna", "yevna", "evna", "oviç", "ovich", "ovič", "yeviç", "eviç"))


@dataclass
class Person:
    raw: str = ""                         # the name part as written
    name: str | None = None               # ``Soyad Ad [Ata adı oğlu|qızı]``, nominative
    degree: str | None = None
    position: str | None = None
    suffix: str | None = None             # a bracketed suffix after the name: ``(sabah qrupları)``
    flags: list[str] = field(default_factory=list)       # no_patronymic | russian_patronymic
    ok: bool = False


def _capital(w: str) -> str:
    first = {"i": "İ", "ı": "I"}.get(w[0], w[0].upper())
    return first + w[1:]


def person(text: str) -> Person:
    """``t.ü.f.d., dosent Quliyev Elçin Rauf oğlunun`` -> degree, position and ``Quliyev Elçin Rauf oğlu``."""
    out = Person()
    s = " ".join((text or "").split())
    m = re.search(r"\(([^()]*)\)\s*$", s)
    if m:
        out.suffix, s = m.group(1).strip() or None, s[:m.start()].strip()
    tokens = [t.lstrip("-–—") for t in re.split(r"[\s,]+", s)]
    tokens = [t for t in tokens if t]
    degrees: list[str] = []
    i = 0
    while i < len(tokens):
        t = tokens[i]
        two = key(" ".join(tokens[i:i + 2]))
        if "." in t.rstrip(".") and not any(ch.isupper() or ch.isdigit() for ch in t) or (
                t.endswith(".") and len(t) <= 4 and t.islower() and key(t.rstrip(".")) not in POSITIONS):
            degrees.append(t)                      # t.e.d. | f.-r.e.n. | t.ü.f.d: lower-case letters with dots
            i += 1
        elif two in POSITIONS:
            out.position, i = " ".join(tokens[i:i + 2]), i + 2
        elif key(t.rstrip(".")) in POSITIONS:
            out.position, i = t.rstrip("."), i + 1
        else:
            break
    out.degree = ", ".join(degrees) or None
    words: list[str] = []
    for t in tokens[i:]:
        words += SPLIT_CASE.sub(" ", t).split()
    out.raw = " ".join(tokens[i:])
    if not 2 <= len(words) <= 4 or not all(WORD.fullmatch(w) for w in words):
        return out
    last = GENITIVE.get(key(words[-1]))
    if last:
        words[-1] = last
        if len(words) < 3:                       # "Ad oğlu" is not a name
            return out
    else:
        out.flags.append("russian_patronymic" if len(words) >= 3 and key(words[-1]).endswith(RUSSIAN) else "no_patronymic")
    out.name = " ".join(w if j == len(words) - 1 and last else _capital(w) for j, w in enumerate(words))
    out.ok = True
    return out


@dataclass
class Staff:
    """What a staff line (layout A) or a section label (layout B) says about the post."""
    kind: str = "unknown"                 # staff | hourly | vacancy | unknown
    fraction: float | None = None
    employment: str | None = None         # main | internal | external | substitute-unspecified | None (not said)
    area: str | None = None               # a vacancy's area
    rest: str = ""                        # what follows the post words: the person (layout A)


STAT = re.compile(r"^\s*(?P<main>[əƏ]sas\s+[iİIı][şsŞS]\s+yer[iİIı]\s+üzrə\s+)?(?P<n>\d+(?:[.,]\d+)?)\s*ştat(?![^\W\d_])", re.IGNORECASE)
HOURLY = re.compile(r"^\s*saat\s*hesab[ıiIİ]", re.IGNORECASE)
VACANCY = re.compile(r"^\s*vakans[iİIı]ya", re.IGNORECASE)


def _area(text: str) -> str | None:
    return " ".join(text.replace("_", " ").strip(" ()-–—").split()) or None


def staff(text: str) -> Staff:
    """A6 and the B3 label grammar: ``[əsas iş yeri üzrə] <kəsr> ştat {əvəzçi|kənar|daxili} [-] …``, ``saat hesabı [-] …``
    (with or without the space), ``Vakansiya [sahə]``. Anything else is ``unknown``."""
    raw = text or ""
    m = VACANCY.match(raw)
    if m:
        return Staff("vacancy", area=_area(raw[m.end():]))
    m = HOURLY.match(raw)
    if m:
        return Staff("hourly", rest=raw[m.end():].strip().lstrip("-–—").strip())
    m = STAT.match(raw)
    if not m:
        return Staff()
    rest = raw[m.end():]
    kinds: set[str] = set()
    while True:
        w = re.match(r"\s*([^\W\d_]+)", rest)
        if not w or key(w.group(1)) not in KINDS:
            break
        if key(w.group(1)) == key("kənar") and key(rest[w.end():]).startswith(key("doktorant")) and "-" not in rest[:w.end()]:
            kinds.add("external")                 # ``kənar doktorant`` is also the position: the word stays with the person
            break
        kinds.add(KINDS[key(w.group(1))])
        rest = rest[w.end():]
    employment = ("internal" if "internal" in kinds else "external" if "external" in kinds
                  else "substitute-unspecified" if kinds else "main" if m.group("main") else None)
    try:
        fraction = float(m.group("n").replace(",", "."))
    except ValueError:
        fraction = None
    return Staff("staff", fraction, employment, rest=rest.strip().lstrip("-–—").strip())


# ---------------------------------------------------------------- groups (G7)
CODE = re.compile(r"(M\d{3}|\d{4})[A-Za-z]{1,3}\d{0,2}")


def group_code(v: str) -> str:
    """The code without any whitespace: ``6526e 1`` is the group ``6526e1`` (there is no subgroup notation)."""
    return re.sub(r"\s+", "", v or "")


def code_looks_wrong(code: str, year_start: int | None) -> bool:
    """Not ``M``+3 digits or 4 digits, then 1–3 letters and up to 2 digits; or an intake year (digits 3–4 of a 4-digit
    code) outside the six years that end at the file year's start."""
    if not CODE.fullmatch(code):
        return True
    if code[0] == "M" or year_start is None:
        return False
    return not year_start % 100 - 5 <= int(code[2:4]) <= year_start % 100


# ---------------------------------------------------------------- subjects (G6)
DASH = re.compile(r"\s*[-–—]\s*")
IFS = re.compile(r"^[İIıi]FS(-\d+y)?\s*:?\s+", re.IGNORECASE)
SF = re.compile(r"^s/f\.\s*", re.IGNORECASE)
COURSE_CODE = re.compile(r"^[A-Z]{2,4}\.\d+-+\s*")
TOOLS = re.compile(r"\s+[—–]\s+\S.*$")
ENGLISH = re.compile(r"\s*\(([A-Z][A-Za-z0-9 /]*)\)\s*$")


def subject_key(v: str) -> str:
    """The matching key of a subject: lower case, spaces collapsed, dashes unified with no space around them."""
    return DASH.sub("-", key(v))


def subject_core(v: str) -> str:
    """The key without an ``İFS:`` / ``s/f.`` / course-code prefix, a `` — tool list`` tail and a trailing bracket that is
    an English translation. Only for suggesting links between posts, never for merging units."""
    s = " ".join((v or "").split())
    for rx in (COURSE_CODE, IFS, SF):
        s = rx.sub("", s, count=1)
    m = TOOLS.search(s)
    if m and ("," in m.group(0) or len(m.group(0).split()) > 3):
        s = s[:m.start()]
    m = ENGLISH.search(s)
    if m and "," not in m.group(1):
        s = s[:m.start()]
    return subject_key(s)


# ---------------------------------------------------------------- cell references
def col_name(c: int) -> str:
    s = ""
    c += 1
    while c:
        c, r = divmod(c - 1, 26)
        s = chr(65 + r) + s
    return s
