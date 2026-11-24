"""The structured syllabus (tasks/todo.md, Task 23): read, a first draft, a new version on every save; a copy of another
course's published syllabus; the approval queue and a term's overview."""
from __future__ import annotations

import csv
import io
import json
import re

from ...core import tenant
from ...core.i18n import E, S, S_, T3, Lit
from ...legacy.store import J, audit, iso, notify, now
from ..integration.domain import csv_cell, norm
from . import domain, repo


def may_read(c, user, cid: int) -> bool:
    """The course's teachers, a department head whose grant covers it, and the readers of every course."""
    from ..journal import service as journal     # here: journal imports the legacy layer this module is loaded from
    return journal.can_read_course(c, user, cid)


def may_write(user, co: dict) -> bool:
    """The syllabus is the course head's: one author per course, the department head approves it (Task 25)."""
    return user["role"] == "teacher" and co["teacher_id"] == user["id"]


def _prereq(c, co: dict) -> list:
    """The course's prerequisite field (Task 17) as the syllabus's first list: a part that names a registry course
    exactly, by its code or its name, becomes that course; the rest stays text."""
    texts = [p.strip() for p in str(co.get("prereq") or "").split(",") if p.strip() and p.strip() != "—"]
    found = repo.registry_match(c, texts)
    return [{"code": found[t]} if found.get(t) not in (None, co["code"]) else t for t in texts]


def named(c, data: dict) -> dict:
    """The syllabus with its registry prerequisites named ({code, name}); a code the registry no longer has, no name."""
    codes = domain.prereq_codes(data)
    if not codes:
        return data
    names = repo.registry_names(c, codes)
    return data | {"prerequisites": [x | {"name": names.get(x["code"])} if isinstance(x, dict) else x for x in data["prerequisites"]]}


def _registry_problem(c, co: dict, data: dict) -> dict | None:
    codes = domain.prereq_codes(data)
    if co["code"] in codes:
        return E("Fənn özünün prerekviziti ola bilməz")
    known = repo.registry_names(c, codes) if codes else {}
    missing = [x for x in codes if x not in known]
    return E("Prerekvizit fənn reyestrdə tapılmadı: {code}", code=Lit(missing[0])) if missing else None


def imported(c, cid: int) -> dict[str, float]:
    return domain.workload_from_units(repo.units(c, cid))


def _version(c, v) -> dict | None:
    return ({"id": v["id"], "version": v["version"], "status": v["status"], "created_at": v["created_at"], "data": named(c, J(v["data"], {})),
             "source": J(v["source"], None)} if v else None)


def state(c, user, cid: int) -> dict | None:
    co = repo.course(c, cid)
    if not co or not may_read(c, user, cid):
        return None
    latest, forma3 = _version(c, repo.latest(c, cid)), imported(c, cid)
    from . import frameworks                     # here: frameworks imports this module
    return {"checks": domain.checks(latest["data"], frameworks.outcome_items(c, cid)) if latest else None,
            "course": {k: co[k] for k in ("id", "code", "name", "credits")}, "latest": latest,
            "versions": [x | {"source": J(x["source"], None)} for x in repo.versions(c, cid)],
            "published": _version(c, repo.published(c, cid)), "imported": forma3,
            "diff": domain.workload_diff(latest["data"].get("workload", {}), forma3) if latest else [],
            "can_edit": may_write(user, co), "limit_percent": tenant.load(c)["attendance"]["limit_percent"],
            "actions": actions(c, user, co, repo.latest(c, cid)), "steps": repo.steps(c, latest["id"]) if latest else []}


def draft(c, user, cid: int) -> dict | None:
    """A first draft, not saved: from a syllabus saved before Task 23, else from the syllabus assistant."""
    co = repo.course(c, cid)
    if not co or not may_write(user, co):
        return None
    old = repo.legacy(c, cid)
    gen = J(old["data"], None) if old else None
    if not isinstance(gen, dict):
        from ...legacy import r_academy         # the assistant stays as the first fill (Task 23)
        gen = r_academy.build_syllabus(c, co)
    return named(c, domain.initial(gen, tenant.load(c), imported(c, cid), _prereq(c, co)))


def _store(c, user, co: dict, clean: dict, source: dict | None = None) -> tuple[str, object]:
    blob = json.dumps(clean, ensure_ascii=False)
    if len(blob) > 200_000:
        return "invalid", E("Sillabus çox böyükdür")
    return "ok", repo.add_version(c, co["id"], blob, user["id"], iso(now()), json.dumps(source, ensure_ascii=False) if source else None)


def save(c, user, cid: int, body) -> tuple[str, object]:
    """('ok', state) | ('missing', None) | ('forbidden', reason) | ('invalid', reason) | ('stale', reason)."""
    co = repo.course(c, cid)
    if not co or not may_read(c, user, cid):
        return "missing", None
    if not may_write(user, co):
        return "forbidden", E("Sillabusu fənnin rəhbər müəllimi yazır")
    base, latest = body.get("base"), repo.latest(c, cid)
    if isinstance(base, int) and not isinstance(base, bool) and (latest["version"] if latest else 0) != base:
        return "stale", E("Bu müddətdə sillabusun yeni versiyası saxlanıb: səhifəni yeniləyin")
    clean, problem = domain.validate(body.get("data"), tenant.load(c))
    problem = problem or _registry_problem(c, co, clean)
    if problem:
        return "invalid", problem
    status, value = _store(c, user, co, clean)
    if status != "ok":
        return status, value
    repo.unmap_gone(c, cid, [o["id"] for o in clean["outcomes"]])
    audit(c, user["id"], "syllabus_saved", "course", f"{co['code']} · v{(latest['version'] if latest else 0) + 1}")
    return "ok", state(c, user, cid)


def version(c, user, cid: int, vid: int) -> dict | None:
    """A version with its outcome map (a submitted one's own, frozen at submission; a draft's the course's current one)
    and the approver's warnings (``domain.checks``)."""
    v = repo.version(c, cid, vid) if may_read(c, user, cid) else None
    if not v:
        return None
    from . import frameworks
    out = _version(c, v) or {}
    tags = frameworks.outcome_items(c, cid, [o["id"] for o in out["data"].get("outcomes", [])], v["tags"])
    return out | {"tags": tags, "checks": domain.checks(out["data"], tags)}


def printable(c, user, cid: int, vid: int | None) -> tuple[dict, dict, dict | None] | None:
    """(course, syllabus data, version or None) for the printable page: the asked version, else the latest one, else an
    unsaved first draft (marked as such on the page). A version's ``tags`` is its own outcome map once submitted."""
    co = repo.course(c, cid)
    if not co:
        return None
    v = repo.version(c, cid, vid) if vid else repo.latest(c, cid)
    if v:
        return co, named(c, J(v["data"], {})), {**(_version(c, v) or {}), "tags": v["tags"]}
    old = repo.legacy(c, cid)
    gen = J(old["data"], None) if old else None
    if not isinstance(gen, dict):
        from ...legacy import r_academy
        gen = r_academy.build_syllabus(c, co)
    return co, named(c, domain.initial(gen, tenant.load(c), imported(c, cid), _prereq(c, co))), None


# ---------------------------------------------------------------- approval and publication (Task 25)
def _covers(c, user, co: dict) -> bool:
    from ..journal import service as journal     # a department head's grant decides which courses are theirs (Task 13)
    return journal.may_correct(c, user, co)


def actions(c, user, co: dict, v: dict | None) -> list[str]:
    """The steps this user may take on this version now."""
    if not v:
        return []
    cur = repo.published(c, co["id"])
    return _actions(user, co, v, cur["version"] if cur else None, user["role"] != "dept_head" or _covers(c, user, co))


def _actions(user, co: dict, v: dict, published: int | None, covered: bool) -> list[str]:
    """``published``: the course's published version number; ``covered``: a department head's grant covers the course."""
    out = []
    for action in domain.STEPS:
        if domain.step(v["status"], action, user["role"]) is None:
            continue
        if user["role"] == "teacher" and not may_write(user, co):
            continue
        if user["role"] == "dept_head" and not covered:
            continue
        if action == "publish" and published and published > v["version"]:
            continue                                     # Checkpoint D, CR-5: an older version never replaces a newer one
        out.append(action)
    return out


def act(c, user, cid: int, vid: int, action: str, body) -> tuple[str, object]:
    """('ok', state) | ('missing', None) | ('forbidden', reason) | ('invalid', reason) | ('blocked', reason)."""
    co, v = repo.course(c, cid), repo.version(c, cid, vid)
    if not co or not v or not may_read(c, user, cid):
        return "missing", None
    new = domain.step(v["status"], action, user["role"])
    if new is None or action not in actions(c, user, co, v):
        return "forbidden", E("Bu addım sizin rolunuza aid deyil")
    latest = repo.latest(c, cid)
    if action == "submit" and latest["id"] != vid:
        return "invalid", E("Yalnız son versiya təqdim olunur")
    note = " ".join(str(body.get("note") or "").split())[:1000]
    if action == "return" and len(note) < 3:
        return "invalid", E("Geri qaytarmanın səbəbini yazın")
    at = iso(now())
    if action == "publish":
        graded = repo.has_grades(c, cid)
        if graded and body.get("override") is True and len(note) < 3:      # the box is ticked: only the reason is missing (D7)
            return "blocked", E("Xüsusi icazənin səbəbini şərhdə yazın")
        if graded and body.get("override") is not True:
            return "blocked", E("Bu fəndə artıq bal yazılıb: dərc etmək üçün tədris hissəsinin xüsusi icazəsi və səbəbin göstərilməsi lazımdır")
        data, rules = J(v["data"], {}), tenant.load(c)
        modes, locked = domain.tutor_modes(data["rules"]["ai_policy"])
        repo.publish_course(c, cid, json.dumps(domain.course_grading(data, rules["grading"]), ensure_ascii=False),
                            data["rules"]["attendance_limit"], json.dumps(modes), locked)
        from ..journal import service as journal
        journal.refresh_finals(c, cid, repo.students(c, cid))      # the course's components and limit changed
        if graded:
            audit(c, user["id"], "syllabus_publish_override", "course", f"{co['code']} · v{v['version']} · {note}")
    if action == "submit":
        repo.freeze_tags(c, vid, cid)                    # what is approved and published is this map, not a later one
    repo.set_status(c, vid, new, note, user["id"], at)
    repo.add_step(c, vid, action, user["id"], note, at)
    audit(c, user["id"], f"syllabus_{action}", "course", f"{co['code']} · v{v['version']}" + (f" · {note}" if note else ""))
    if action in ("return", "publish") and v["author_id"]:
        title = (T3("Sillabus geri qaytarıldı: {course}", course=co["name"]) if action == "return"
                 else T3("Sillabus dərc olundu: {course}", course=co["name"]))
        notify(c, [v["author_id"]], "syllabus", title, note, f"/teacher/syllabus?course={cid}")
    return "ok", state(c, user, cid)


QUEUE_PAGE = 50


def queue(c, user, page: int = 1) -> dict:
    """The versions waiting for this user, a page at a time: submitted ones for a department head (of the courses the
    grant covers), approved ones for the academic office; an administrator sees both. A page costs the same few queries
    whatever its length (AR-11): the waiting versions without their data, then the page's data, decisions and units."""
    statuses = {"dept_head": ("submitted",), "academic_office": ("approved",), "admin": ("submitted", "approved")}.get(user["role"], ())
    found = repo.pending(c, statuses) if statuses else []
    if user["role"] == "dept_head":
        from ..timetable import builder                # the grant's scope, as the journal and the timetable builder read it
        scope = builder.scope_of(c, user)
        found = [v for v in found if builder.covers(scope, v)]
    part = found[(page - 1) * QUEUE_PAGE:page * QUEUE_PAGE]
    cids = sorted({v["course_id"] for v in part})
    decided: dict[int, list[dict]] = {}
    for d in repo.decided(c, cids):
        decided.setdefault(d["course_id"], []).append(d)
    pubs = {k: max((d for d in ds if d["status"] == "published"), key=lambda d: d["version"], default=None) for k, ds in decided.items()}
    backs = {v["id"]: domain.answered_return(decided.get(v["course_id"], []), v["version"]) for v in part}   # a resubmission (D5)
    ids = {v["id"] for v in part} | {d["id"] for d in [*pubs.values(), *backs.values()] if d}
    data = {k: J(x, {}) for k, x in repo.data_of(c, sorted(ids)).items()}
    units: dict[int, list[dict]] = {}
    for u in repo.units_of(c, cids):
        units.setdefault(u["course_id"], []).append(u)
    items = []
    for v in part:
        d, pub, back = data[v["id"]], pubs.get(v["course_id"]), backs[v["id"]]
        items.append({k: v[k] for k in ("id", "course_id", "version", "status", "created_at", "code", "name", "author")} |
                     {"actions": _actions(user, {"id": v["course_id"], "teacher_id": v["teacher_id"]}, v, pub["version"] if pub else None, True),
                      "published_id": pub["id"] if pub else None,
                      "forma3": domain.workload_diff(d.get("workload", {}), domain.workload_from_units(units.get(v["course_id"], []))),
                      "changes": len(domain.diff(data[pub["id"]], d)) if pub else None,
                      "returned_id": back["id"] if back else None, "returned_version": back["version"] if back else None,
                      "returned_note": back["note"] if back else None,
                      "changes_returned": len(domain.diff(data[back["id"]], d)) if back else None})
    return {"items": items, "total": len(found), "page": page, "pages": max(1, -(-len(found) // QUEUE_PAGE)), "page_size": QUEUE_PAGE}


def compare(c, user, cid: int, a: int, b: int) -> list[dict] | None:
    va, vb = repo.version(c, cid, a), repo.version(c, cid, b)
    if not va or not vb or not may_read(c, user, cid):
        return None
    return domain.diff(J(va["data"], {}), J(vb["data"], {}))


def published_for(c, user, cid: int) -> dict | None:
    """The published syllabus of a course: what its students see (only that version), and its staff."""
    if user["role"] == "student":
        if not repo.enrolled(c, cid, user["id"]):
            return None
    elif not may_read(c, user, cid) and not _earlier_offering(c, user, cid):
        return None
    return _version(c, repo.published(c, cid))


def _earlier_offering(c, user, cid: int) -> bool:
    """SEC-8D5-1: a course's author reads the published syllabus of an earlier offering of the same course, the one
    ``sources`` offers to copy: what a copy brings into the draft is readable before it is copied."""
    co = repo.course(c, cid) if user["role"] == "teacher" else None
    return co is not None and any(any(x["course_id"] == cid for x in sources(c, user, m) or [])
                                  for m in repo.authored(c, co["code"], user["id"], cid))


def exam_defaults(c, cid: int) -> dict | None:
    """What the course's published syllabus sets for a new exam (plan A12, Task 25); None before a publication."""
    pub = repo.published(c, cid)
    return (domain.exam_defaults(J(pub["data"], {})) or None) if pub else None


# ---------------------------------------------------------------- a copy of another course's published syllabus
def sources(c, user, cid: int) -> list[dict] | None:
    """The published syllabi a draft of this course can start from: another offering of the same course (its code) in an
    earlier term, or any course the teacher heads or teaches. None: not the course's author."""
    co = repo.course(c, cid)
    if not co or not may_write(user, co):
        return None
    start = repo.term_start(c, co["term_id"])
    return [{k: x[k] for k in ("course_id", "code", "name", "term", "version_id", "version", "decided_at")}
            for x in repo.copy_sources(c, cid, co["code"], user["id"])
            if x["mine"] or (start and x["teaching_start"] and x["teaching_start"] < start)]   # no term: nothing is earlier


def copy_from(c, user, cid: int, body) -> tuple[str, object]:
    """A new draft version from a source of ``sources``: its outcomes, plan, assessment, rules, prerequisites, literature
    and outcome tags; the contact hours from this course's Forma №3. ('ok', state) | ('missing'|'forbidden'|'invalid', …)."""
    co = repo.course(c, cid)
    if not co or not may_read(c, user, cid):
        return "missing", None
    if not may_write(user, co):
        return "forbidden", E("Sillabusu fənnin rəhbər müəllimi yazır")
    src = body.get("from")
    found = next((x for x in sources(c, user, cid) or [] if x["course_id"] == src), None)
    if not found:
        return "invalid", E("Bu sillabusu köçürmək mümkün deyil: bu fənnin əvvəlki semestrdəki və ya tədris etdiyiniz fənnin dərc olunmuş sillabusunu seçin")
    v = repo.version(c, found["course_id"], found["version_id"])
    rules = tenant.load(c)
    data = domain.copied(J(v["data"], {}), imported(c, cid), float(rules["attendance"]["limit_percent"]))
    data["prerequisites"] = [x for x in data.get("prerequisites", []) if x != {"code": co["code"]}]   # the course itself is not its own
    clean, problem = domain.validate(data, rules)
    problem = problem or _registry_problem(c, co, clean)
    if problem:
        return "invalid", problem
    source = {k: found[k] for k in ("course_id", "code", "name", "term", "version")}
    status, value = _store(c, user, co, clean, source)
    if status != "ok":
        return status, value
    # a version without its own tags: the source's working map, only for a course the author reads (SEC-8D5-1)
    tags = J(v["tags"], None) if v["tags"] else repo.live_map(c, found["course_id"]) if may_read(c, user, found["course_id"]) else {}
    keep = {o["id"] for o in clean["outcomes"]}
    repo.replace_map(c, cid, [(o, i) for o, ids in (tags or {}).items() if o in keep for i in ids], user["id"], iso(now()))
    audit(c, user["id"], "syllabus_copied", "course", f"{co['code']} · v{repo.latest(c, cid)['version']} · {found['code']} v{found['version']}")
    return "ok", state(c, user, cid)


# ---------------------------------------------------------------- the overview of a term
OVERVIEW_ROLES = ("office", "academic_office", "leader")
OVERVIEW_PAGE = 100
STATE_LABEL = {"none": S_("Sillabus yoxdur"), "draft": S_("Qaralama"), "submitted": S_("Təqdim olunub"),
               "approved": S_("Kafedra təsdiqləyib"), "published": S_("Dərc olunub")}
OVERVIEW_CSV = (S_("Kafedra"), S_("Fənnin kodu"), S_("Fənn"), S_("Müəllim"), S_("Vəziyyət"), S_("Son versiya"), S_("Dərc olunmuş versiya"))


def _overview(c, user, term_id: int | None, state_: str | None, department_id: int | None, q: str | None):
    """(term, terms, departments, counts, rows) or None for an unknown term. Leadership reads every course; the academic
    office and the dean's office those their scope covers, as the timetable builder reads it. The counts follow the
    department and the search, not the state filter."""
    terms = repo.terms(c)
    if not term_id:
        from ..directory import service as directory
        cur = directory.current_term(c)
        term_id = cur["id"] if cur else (terms[0]["id"] if terms else None)
    term = next((t for t in terms if t["id"] == term_id), None)
    if term is None:
        return None
    found = repo.term_courses(c, term["id"])
    if user["role"] != "leader":
        from ..timetable import builder
        scope = builder.scope_of(c, user)
        found = [r for r in found if builder.covers(scope, r)]
    deps = sorted({(r["department_id"], r["department"] or "") for r in found if r["department_id"]}, key=lambda d: norm(d[1]))
    if department_id:
        found = [r for r in found if r["department_id"] == department_id]
    if q and (needle := norm(q)):
        found = [r for r in found if needle in norm(r["code"]) or needle in norm(r["name"])]
    counts = dict.fromkeys(domain.OVERVIEW, 0)
    for r in found:
        r["state"] = domain.overview_state(r["status"])
        counts[r["state"]] += 1
    if state_ in domain.OVERVIEW:
        found = [r for r in found if r["state"] == state_]
    return term, terms, [{"id": i, "name": n} for i, n in deps], counts, found


ROW = ("id", "code", "name", "department_id", "department", "teacher", "state", "status", "latest", "published")


def overview(c, user, term_id: int | None, state_: str | None, department_id: int | None, q: str | None, page: int = 1) -> dict | None:
    got = _overview(c, user, term_id, state_, department_id, q)
    if got is None:
        return None
    term, terms, deps, counts, found = got
    return {"term": term, "terms": terms, "departments": deps, "counts": counts, "total": len(found), "page": page,
            "pages": max(1, -(-len(found) // OVERVIEW_PAGE)), "page_size": OVERVIEW_PAGE,
            "items": [{k: r[k] for k in ROW} for r in found[(page - 1) * OVERVIEW_PAGE:page * OVERVIEW_PAGE]]}


def overview_csv(c, user, term_id: int | None, state_: str | None, department_id: int | None, q: str | None, lang: str) -> tuple[str, str] | None:
    """(file name, CSV text): every filtered course, UTF-8 with a BOM so that a spreadsheet reads the letters; a cell a
    spreadsheet would run as a formula starts with a quote."""
    got = _overview(c, user, term_id, state_, department_id, q)
    if got is None:
        return None
    term, found = got[0], got[4]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([S(h, lang) for h in OVERVIEW_CSV])
    for r in found:
        w.writerow([csv_cell(x) for x in (r["department"], r["code"], r["name"], r["teacher"], S(STATE_LABEL[r["state"]], lang),
                                          r["latest"], r["published"])])
    safe = re.sub(r"[^A-Za-z0-9.-]+", "-", str(term["code"]))
    return f"syllabus-overview-{safe}.csv", "\ufeff" + buf.getvalue()
