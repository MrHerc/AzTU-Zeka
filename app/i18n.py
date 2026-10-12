"""Internationalisation (gettext style): the Azerbaijani source string is the key.

* ``S(text, lang, **p)``   – translate + format one string for one language.
* ``T3(text, **p)``        – the same string for all languages as ``{"az","en","ru"}`` (stored or returned as-is;
                             JSON responses are localised automatically by ``localize``).
* ``S_(text)``             – no-op marker so the extractor picks up strings used elsewhere (vocabularies, templates).
* ``tr3 / J3``             – content strings (seed data) as i18n dicts / JSON text for DB columns.
* ``localize(obj, lang)``  – walks a JSON-able object and resolves every i18n dict / i18n JSON string.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

LANGS = ("az", "en", "ru")
ROOT = Path(__file__).resolve().parent
_CAT: dict[str, dict] = {"en": {}, "ru": {}}
_SET = set(LANGS)


def load():
    for lg in ("en", "ru"):
        p = ROOT / "locales" / f"{lg}.json"
        try:
            _CAT[lg] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except ValueError:
            _CAT[lg] = {}


def norm_lang(v) -> str | None:
    v = str(v or "").strip().lower()[:2]
    return v if v in _SET else None


def _plural(lang: str, n, forms: dict) -> str:
    try:
        n = abs(int(float(n)))
    except (TypeError, ValueError):
        n = 0
    if lang == "ru":
        m10, m100 = n % 10, n % 100
        if m10 == 1 and m100 != 11:
            key = "one"
        elif 2 <= m10 <= 4 and not 12 <= m100 <= 14:
            key = "few"
        else:
            key = "many"
        return forms.get(key) or forms.get("other") or forms.get("many") or ""
    return (forms.get("one") if n == 1 else None) or forms.get("other") or forms.get("many") or ""


def tr(text, lang: str, n=None):
    if not isinstance(text, str) or not text or lang not in _CAT:
        return text
    v = _CAT[lang].get(text)
    if v is None or v == "":
        return text
    if isinstance(v, dict):
        return _plural(lang, n, v)
    return v


def _fmt(s: str, params: dict, lang: str) -> str:
    if not params:
        return s
    vals = {k: L(tr(v, lang) if isinstance(v, str) else v, lang) for k, v in params.items()}
    try:
        return s.format(**vals)
    except (KeyError, IndexError, ValueError):
        return s


def S(text: str, lang: str = "az", /, **params) -> str:
    return _fmt(tr(text, lang, params.get("n")), params, lang)


def S_(text: str) -> str:
    return text


def T3(text: str, /, **params) -> dict:
    return {lg: S(text, lg, **params) for lg in LANGS}


E = T3  # error messages


def tr3(text):
    if not isinstance(text, str) or not text:
        return text
    return {lg: tr(text, lg) for lg in LANGS}


def J3(text) -> str:
    v = tr3(text)
    return json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else (v or "")


def is_i18n(d) -> bool:
    return isinstance(d, dict) and len(d) == 3 and set(d) == _SET


def L(v, lang: str):
    if isinstance(v, dict) and is_i18n(v):
        return v.get(lang) or v.get("az") or ""
    if isinstance(v, str) and v.startswith('{"az"'):
        try:
            d = json.loads(v)
        except ValueError:
            return v
        if is_i18n(d):
            return d.get(lang) or d.get("az") or ""
    return v


def localize(obj, lang: str, _key: str = ""):
    """Resolve i18n dicts / i18n JSON strings and translate plain catalog strings (seeded content).

    Values under user-content keys (chat messages, typed questions) are never translated.
    """
    if isinstance(obj, dict):
        if is_i18n(obj):
            return obj.get(lang) or obj.get("az") or ""
        return {k: (v if k in SKIP_KEYS and isinstance(v, str) else localize(v, lang, k)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [localize(v, lang, _key) for v in obj]
    if isinstance(obj, str):
        if obj.startswith('{"az"'):
            return L(obj, lang)
        if lang != "az" and obj:
            if _key != "tags" and _IDENT.fullmatch(obj):
                return obj          # codes such as roles, statuses, kinds and tab keys are never translated
            v = _CAT[lang].get(obj)
            if isinstance(v, str) and v:
                return v
            if len(obj) < 200:
                c = _compose(obj, _CAT[lang])
                if c:
                    return c
    return obj


_SEP = re.compile(r"(, | · |: | — | – )")
_IDENT = re.compile(r"[a-z0-9_\-]+")
_NUMERIC = re.compile(r"[\d\s№#.,:/+\-–()]*[A-Za-z]?\d*")


def _compose(s: str, cat: dict):
    """Translate composite strings such as 'İT korpusu, 214' or 'Sertifikat: <track>' when every textual part is a catalog key."""
    parts = _SEP.split(s)
    if len(parts) < 3:
        return None
    out, translated = [], False
    for i, p in enumerate(parts):
        core = p.strip()
        if i % 2 or not core or _NUMERIC.fullmatch(core):
            out.append(p)
            continue
        v = cat.get(core)
        if not isinstance(v, str) or not v:
            return None
        out.append(p.replace(core, v))
        translated = True
    return "".join(out) if translated else None


# User texts and course-material section headings are shown as written. A heading is course content and can share
# its spelling with a UI string of another sense ("Giriş": introduction vs. "Log in"). Reference titles, sections, authors and
# publishers (content/references.json) are proper names in the language of the source. Their keys are unique to references:
# "author" is NOT skipped, because message and news authors include translated personas ("İT administratoru").
SKIP_KEYS = {"content", "question", "context", "username", "email", "heading", "work", "part", "authors", "publisher"}


def canon(value, options):
    """Map a (possibly translated) option label back to its canonical Azerbaijani value."""
    if value in options:
        return value
    for o in options:
        if any(tr(o, lg) == value for lg in ("en", "ru")):
            return o
    return value


def num3(x, digits: int = 1) -> dict:
    s = f"{x:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{x:.0f}"
    return {"az": s.replace(".", ","), "en": s, "ru": s.replace(".", ",")}


def join3(items, sep: str = ", ") -> dict:
    return {lg: sep.join(str(L(i, lg)) for i in items) for lg in LANGS}


# Vocabulary stored as canonical Azerbaijani values in data (rooms, components, levels...).
VOCAB = [S_("Mühazirə"), S_("Məşğələ"), S_("Laboratoriya"), S_("Xatırlama"), S_("Anlama"), S_("Tətbiq"), S_("Təhlil"),
         S_("Asan"), S_("Orta"), S_("Çətin"), S_("Əsas korpus"), S_("İT korpusu"), S_("Elektronika laboratoriyası"),
         S_("Fizika laboratoriyası"), S_("Qrafika laboratoriyası"), S_("Mexatronika laboratoriyası")]

load()
