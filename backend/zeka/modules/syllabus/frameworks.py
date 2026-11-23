"""Frameworks and the outcome map (tasks/todo.md, Task 24): the service; its SQL is in repo.py.

A framework is a version of a published reference (NICE Framework Components, Bloom's revised taxonomy, the EQF levels)
with its items, the links between them and a parent per item (a NICE work role's category, an EQF descriptor's level).
NICE comes as the JSON file NIST publishes (content/frameworks/README.md), imported unchanged by
``manage.py import-framework``: a known version's SHA-256 is checked, a version is never re-imported with other content,
and a newer version is a new row beside the older one, whose items and maps stay readable. Bloom and EQF are built in
(``BUILTIN``) and written at every start, in prod too.

A course's teacher tags each learning outcome with items of any framework. The key of a tag is the course and the
outcome's code (N1 …), which every new version of the syllabus keeps; a saved version without an outcome drops its tags.
A submitted version keeps the map it was submitted with (``syllabus_versions.tags``): what is approved, published,
printed and reported is that map, and a later change reaches only the next version. The coverage report of a programme (a specialty:
its groups' teaching units give its courses) lists, per NICE work role, the task, knowledge and skill statements that
an outcome of the programme's courses covers, by which outcome, and the ones nothing covers.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from typing import Any

from ...core.i18n import E, Lit, S, S_
from ...legacy.store import J, audit, iso, now
from ..integration.domain import csv_cell
from . import repo, service

# A version NIST published: the SHA-256 of its file as downloaded and where it came from (content/frameworks/README.md).
KNOWN = {("nice", "2.2.0"): ("3ad1d9d7e0d6b32895cb569f86c3bc05af2937a68e96eab4d1c9b3d9fa6e575e",
                             "https://csrc.nist.gov/csrc/media/Projects/cprt/documents/nice/v2-2-0_nf_components.json")}
MAX_FILE = 50 * 1024 * 1024
STATEMENTS = ("task", "knowledge", "skill")                          # what a NICE work role is measured by
MAPPABLE = ("task", "knowledge", "skill", "level", "responsibility")  # what an outcome may carry
MAX_TAGS = 50
KIND = re.compile(r"[a-z_]{1,32}", re.ASCII)
KIND_LABEL = {"task": S_("Tapşırıq bəyanatı"), "knowledge": S_("Bilik"), "skill": S_("Bacarıq"), "work_role": S_("İş rolu"),
              "competency_area": S_("Səriştə sahəsi"), "category": S_("Kateqoriya"), "opm_code": S_("OPM kodu"),
              "sort": S_("Sıralama açarı"), "level": S_("Səviyyə"), "responsibility": S_("Məsuliyyət və müstəqillik")}

# Built-in frameworks. The Azerbaijani and Russian texts are working translations (no official one exists); the EQF's
# official text is the English one of the Council Recommendation of 22 May 2017 (2017/C 189/03), Annex II.
_EQF = (
    (S_("Əsas ümumi bilik"),
     S_("Sadə tapşırıqları yerinə yetirmək üçün lazım olan əsas bacarıqlar"),
     S_("Strukturlaşdırılmış mühitdə birbaşa nəzarət altında işləmək və ya təhsil almaq")),
    (S_("İş və ya təhsil sahəsi üzrə əsas faktiki bilik"),
     S_("Sadə qayda və alətlərlə tapşırıqları yerinə yetirmək və adi problemləri həll etmək üçün lazımi məlumatdan istifadəyə "
        "imkan verən əsas koqnitiv və praktik bacarıqlar"),
     S_("Nəzarət altında, müəyyən müstəqilliklə işləmək və ya təhsil almaq")),
    (S_("İş və ya təhsil sahəsində faktlar, prinsiplər, proseslər və ümumi anlayışlar haqqında bilik"),
     S_("Əsas üsul, alət, material və məlumatları seçib tətbiq etməklə tapşırıqları yerinə yetirmək və problemləri həll etmək "
        "üçün lazım olan koqnitiv və praktik bacarıqlar"),
     S_("İşdə və ya təhsildə tapşırıqların yerinə yetirilməsinə görə məsuliyyət daşımaq; problemləri həll edərkən öz "
        "davranışını şəraitə uyğunlaşdırmaq")),
    (S_("İş və ya təhsil sahəsində geniş kontekstlərdə faktiki və nəzəri bilik"),
     S_("İş və ya təhsil sahəsində konkret problemlərin həllini tapmaq üçün lazım olan koqnitiv və praktik bacarıqlar"),
     S_("Adətən proqnozlaşdırılan, lakin dəyişə bilən iş və ya təhsil şəraitində müəyyən edilmiş qaydalar çərçivəsində "
        "özünüidarə; başqalarının gündəlik işinə nəzarət etmək, iş və ya təhsil fəaliyyətinin qiymətləndirilməsi və "
        "təkmilləşdirilməsi üçün müəyyən məsuliyyət daşımaq")),
    (S_("İş və ya təhsil sahəsində əhatəli, ixtisaslaşmış, faktiki və nəzəri bilik və bu biliyin hüdudlarını dərk etmək"),
     S_("Mücərrəd problemlərə yaradıcı həllər hazırlamaq üçün lazım olan əhatəli koqnitiv və praktik bacarıqlar"),
     S_("Gözlənilməz dəyişikliklər olan iş və ya təhsil fəaliyyətində idarəetmə və nəzarəti həyata keçirmək; özünün və "
        "başqalarının fəaliyyətini təhlil edib inkişaf etdirmək")),
    (S_("İş və ya təhsil sahəsində nəzəriyyə və prinsipləri tənqidi anlamağı nəzərdə tutan qabaqcıl bilik"),
     S_("İxtisaslaşmış iş və ya təhsil sahəsində mürəkkəb və gözlənilməz problemləri həll etmək üçün lazım olan, ustalıq və "
        "yenilikçilik nümayiş etdirən qabaqcıl bacarıqlar"),
     S_("Mürəkkəb texniki və ya peşə fəaliyyətini, yaxud layihələri idarə etmək, gözlənilməz iş və ya təhsil şəraitində qərar "
        "qəbuluna görə məsuliyyət daşımaq; fərdlərin və qrupların peşəkar inkişafının idarə olunmasına görə məsuliyyət daşımaq")),
    (S_("Bir qismi iş və ya təhsil sahəsində biliyin ön cəbhəsində olan, orijinal təfəkkür və (və ya) tədqiqat üçün əsas "
        "olan yüksək ixtisaslaşmış bilik; sahədəki və müxtəlif sahələrin qovşağındakı bilik məsələlərini tənqidi dərk etmək"),
     S_("Yeni bilik və prosedurlar yaratmaq və müxtəlif sahələrin biliklərini birləşdirmək üçün tədqiqat və (və ya) "
        "innovasiyada lazım olan ixtisaslaşmış problem həlli bacarıqları"),
     S_("Mürəkkəb, gözlənilməz və yeni strateji yanaşmalar tələb edən iş və ya təhsil şəraitini idarə etmək və dəyişdirmək; "
        "peşə biliyinə və təcrübəsinə töhfəyə və (və ya) komandaların strateji fəaliyyətinin təhlilinə görə məsuliyyət daşımaq")),
    (S_("İş və ya təhsil sahəsinin ən qabaqcıl sərhədində və sahələrin qovşağında bilik"),
     S_("Tədqiqat və (və ya) innovasiyada kritik problemləri həll etmək, mövcud bilik və ya peşə təcrübəsini genişləndirmək və "
        "yenidən müəyyən etmək üçün lazım olan, sintez və qiymətləndirmə daxil olmaqla ən qabaqcıl və ixtisaslaşmış bacarıq "
        "və üsullar"),
     S_("Tədqiqat daxil olmaqla iş və ya təhsil şəraitinin ön cəbhəsində yeni ideya və proseslərin inkişafına davamlı "
        "bağlılıq, əhəmiyyətli nüfuz, yenilikçilik, müstəqillik, elmi və peşə dürüstlüyü nümayiş etdirmək")),
)
_LEVEL = (S_("1-ci səviyyə"), S_("2-ci səviyyə"), S_("3-cü səviyyə"), S_("4-cü səviyyə"), S_("5-ci səviyyə"), S_("6-cı səviyyə"),
          S_("7-ci səviyyə"), S_("8-ci səviyyə"))
BUILTIN: tuple[dict[str, Any], ...] = (
    {"key": "bloom", "version": "2001", "title": S_("Bloom taksonomiyası (yenilənmiş)"), "source_url": None,
     "note": S_("Anderson və Krathwohl (2001) əsasında; mətnlər işçi tərcümədir."),
     "items": [(code, "level", None, title, text) for code, title, text in (
         ("remember", S_("Xatırlamaq"), S_("Lazımi bilikləri uzunmüddətli yaddaşdan tapıb yada salmaq")),
         ("understand", S_("Anlamaq"), S_("Şifahi, yazılı və qrafik tədris materiallarından məna çıxarmaq")),
         ("apply", S_("Tətbiq etmək"), S_("Verilmiş vəziyyətdə proseduru yerinə yetirmək və ya ondan istifadə etmək")),
         ("analyze", S_("Təhlil etmək"), S_("Materialı tərkib hissələrinə ayırmaq və hissələrin bir-biri ilə və ümumi quruluşla "
                                            "əlaqəsini müəyyən etmək")),
         ("evaluate", S_("Qiymətləndirmək"), S_("Meyar və standartlar əsasında mühakimə yürütmək")),
         ("create", S_("Yaratmaq"), S_("Elementləri ahəngdar və ya işlək bütövdə birləşdirmək; onları yeni nümunə və ya "
                                       "quruluşda yenidən təşkil etmək")))]},
    {"key": "eqf", "version": "2017", "title": S_("Avropa Kvalifikasiyalar Çərçivəsi (EQF)"),
     "source_url": "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32017H0615(01)",
     "note": S_("Rəsmi mətn ingilis dilindədir (Şuranın 2017/C 189/03 tövsiyəsi, II əlavə); Azərbaycan və rus dillərində "
                "mətn işçi tərcümədir."),
     "items": [x for n, (k, s, r) in enumerate(_EQF, start=1) for x in (
         (str(n), "level", None, _LEVEL[n - 1], ""), (f"{n}-K", "knowledge", str(n), KIND_LABEL["knowledge"], k),
         (f"{n}-S", "skill", str(n), KIND_LABEL["skill"], s), (f"{n}-R", "responsibility", str(n), KIND_LABEL["responsibility"], r))]},
)
NOTES = {b["key"]: b["note"] for b in BUILTIN}


class FrameworkError(ValueError):
    """The file cannot be imported; ``args[0]`` is the reason in every language (``E``)."""


# ---------------------------------------------------------------- the file NIST publishes (pure)
def parse_cprt(raw: bytes) -> dict:
    """A framework file in NIST's CPRT JSON shape: {"documents": [one], "elements": [...], "relationships": [...]}.
    Every element is kept as an item of its own type, every relationship as a link; a work role's parent is its category
    (the category → work role relationship). Raises FrameworkError."""
    try:
        d = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):                 # UnicodeDecodeError is one; RecursionError: nesting too deep (SEC-FW-4)
        raise FrameworkError(E("Fayl JSON deyil")) from None
    docs, els, rels = (d.get("documents"), d.get("elements"), d.get("relationships")) if isinstance(d, dict) else (None, None, None)
    if not (isinstance(docs, list) and len(docs) == 1 and isinstance(docs[0], dict) and isinstance(els, list) and isinstance(rels, list)):
        raise FrameworkError(E("Fayl NIST-in CPRT formatında deyil: bir sənəd, elementlər və əlaqələr olmalıdır"))
    doc = docs[0]
    did, version, name = doc.get("doc_identifier"), doc.get("version"), doc.get("name")
    if not (isinstance(did, str) and isinstance(version, str) and isinstance(name, str)) or \
            not all(x.strip() and len(x) <= 300 for x in (did, version, name)) or len(version) > 40:
        raise FrameworkError(E("Sənədin identifikatoru, versiyası və adı yoxdur"))
    items: list[dict] = []
    kind_of: dict[str, str] = {}
    for e in els:
        code, kind = (e.get("element_identifier"), e.get("element_type")) if isinstance(e, dict) else (None, None)
        title, text = (e.get("title"), e.get("text")) if isinstance(e, dict) else (None, None)
        if not (isinstance(code, str) and 0 < len(code) <= 64 and isinstance(kind, str) and KIND.fullmatch(kind)
                and isinstance(title, str) and len(title) <= 1000 and isinstance(text, str) and len(text) <= 10000
                and e.get("doc_identifier") == did):
            raise FrameworkError(E("Element düzgün deyil: {code}", code=Lit(str(code)[:64])))
        if code in kind_of:
            raise FrameworkError(E("Element iki dəfə yazılıb: {code}", code=Lit(code)))
        kind_of[code] = kind
        items.append({"code": code, "kind": kind, "title": title, "text": text})
    links: dict[tuple[str, str], None] = {}
    for r in rels:
        s, t = (r.get("source_element_identifier"), r.get("dest_element_identifier")) if isinstance(r, dict) else (None, None)
        if s not in kind_of or t not in kind_of:
            raise FrameworkError(E("Əlaqə faylda olmayan elementə istinad edir: {code}", code=Lit(str(s if s not in kind_of else t)[:64])))
        links[(s, t)] = None
    parent = {t: s for s, t in links if kind_of[s] == "category" and kind_of[t] == "work_role"}
    for i in items:
        i["parent"] = parent.get(i["code"])
    return {"key": "nice" if did.startswith("SP_800_181") else did.lower(), "version": version.strip(), "title": name.strip(),
            "website": doc.get("website") if isinstance(doc.get("website"), str) else None, "items": items, "links": list(links)}


def _vkey(v: str) -> tuple:
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"[.\-]", v))


# ---------------------------------------------------------------- import and the built-in frameworks
def import_file(c, raw: bytes) -> dict:
    """Import a framework file in one transaction of the caller: {status: imported | unchanged, framework, file, stored, links}.
    ``file`` counts the file's elements per type, ``stored`` the database's items of that version per kind."""
    if len(raw) > MAX_FILE:
        raise FrameworkError(E("Fayl çox böyükdür"))
    f = parse_cprt(raw)
    digest = hashlib.sha256(raw).hexdigest()
    known = KNOWN.get((f["key"], f["version"]))
    if known and digest != known[0]:
        raise FrameworkError(E("Fayl NIST-in dərc etdiyi {version} versiyası ilə eyni deyil (SHA-256 uyğun gəlmir): dəyişdirilmiş "
                               "nüsxə idxal olunmur", version=Lit(f["version"])))
    counts = dict(sorted(Counter(i["kind"] for i in f["items"]).items()))
    old = repo.framework_version(c, f["key"], f["version"])
    if old and old["sha256"] != digest:
        raise FrameworkError(E("{version} versiyası artıq başqa fayldan idxal olunub: versiya dəyişdirilmir, yeni versiya yeni "
                               "fayldır", version=Lit(f["version"])))
    if old:
        fid, status = old["id"], "unchanged"
    else:                                                # an unverified version names no source: its file's own claim is not one (SEC-FW-3)
        fid, status = repo.add_framework(c, f["key"], f["version"], f["title"], known[1] if known else None, digest, len(raw),
                                         json.dumps(counts), len(f["links"]), iso(now())), "imported"
        ids = repo.add_items(c, fid, f["items"])
        repo.add_links(c, [(ids[s], ids[t]) for s, t in f["links"]])
    return {"status": status, "framework": {"id": fid, "key": f["key"], "version": f["version"], "sha256": digest},
            "file": counts, "stored": repo.kind_counts(c, fid), "links": {"file": len(f["links"]), "stored": repo.link_count(c, fid)}}


def ensure_builtin(c) -> None:
    """Bloom and EQF in every database (store.init, prod too); a changed text replaces the stored one, ids stay."""
    at = iso(now())
    for b in BUILTIN:
        counts = dict(sorted(Counter(k for _, k, *_ in b["items"]).items()))
        fid = repo.put_builtin(c, b["key"], b["version"], b["title"], b["source_url"], json.dumps(counts), at)
        for code, kind, parent, title, text in b["items"]:
            repo.put_item(c, fid, code, kind, parent, title, text)


# ---------------------------------------------------------------- reading and the picker
def verified(f: dict) -> bool:
    """Built in, or the file NIST published for a known version (its SHA-256 in ``KNOWN``)."""
    return bool(f["builtin"]) or KNOWN.get((f["key"], f["version"]), ("",))[0] == f["sha256"]


def _fw(f: dict) -> dict:
    counts = J(f["counts"], {})
    return {k: f[k] for k in ("id", "key", "version", "title", "source_url", "sha256", "imported_at", "links")} | {
        "builtin": bool(f["builtin"]), "verified": verified(f), "note": NOTES.get(f["key"]) if f["builtin"] else None, "counts": counts,
        "kinds": [{"kind": k, "label": KIND_LABEL.get(k, k), "count": n, "mappable": k in MAPPABLE} for k, n in counts.items()]}


def listing(c) -> list[dict]:
    """Every framework version, the built-in ones first; within a key the verified versions first, each newest first."""
    out = sorted(repo.frameworks(c), key=lambda f: _vkey(f["version"]), reverse=True)
    return [_fw(f) for f in sorted(out, key=lambda f: (-f["builtin"], f["key"], not verified(f)))]


def _item(r: dict) -> dict:
    return {k: r[k] for k in ("id", "code", "kind", "parent", "title", "text")} | {"label": KIND_LABEL.get(r["kind"], r["kind"])}


def search(c, fid: int, q, kind, role, page: int, size: int) -> dict | None:
    """One page of a framework's items: ``q`` in the code, title or text; ``kind``; ``role``: a work role's code, its
    statements only. None when the framework or the role does not exist. shortcut: the search reads the stored text, so a
    built-in framework (32 items at most) is searched in Azerbaijani only; a translated search if users ask for one."""
    fw = repo.framework(c, fid)
    if not fw:
        return None
    role_id = None
    if role:
        r = repo.item(c, fid, str(role)[:64])
        if not r or r["kind"] != "work_role":
            return None
        role_id = r["id"]
    text = " ".join(str(q or "").split())[:100]
    like = "%" + re.sub(r"([\\%_])", r"\\\1", text) + "%" if text else None
    kind = kind if isinstance(kind, str) and KIND.fullmatch(kind) else None
    found = repo.search_items(c, fid, kind, like, role_id, size + 1, (page - 1) * size, written=bool(fw["builtin"]))
    return {"framework": _fw(fw), "items": [_item(r) for r in found[:size]], "page": page, "more": len(found) > size}


def outcome_items(c, cid: int, outcomes: list[str] | None = None, frozen: str | None = None) -> dict[str, list[dict]]:
    """{outcome code: its tags}; ``outcomes``: only these codes (the outcomes of the version shown); ``frozen``: a
    submitted version's own map (``syllabus_versions.tags``), read instead of the course's current one (SEC-FW-1)."""
    if frozen is None:
        found = repo.course_items(c, cid)
    else:
        m = J(frozen, {})
        by = {r["id"]: r for r in repo.items_full(c, sorted({i for ids in m.values() for i in ids}))}
        found = sorted(({**by[i], "outcome": o, "mapped_at": None} for o, ids in m.items() for i in ids if i in by),
                       key=lambda r: (r["outcome"], r["key"], r["version"], r["kind"], r["code"]))
    out: dict[str, list[dict]] = {}
    for r in found:
        if outcomes is None or r["outcome"] in outcomes:
            out.setdefault(r["outcome"], []).append(_item(r) | {"framework_id": r["framework_id"], "key": r["key"], "version": r["version"],
                                                                 "builtin": bool(r["builtin"]), "mapped_at": r["mapped_at"]})
    return out


def course_map(c, user, cid: int) -> dict | None:
    if not service.may_read(c, user, cid):
        return None
    return {"outcomes": outcome_items(c, cid), "can_map": user["role"] == "teacher"}


def set_outcome(c, user, cid: int, oid: str, body) -> tuple[str, object]:
    """Replace one outcome's tags: ('ok', map) | ('missing', reason) | ('invalid', reason). A teacher of the course only
    (its head or a teacher of one of its units); the outcome must be one of the latest saved version."""
    co = repo.course(c, cid)
    if not co or user["role"] != "teacher" or not service.may_read(c, user, cid):
        return "missing", E("Fənn tapılmadı")
    latest = repo.latest(c, cid)
    if oid not in ({o["id"] for o in J(latest["data"], {}).get("outcomes", [])} if latest else set()):
        return "missing", E("Təlim nəticəsi tapılmadı: əvvəlcə sillabusu saxlayın")
    ids = body.ids("items", MAX_TAGS + 1)
    if len(ids) > MAX_TAGS or len(set(ids)) != len(ids):
        return "invalid", E("Bir nəticəyə ən çox {n} fərqli çərçivə bəndi əlavə olunur", n=MAX_TAGS)
    found = {r["id"]: r for r in repo.items_by_ids(c, ids)}
    if len(found) != len(ids):
        return "invalid", E("Çərçivə bəndi tapılmadı")
    if any(r["kind"] not in MAPPABLE for r in found.values()):
        return "invalid", E("Nəticəyə yalnız bəyanat və ya səviyyə əlavə olunur")
    have, at = set(repo.outcome_item_ids(c, cid, oid)), iso(now())
    added, gone = [i for i in ids if i not in have], [i for i in have if i not in found]
    for i in added:
        repo.map_item(c, cid, oid, i, user["id"], at)
    for i in gone:
        repo.unmap_item(c, cid, oid, i)
    if added or gone:
        audit(c, user["id"], "syllabus_outcome_map", "course", f"{co['code']} · {oid} · +{len(added)} −{len(gone)}")
    return "ok", course_map(c, user, cid)


# ---------------------------------------------------------------- the coverage report of a programme
COVERAGE_ROLES = ("dept_head", "academic_office", "leader", "admin")


def _covers(c, user, spec: dict) -> bool:
    """Leadership reads every programme; the others within their grants, as the timetable builder reads them (Task 48):
    unscoped, or the programme's faculty or department."""
    if user["role"] == "leader":
        return True
    from ..timetable import builder                    # here: the builder imports modules that load after this one
    s = builder.scope_of(c, user)
    return s["all"] or spec["department_id"] in s["departments"] or spec["faculty_id"] in s["faculties"]


def programmes(c, user) -> list[dict]:
    return [p for p in repo.specialties(c) if _covers(c, user, p)]


def _report(c, user, sid: int, fid: int | None):
    spec = repo.specialty(c, sid)
    if not spec or not _covers(c, user, spec):
        return None
    if fid:
        fw = repo.framework(c, fid)
    else:
        nice = [f for f in repo.frameworks(c) if f["key"] == "nice"]
        fw = max(nice, key=lambda f: (verified(f), _vkey(f["version"]))) if nice else None   # an unverified file is never the default
    if not fw:
        return None
    courses = repo.programme_courses(c, sid)
    # (course, outcome) -> its text: the published version with the map it was submitted with; without one, the latest
    # version with the live map, for a caller who may read the course's syllabus (SEC-FW-2: a draft is its readers' only)
    texts: dict[tuple[int, str], str] = {}
    maps: list[tuple[int, str, int]] = []
    live: list[int] = []
    for co in courses:
        v = repo.published(c, co["id"])
        if v:
            maps += [(co["id"], o, i) for o, ids in J(v["tags"], {}).items() for i in ids]
        elif service.may_read(c, user, co["id"]):
            v = repo.latest(c, co["id"])
            live.append(co["id"])
        for o in J(v["data"], {}).get("outcomes", []) if v else []:
            texts[(co["id"], o["id"])] = o["text"]
    maps += [(m["course_id"], m["outcome"], m["item_id"]) for m in repo.maps_for_courses(c, live, fw["id"])]
    name = {co["id"]: co for co in courses}
    covered: dict[int, list[dict]] = {}
    for cid, oid, iid in maps:
        if (cid, oid) in texts:
            co = name[cid]
            covered.setdefault(iid, []).append({"course_id": cid, "course": co["code"], "name": co["name"], "outcome": oid,
                                                "text": texts[(cid, oid)]})
    per: dict[int, list[dict]] = {}
    for s in repo.role_statements(c, fw["id"], STATEMENTS):
        per.setdefault(s["role_id"], []).append(s)
    cats = {r["code"]: r["title"] for r in repo.items_of_kind(c, fw["id"], "category")}
    return spec, fw, courses, texts, covered, per, cats, repo.items_of_kind(c, fw["id"], "work_role")


def coverage(c, user, sid: int, fid: int | None, role: str | None) -> dict | None:
    """Per work role: its statements by kind, how many an outcome covers; with ``role``, that role's statements with the
    outcomes covering each (an empty ``covered_by`` is an uncovered statement). None: outside the caller's scope."""
    rep = _report(c, user, sid, fid)
    if rep is None:
        return None
    spec, fw, courses, texts, covered, per, cats, roles = rep
    out, detail = [], None
    for r in roles:
        ss = per.get(r["id"], [])
        kinds = {k: {"total": sum(s["kind"] == k for s in ss), "covered": sum(s["kind"] == k and s["id"] in covered for s in ss)}
                 for k in STATEMENTS}
        out.append({"code": r["code"], "title": r["title"], "category": cats.get(r["parent"] or ""), "kinds": kinds,
                    "total": len(ss), "covered": sum(s["id"] in covered for s in ss)})
        if r["code"] == role:
            detail = {"code": r["code"], "title": r["title"], "text": r["text"],
                      "statements": [{"code": s["code"], "kind": s["kind"], "text": s["text"], "covered_by": covered.get(s["id"], [])}
                                     for s in ss]}
    if role and detail is None:
        return None
    return {"programme": spec, "framework": _fw(fw), "courses": len(courses), "outcomes": len(texts),
            "labels": {k: KIND_LABEL[k] for k in STATEMENTS}, "roles": out, "role": detail}


def coverage_csv(c, user, sid: int, fid: int | None, lang: str) -> tuple[str, str] | None:
    """(file name, CSV text): one row per work role and statement, UTF-8 with a BOM so that Excel reads the letters."""
    rep = _report(c, user, sid, fid)
    if rep is None:
        return None
    spec, fw, _, _, covered, per, cats, roles = rep
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([S(h, lang) for h in (S_("İş rolu"), S_("İş rolunun adı"), S_("Kateqoriya"), S_("Növ"), S_("Bəyanat"),
                                     S_("Bəyanatın mətni"), S_("Örtülür"), S_("Fənn və təlim nəticəsi"))])
    for r in roles:
        for s in per.get(r["id"], []):
            by = covered.get(s["id"], [])
            w.writerow([csv_cell(x) for x in (r["code"], r["title"], cats.get(r["parent"] or "", ""), S(KIND_LABEL[s["kind"]], lang),
                                              s["code"], s["text"], S("Bəli" if by else "Xeyr", lang),
                                              "; ".join(f"{b['course']} {b['outcome']}: {b['text']}" for b in by))])
    safe = re.sub(r"[^A-Za-z0-9.-]+", "-", f"{spec['code']}-{fw['key']}-{fw['version']}")
    return f"framework-coverage-{safe}.csv", "\ufeff" + buf.getvalue()
