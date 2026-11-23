"""The semester timetable builder (tasks/todo.md, Task 48, slice 2): who may see and change what (scope), the readiness
checklist, the term's inputs (unit needs, group shifts, teachers' availability with the cap), runs in the job runner
(snapshot, solve in chunks, check), drafts and the editor (options, a move with a live clash check, locks) and the
exactly-once publication of a version to timetable rows, lessons and notifications.

Handlers raise ``HTTPError`` with a translated message; an id outside the caller's scope answers 404, as
``course_access`` does (design C24). No request computes a whole term: runs, checks and the publication are job work.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import zlib
from datetime import date, timedelta

from ...core import perms, tenant
from ...core.i18n import LANGS, E, S, S_, T3
from ...core.web import HTTPError
from ...legacy.store import J, audit, iso, notify, now
from ..directory import service as directory
from . import domain, repo, solver
from . import service as rows_service

RUN_KINDS = ("precheck", "solve", "check")
EDITABLE = ("draft", "review")
VISIBLE_PREPARE = ("review", "published", "superseded")      # what a timetable.prepare-only holder sees (design C12)
ROWS_BATCH, DROP_BATCH, LESSON_BATCH, NOTIFY_BATCH = 2000, 500, 200, 2000
CACHE: dict[int, tuple[str, solver.Model]] = {}               # the runner keeps one run's model between chunks (§8.1)

TITLES = {   # readiness lines, publish gate and slot reasons: one catalogue key per code
    "term_dates": S_("Semestrin dərs tarixləri"), "pattern": S_("Saatların həftələrə bölgü qaydası"),
    "lesson_times": S_("Zəng cədvəli və növbələr"), "group_shifts": S_("Qrupların növbəsi"), "rooms": S_("Otaqlar"),
    "availability": S_("Müəllimlərin məşğulluq vaxtları"), "availability_late": S_("Məşğulluq vaxtlarının son tarixi keçib"),
    "availability_pending": S_("Kafedra müdirinin təsdiqini gözləyən məşğulluq cədvəlləri"),
    "unit_groups": S_("Qrupu olmayan tədris vahidləri"), "vacancies": S_("Müəllimi olmayan tədris vahidləri"),
    "defaults": S_("Təsdiqlənməmiş standart ayarlar"),
    "status": S_("Yalnız layihə və ya rəydəki versiya dərc olunur"), "unchecked": S_("Versiya son dəyişiklikdən sonra yoxlanmayıb və ya pozuntusu var"),
    "stale_parent": S_("Bu layihə hazırlandıqdan sonra başqa versiya dərc olunub: hesablamanı yenidən başladın"),
    "unconfirmed": S_("Dərcdən əvvəl təsdiqlənməli olan ayarlar hələ təsdiqlənməyib"), "readiness": S_("Hazırlıq siyahısında dərci dayandıran bənd var"),
    "effective_from": S_("Qüvvəyə minmə tarixi semestrin dərs dövründə və bildiriş müddətindən sonra olmalıdır"),
    "unplaced_count": S_("Yerləşdirilməyən dərslərin sayı düzgün yazılmayıb"),
    "review": S_("Rəy mərhələsi hələ yoxdur: dərc üçün səbəb yazın (ən azı 10 simvol)"),
    "teacher_clash": S_("Müəllim bu vaxtda başqa dərsdədir"), "group_clash": S_("Qrup bu vaxtda başqa dərsdədir"),
    "room_clash": S_("Otaq bu vaxtda tutulub"), "rooms_busy": S_("Uyğun otaqların hamısı tutulub"),
    "no_room": S_("Uyğun otaq yoxdur"), "capacity": S_("Otaq tutumu çatmır"), "room_fit": S_("Otaq bu dərs üçün uyğun deyil"),
    "teacher_unavailable": S_("Müəllim bu vaxtı məşğul kimi qeyd edib"), "room_unavailable": S_("Otaq bu vaxtda bağlıdır"),
    "shift": S_("Vaxt qrupun növbəsindən kənardır"), "fixed_slot": S_("Bu vaxt universitet üzrə tədbirə ayrılıb"),
    "block": S_("Bu həftələrdə qrup, müəllim və ya otaq dərsdən azaddır (təcrübə, məzuniyyət və s.)"), "travel": S_("Binalar arasında keçməyə vaxt çatmır"),
    "day_limit_group": S_("Qrupun günlük cüt həddi aşılır"), "day_limit_teacher": S_("Müəllimin günlük cüt həddi aşılır"),
    "week_hours": S_("Qrupun həftəlik auditoriya saatı həddi aşılır"), "week_pairs_teacher": S_("Müəllimin həftəlik cüt həddi aşılır"),
    "day": S_("Həftənin bu günü dərs günü deyil"), "duration": S_("Cütlər zəng cədvəlindən kənara çıxır"),
    "pattern_weeks": S_("Həftələr vahidin bölgüsünə uyğun deyil"), "past": S_("Keçmiş həftələr dəyişdirilə bilməz"),
    "locked": S_("Yerləşdirmə kilidlidir"), "unknown_meeting": S_("Dərs vahidin cari saatlarına uyğun deyil"),
    "duplicate": S_("Dərs iki dəfə yerləşdirilib"),
    # why the solver left a meeting unplaced (solver.explain), counted over the slots of the week
    "slot_rules": S_("Növbə, universitet tədbiri və ya müəllimin məşğul vaxtı imkan vermir"),
    "blocked_weeks": S_("Bütün həftələr təcrübə və ya başqa səbəblə dərsdən azaddır"),
    "teacher_busy": S_("Müəllim başqa dərsdədir"), "group_busy": S_("Qrup başqa dərsdədir"), "day_limit": S_("Günlük cüt həddi aşılır"),
    "locked_infeasible": S_("Kilidli yerləşdirmə qaydalara uyğun deyil"), "free": S_("Boş vaxt var, lakin axtarış onu tapmadı"),
    # what a precheck finds before any search (solver.precheck) and the units a run leaves out
    "no_groups": S_("Vahidin qrupu yoxdur: hesablamaya daxil edilmir"), "no_hours": S_("Vahidin saatı yoxdur: hesablamaya daxil edilmir"),
    "no_room_kind": S_("Bu növdə otaq yoxdur"),
    "room_reserved": S_("Tutumu çatan otaqlar başqa vahidlərə ayrılıb və ya vahidin otaq siyahısında deyil"),
    "no_room_capacity": S_("Otaq tutumu çatmır: {need} yer lazımdır, ən böyük uyğun otaqda {max} yer var"),
    "empty_time_domain": S_("Növbə, universitet tədbirləri və müəllimin məşğul vaxtları bu dərsə vaxt saxlamır"),
    "teacher_overload": S_("Müəllimin dərs yükü boş vaxtına sığmır: semestrdə {pair_weeks} cüt lazımdır, boş xanaların sayı: {available}"),
    "group_over_law": S_("Qrupun həftəlik auditoriya saatı qanuni həddi aşır: həftədə {hours} saat"),
    "room_supply": S_("{need} və daha çox yerlik otaqlar çatmır: həftədə {demand} cüt lazımdır, imkan {supply} cütdür"),
    "manual_rows": S_("Əl ilə yazılmış sətirləri olduğu üçün hesablamaya daxil edilməyən vahidlər"),
}


class Refused(Exception):
    """A refusal that carries more than its message (the readiness lines, the publish gate, a move's reasons); the route
    answers it as JSON with that status. Raised before any write of the request."""

    def __init__(self, status: int, message: dict, **extra):
        super().__init__(status)
        self.status, self.body = status, {"error": message, **extra}


def titled(items: list[dict], slot: bool = False) -> list[dict]:
    """Codes with their translated titles; ``slot``: a hard rule of a slot ("pattern" there is the unit's week sets)."""
    out = []
    for x in items:
        code = "pattern_weeks" if slot and x["code"] == "pattern" else x["code"]
        out.append({**x, "code": code, "title": T3(TITLES[code], **{k: v for k, v in x.items() if type(v) is int}) if code in TITLES else code})
    return out


def _unit_of(key) -> int | None:
    head = key.split(":")[0] if isinstance(key, str) else ""
    return int(head) if head.isdigit() else None


def named(c, items: list[dict], slot: bool = False) -> list[dict]:
    """Titled codes with the names the office reads: the courses of their meetings ("{unit}:{part}" keys) or units, the
    teacher and the group (a precheck line, a publication's problems)."""
    units = {u for x in items for u in [_unit_of(k) for k in x.get("keys") or [x.get("key")]] + [x.get("unit_id")] if u}
    courses = {u["id"]: u["course"] for u in repo.units_by_id(c, sorted(units))}
    teachers = repo.user_names(c, sorted({x["teacher_id"] for x in items if type(x.get("teacher_id")) is int}))
    groups = repo.groups_info(c, sorted({x["group_id"] for x in items if type(x.get("group_id")) is int}))
    out = []
    for x in titled(items, slot):
        us = [_unit_of(k) for k in x.get("keys") or [x.get("key")]] + [x.get("unit_id")]
        out.append({**x, "courses": sorted({courses[u] for u in us if u in courses}),
                    **({"teacher": teachers[x["teacher_id"]]} if x.get("teacher_id") in teachers else {}),
                    **({"group": groups[x["group_id"]]["name"]} if x.get("group_id") in groups else {})})
    return out


def _today() -> str:
    return now().date().isoformat()


def _z(v) -> bytes:
    return zlib.compress(json.dumps(v, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())


def _unz(b) -> dict | None:
    return json.loads(zlib.decompress(b)) if b else None


def settings(c) -> dict:
    return tenant.load(c)["timetable"]


def bell(c) -> tuple[list[list[str]], list[list[str]]]:
    """(stored bell times, the times the builder uses: the defaults of D3 while none are stored)."""
    stored = tenant.load(c)["calendar"]["lesson_times"]
    return stored, stored or domain.DEFAULT_TIMES


def term(c, tid: int) -> dict:
    t = directory.get(c, "terms", tid)
    if not t:
        raise HTTPError(404, "Semestr tapılmadı")
    return t


# ---------------------------------------------------------------- scope (design §7.1)
def scope_of(c, user) -> dict:
    """What the session's role covers: every unit (``all``), or units of these faculties, departments and courses.
    Administrator: all. Academic office: all as its primary role or with an unscoped grant, else its faculties. Dean's
    office: its faculties. Department head: its grants (unscoped: all), or its own department without one. Others: nothing."""
    role = user["role"]
    s: dict = {"all": role == "admin", "faculties": set(), "departments": set(), "courses": set()}
    if role not in ("academic_office", "office", "dept_head"):
        return s
    gs = repo.grants(c, user["id"], role)
    if (role != "office" and any(g["scope_type"] is None for g in gs)) or (role == "academic_office" and user.get("primary_role", role) == role):
        s["all"] = True
        return s
    for g in gs:
        key = {"faculty": "faculties", "department": "departments", "course": "courses"}.get(g["scope_type"] or "")
        if key and (role != "office" or key == "faculties"):
            s[key].add(g["scope_id"])
    if role == "dept_head" and not gs:
        me = repo.user_unit(c, user["id"])
        if me and me["department_id"]:
            s["departments"].add(me["department_id"])
    return s


def covers(s: dict, u: dict) -> bool:
    return s["all"] or u.get("department_id") in s["departments"] or u.get("faculty_id") in s["faculties"] or u.get("course_id") in s["courses"]


def _covers_department(c, s: dict, dep_id: int) -> bool:
    d = directory.get(c, "departments", dep_id)
    return bool(d) and (s["all"] or dep_id in s["departments"] or d["faculty_id"] in s["faculties"])


def _covers_scope(c, s: dict, sc: dict) -> bool:
    """A stored run or version scope the caller covers: a university-wide one only an unscoped holder, a list of
    departments one that covers each of them."""
    deps = [] if sc.get("all") else sc.get("departments") or []
    return s["all"] or (bool(deps) and all(_covers_department(c, s, d) for d in deps))


def _scope_from_run(scope: dict) -> dict:
    return {"all": bool(scope.get("all")), "faculties": set(), "departments": set(scope.get("departments") or []), "courses": set()}


def manages(user) -> bool:
    return perms.has(user["role"], "timetable.manage")


def unit_for(c, user, uid: int) -> dict:
    us = repo.units_by_id(c, [uid])
    if not us or not covers(scope_of(c, user), us[0]):
        raise HTTPError(404, "Tədris vahidi tapılmadı")
    return us[0]


def teacher_for(c, user, t: dict, tid: int, write: bool) -> dict:
    """A teacher whose grid the caller may read (write: change): their own, or one in the caller's scope (the teacher's
    department, or a unit they teach this term). The teacher's own write after the deadline needs a reopening."""
    who = repo.user_unit(c, tid)
    if not who or who["status"] != "active" or who["role"] not in ("teacher", "dept_head"):
        raise HTTPError(404, "Müəllim tapılmadı")
    if user["id"] == tid:
        if write:
            st = repo.availability_status_of(c, t["id"], tid) or {}
            if _today() > dues(c, t)["availability"] and (st.get("reopened_until") or "") < _today():
                raise HTTPError(409, "Məşğulluq vaxtlarının son tarixi keçib: kafedra müdirinə müraciət edin")
        return who
    s = scope_of(c, user)
    if user["role"] == "teacher" or not (s["all"] or who["department_id"] in s["departments"] or who["faculty_id"] in s["faculties"]
                                         or any(covers(s, u) for u in repo.units_by_id(c, repo.teacher_term_units(c, t["id"], tid)))):
        raise HTTPError(404, "Müəllim tapılmadı")
    return who


def group_for(c, user, t: dict, gid: int, write: bool) -> dict:
    """A group of the caller's faculties (a head reads the groups its units teach and never writes them)."""
    g = repo.groups_info(c, [gid]).get(gid)
    s = scope_of(c, user)
    if not g:
        raise HTTPError(404, "Qrup tapılmadı")
    seen = s["all"] or g["faculty_id"] in s["faculties"] or any(covers(s, u) for u in repo.units_by_id(c, repo.group_term_units(c, t["id"], [gid])))
    if not seen:
        raise HTTPError(404, "Qrup tapılmadı")
    if write and (user["role"] == "dept_head" or not (s["all"] or g["faculty_id"] in s["faculties"])):
        raise HTTPError(403, "Qrupların növbəsini dekanlıq müəyyən edir")
    return g


def _visible(c, user, v: dict, s: dict | None = None) -> bool:
    """One in review, published or superseded: to every holder (a scoped one reads its own units of it). A draft: to a
    timetable.manage holder whose scope covers the draft's (Checkpoint F, SEC-TT-3)."""
    return v["status"] in VISIBLE_PREPARE or (manages(user) and _covers_scope(c, s or scope_of(c, user), J(v["scope"], {"all": True}) or {}))


def version_for(c, user, vid: int) -> dict:
    v = repo.version(c, vid)
    if not v or not _visible(c, user, v):
        raise HTTPError(404, "Cədvəl versiyası tapılmadı")
    return v


# ---------------------------------------------------------------- deadlines and readiness (design §7.2)
def dues(c, t: dict) -> dict:
    st, tt = settings(c), repo.tt_term(c, t["id"]) or {}
    start = date.fromisoformat(t["teaching_start"])
    out = {k: tt.get(f"{k}_due") or (start + timedelta(days=st["offsets"][k])).isoformat() for k in ("needs", "groups", "availability", "review")}
    out["publish"] = tt.get("publish_target") or (start + timedelta(days=st["offsets"]["publish"])).isoformat()
    return out


def _facts(c, t: dict, s: dict, department_id: int | None = None) -> dict:
    st = settings(c)
    units = [u for u in repo.term_units(c, t["id"]) if covers(s, u) and (department_id is None or u["department_id"] == department_id)]
    ug = repo.term_unit_groups(c, t["id"])
    groups = sorted({g for u in units for g in ug.get(u["id"], [])})
    gt, rooms, needs = repo.group_terms(c, t["id"]), repo.rooms(c), repo.term_needs(c, t["id"])
    sizes, status = repo.registry_sizes(c, groups), repo.availability_status(c, t["id"])
    teachers = sorted({u["teacher_id"] for u in units if u["teacher_id"]})
    mine = {u["id"] for u in units}
    manual = sorted({r["unit_id"] for r in repo.term_rows(c, t["id"]) if r["unit_id"] in mine and not r["meeting_key"]})
    over = []
    for u in units:
        nd = needs.get(u["id"]) or {}
        if nd.get("mode") == "online":
            continue
        kinds = J(nd.get("room_kinds")) or domain.UNIT_ROOM_KINDS.get(u["kind"], [])
        need = nd.get("need") or u["students"] or sum(sizes.get(g, 0) for g in ug.get(u["id"], [])) or st["default_need"]
        if need > max((r["capacity"] or 0 for r in rooms if r["kind"] in kinds and r["schedulable"]), default=0):
            over.append(u["id"])
    return {"term": t, "weeks": domain.term_weeks(t), "lesson_times": bell(c)[0], "rooms": rooms, "groups": groups,
            "groups_no_shift": [g for g in groups if not (gt.get(g) or {}).get("shift")], "units": [u["id"] for u in units],
            "units_no_groups": [u["id"] for u in units if not ug.get(u["id"])], "units_no_teacher": [u["id"] for u in units if not u["teacher_id"]],
            "units_over_room": over, "teachers": teachers, "units_manual": manual,
            "teachers_unconfirmed": [x for x in teachers if not (status.get(x) or {}).get("confirmed_at")],
            "pending": [x for x in teachers if (status.get(x) or {}).get("pending")], "availability_due": dues(c, t)["availability"]}


def readiness(c, user, tid: int, department_id: int | None = None) -> dict:
    t, s = term(c, tid), scope_of(c, user)
    if department_id is not None and not _covers_department(c, s, department_id):
        raise HTTPError(404, "Kafedra tapılmadı")
    lines = domain.readiness(_facts(c, t, s, department_id), settings(c), _today())
    return {"term_id": t["id"], "lines": _labelled(c, titled(lines)), "run_blocked": bool(domain.gate(lines, "run")),
            "publish_blocked": bool(domain.gate(lines, "publish")), "dues": dues(c, t)}


SAMPLE_KIND = {"group_shifts": "group", "availability": "teacher", "availability_late": "teacher", "availability_pending": "teacher",
               "rooms": "unit", "unit_groups": "unit", "vacancies": "unit", "manual_rows": "unit"}


def _labelled(c, lines: list[dict]) -> list[dict]:
    """The samples of readiness lines with the names the pages show (a group's name, a teacher's, a unit's course and kind)."""
    want: dict[str, set] = {"group": set(), "teacher": set(), "unit": set()}
    for x in lines:
        if x["code"] in SAMPLE_KIND:
            want[SAMPLE_KIND[x["code"]]].update(v for v in x["samples"] if type(v) is int)
    names = {"group": {g: v["name"] for g, v in repo.groups_info(c, sorted(want["group"])).items()},
             "teacher": repo.user_names(c, sorted(want["teacher"])),
             "unit": {u["id"]: f"{u['course']} · {domain.KIND_LABEL.get(u['kind'], u['kind'])}" for u in repo.units_by_id(c, sorted(want["unit"]))}}
    return [{**x, "labels": [names[SAMPLE_KIND[x["code"]]].get(v, f"#{v}") for v in x["samples"]]} if x["code"] in SAMPLE_KIND else x
            for x in lines]


def start_page(c, user, tid: int) -> dict:
    t = term(c, tid)
    r = readiness(c, user, tid)
    pub = repo.published_version(c, tid)
    s = scope_of(c, user)
    vs = [v for v in repo.versions(c, tid) if _visible(c, user, v, s)]
    run = repo.active_run(c, tid) if manages(user) else None
    return {"term": {k: t[k] for k in ("id", "code", "name", "teaching_start", "teaching_end")}, "weeks": domain.term_weeks(t),
            "manages": manages(user), "can_publish": perms.has(user["role"], "timetable.publish") and scope_of(c, user)["all"],
            "notice_days": settings(c)["notice_days"], "term_confirmed": J((repo.tt_term(c, tid) or {}).get("confirmed"), []) or [],
            "dues": r["dues"], "run_blocked": r["run_blocked"], "publish_blocked": r["publish_blocked"],
            "warnings": sum(1 for x in r["lines"] if x["level"] == "warn"), "versions": len(vs), "published_id": pub["id"] if pub else None,
            "run": run_out(run) if run else None}


def _date(v, field: str) -> str | None:
    if v is None or v == "":
        return None
    try:
        return date.fromisoformat(v).isoformat() if isinstance(v, str) else _bad_date(field)
    except ValueError:
        return _bad_date(field)


def _bad_date(field: str):
    raise HTTPError(400, E("«{field}» sahəsində tarix İİİİ-AA-GG formatında olmalıdır", field=field))


def _university_wide(c, user) -> None:
    """The term's plan and the timetable rules hold for every faculty: only an unscoped holder changes them (SEC-TT-1)."""
    if not scope_of(c, user)["all"]:
        raise HTTPError(403, "Semestrin planını və cədvəl qaydalarını yalnız bütün universitet üzrə səlahiyyəti olan tədris hissəsi dəyişir")


def save_plan(c, user, tid: int, body) -> dict:
    """The term's deadlines (empty: the default offset) and its own confirmations (practice, reserved weeks, fixed slots, online)."""
    _university_wide(c, user)
    t = term(c, tid)
    v: dict = {k: _date(body.get(k), k) for k in ("needs_due", "groups_due", "availability_due", "review_due", "publish_target")}
    conf = body.array("confirmed")
    if not all(isinstance(x, str) and x in domain.TERM_KEYS for x in conf) or len(set(conf)) != len(conf):
        raise HTTPError(400, "Təsdiq siyahısında naməlum bənd var")
    v["confirmed"] = sorted(conf)
    repo.set_tt_term(c, t["id"], v, user["id"], iso(now()))
    audit(c, user["id"], "tt_plan", "term", f"{t['code']} · " + ", ".join(f"{k}: {x}" for k, x in v.items() if x))
    return {**v, "dues": dues(c, t)}


# ---------------------------------------------------------------- settings
def get_settings(c) -> dict:
    stored, _ = bell(c)
    return {"timetable": settings(c), "lesson_times": stored, "defaults": domain.DEFAULT_TIMES}


def put_settings(c, user, value) -> dict:
    from ..tenant import service as tenant_settings          # here: the tenant module imports the identity layer
    _university_wide(c, user)
    problem = tenant_settings.problem("timetable", value)
    if problem:
        raise HTTPError(400, problem)
    before = set(settings(c)["confirmed"])
    tenant_settings.save(c, user, "timetable", value)
    now_conf = set(value.get("confirmed") or [])
    audit(c, user["id"], "tt_settings", "settings", "timetable · confirmed: +" + ",".join(sorted(now_conf - before)) + " −" + ",".join(sorted(before - now_conf)))
    return get_settings(c)


# ---------------------------------------------------------------- unit needs and group shifts
def _needs_out(n: dict | None) -> dict | None:
    if not n:
        return None
    return {**{k: n[k] for k in ("need", "need_reason", "duration", "mode", "split")},
            **{k: J(n[k]) for k in ("room_kinds", "room_ids", "pattern")}}


def units(c, user, tid: int, department_id: int | None, offset: int) -> dict:
    t, s = term(c, tid), scope_of(c, user)
    if department_id is not None and not _covers_department(c, s, department_id):
        raise HTTPError(404, "Kafedra tapılmadı")
    us = [u for u in repo.term_units(c, t["id"]) if covers(s, u) and (department_id is None or u["department_id"] == department_id)]
    page = us[offset:offset + 100]
    groups, needs = repo.groups_of_units(c, [u["id"] for u in page]), repo.needs_of(c, [u["id"] for u in page])
    return {"total": len(us), "offset": offset,
            "items": [{**{k: u[k] for k in ("id", "course_id", "course", "kind", "teacher_id", "subgroup", "hours", "students", "department_id")},
                       "groups": groups.get(u["id"], []), "needs": _needs_out(needs.get(u["id"]))} for u in page]}


def teachers(c, user, tid: int, department_id: int | None) -> dict:
    """The teachers' board: everyone teaching a unit of the term in the caller's scope, with their grid's state."""
    t, s = term(c, tid), scope_of(c, user)
    if department_id is not None and not _covers_department(c, s, department_id):
        raise HTTPError(404, "Kafedra tapılmadı")
    us = [u for u in repo.term_units(c, t["id"]) if u["teacher_id"] and covers(s, u) and (department_id is None or u["department_id"] == department_id)]
    ids = sorted({u["teacher_id"] for u in us})
    names, status, due = repo.user_names(c, ids), repo.availability_status(c, t["id"]), dues(c, t)["availability"]
    more = repo.user_details(c, ids)
    cells: dict[int, int] = {}
    for a in repo.subjects_availability(c, t["id"], "teacher", ids):
        cells[a["subject_id"]] = cells.get(a["subject_id"], 0) + 1
    out = []
    for x in ids:
        st = status.get(x) or {}
        out.append({"id": x, "full_name": names.get(x, ""), "patronymic": (more.get(x) or {}).get("patronymic"),
                    "department": (more.get(x) or {}).get("department"), "units": sum(1 for u in us if u["teacher_id"] == x), "cells": cells.get(x, 0),
                    "confirmed_at": st.get("confirmed_at"), "pending": bool(st.get("pending")), "pending_at": st.get("pending_at"),
                    "reopened_until": st.get("reopened_until"), "over_cap_cells": st.get("over_cap_cells"),
                    "late": not st.get("confirmed_at") and _today() > due})
    return {"due": due, "items": sorted(out, key=lambda x: (x["full_name"], x["id"]))}


def put_needs(c, user, uid: int, body) -> dict:
    u = unit_for(c, user, uid)
    if not u["term_id"]:
        raise HTTPError(409, "Vahidin fənni heç bir semestrə bağlanmayıb")
    t = term(c, u["term_id"])
    if _today() > dues(c, t)["needs"] and not manages(user):
        raise HTTPError(409, "Tələblərin son tarixi keçib: dəyişikliyi indi yalnız tədris hissəsi edə bilər")
    v, problem = domain.needs_input(dict(body), u, settings(c), domain.term_weeks(t), {r["id"] for r in repo.rooms(c)})
    if problem:
        raise HTTPError(400, problem)
    repo.set_needs(c, uid, v, user["id"], iso(now()))
    audit(c, user["id"], "tt_needs", "teaching_unit", f"{uid} · " + ", ".join(f"{k}: {x}" for k, x in v.items() if x not in (None, 1, "in_person")))
    return {"unit_id": uid, "needs": v}


def groups(c, user, tid: int) -> list[dict]:
    t, s = term(c, tid), scope_of(c, user)
    ug = repo.term_unit_groups(c, t["id"])
    ids = sorted({g for u in repo.term_units(c, t["id"]) if covers(s, u) for g in ug.get(u["id"], [])})
    info, gt = repo.groups_info(c, ids), repo.group_terms(c, t["id"])
    return sorted(({"id": g, "name": info[g]["name"], "faculty_id": info[g]["faculty_id"], "shift": (gt.get(g) or {}).get("shift"),
                    "home_building_id": (gt.get(g) or {}).get("home_building_id")} for g in ids if g in info), key=lambda x: (x["name"] or "", x["id"]))


def put_groups(c, user, tid: int, body) -> dict:
    t = term(c, tid)
    items = body.array("items")
    shifts, buildings = settings(c)["shifts"], repo.building_ids(c)
    if len(items) > 500:
        raise HTTPError(400, "Bir dəfəyə ən çox 500 qrup saxlamaq mümkündür")
    clean = []
    for x in items:
        gid = x.get("group_id") if isinstance(x, dict) else None
        shift, bld = (x.get("shift"), x.get("home_building_id")) if isinstance(x, dict) else (None, None)
        if (type(gid) is not int or (shift is not None and (not isinstance(shift, str) or shift not in shifts))
                or (bld is not None and (type(bld) is not int or bld not in buildings))):
            raise HTTPError(400, "Qrupun növbəsi və ya binası düzgün deyil")
        group_for(c, user, t, gid, write=True)
        clean.append((gid, shift, bld))
    stamp = iso(now())
    for gid, shift, bld in clean:
        repo.set_group_term(c, t["id"], gid, shift, bld, user["id"], stamp)
    audit(c, user["id"], "tt_groups", "term", f"{t['code']} · {len(clean)}")
    return {"saved": len(clean)}


# ---------------------------------------------------------------- availability (C9)
def _grid_size(c) -> tuple[list[int], int]:
    return settings(c)["days"], len(bell(c)[1])


def _feedback(c, t: dict, tid: int, cells: list[dict]) -> dict:
    days, periods = _grid_size(c)
    us = repo.units_by_id(c, repo.teacher_term_units(c, t["id"], tid))
    return domain.availability_feedback(cells, domain.weekly_pairs(us, settings(c), domain.term_weeks(t)), settings(c), len(days), periods)


def availability(c, user, tid: int, uid: int) -> dict:
    t = term(c, tid)
    who = teacher_for(c, user, t, uid, write=False)
    cells = repo.subject_availability(c, t["id"], "teacher", uid)
    st = repo.availability_status_of(c, t["id"], uid) or {}
    days, periods = _grid_size(c)
    return {"teacher": {"id": who["id"], "full_name": who["full_name"]}, "cells": cells, "feedback": _feedback(c, t, uid, cells),
            "status": {"confirmed_at": st.get("confirmed_at"), "pending": J(st.get("pending")), "pending_at": st.get("pending_at"),
                       "reopened_until": st.get("reopened_until"), "over_cap_cells": st.get("over_cap_cells"), "decided_at": st.get("decided_at")},
            "due": dues(c, t)["availability"], "days": days, "periods": periods, "times": bell(c)[1][:periods],
            "cap_pct": settings(c)["availability_cap_pct"], "load_pct": settings(c)["availability_load_factor_pct"],
            "editable": _today() <= dues(c, t)["availability"] or (st.get("reopened_until") or "") >= _today() or user["id"] != uid}


def put_availability(c, user, tid: int, uid: int, body) -> dict:
    """The whole grid. The teacher's own grid above the cap is not written: it waits for the head (C9)."""
    t = term(c, tid)
    who = teacher_for(c, user, t, uid, write=True)
    days, periods = _grid_size(c)
    cells, problem = domain.availability_input(body.get("cells"), days, periods, domain.term_weeks(t))
    if problem:
        raise HTTPError(400, problem)
    fb, stamp = _feedback(c, t, uid, cells), iso(now())
    if user["id"] == uid and fb["over_cap"]:
        repo.set_availability_status(c, t["id"], uid, pending=json.dumps(cells, ensure_ascii=False), pending_at=stamp, decided_at=None, decided_by=None)
        heads = [h for h in repo.heads_of(c, who["department_id"], who["faculty_id"]) if h != uid]
        if heads:
            notify(c, heads, "timetable", T3("Müəllimin məşğulluq cədvəli təsdiqinizi gözləyir: {name}", name=who["full_name"]), "", "/dept/timetable")
        audit(c, user["id"], "tt_availability_pending", "user", f"{uid} · {len(cells)} xana · +{fb['over_cap']}")
        return {"status": "pending", "feedback": fb}
    repo.replace_availability(c, t["id"], "teacher", uid, cells, user["id"], stamp)
    repo.set_availability_status(c, t["id"], uid, pending=None, pending_at=None,
                                 over_cap_cells=fb["over_cap"] if user["id"] != uid and fb["over_cap"] else None)
    audit(c, user["id"], "tt_availability", "user", f"{uid} · {len(cells)} xana")      # never the notes (§7.3)
    return {"status": "saved", "feedback": fb}


def confirm_availability(c, user, tid: int, uid: int) -> dict:
    t = term(c, tid)
    teacher_for(c, user, t, uid, write=True)
    stamp = iso(now())
    repo.set_availability_status(c, t["id"], uid, confirmed_at=stamp, confirmed_by=user["id"])
    audit(c, user["id"], "tt_availability_confirm", "user", str(uid))
    return {"confirmed_at": stamp}


def decide_availability(c, user, tid: int, uid: int, approve: bool) -> dict:
    t = term(c, tid)
    if user["id"] == uid:
        raise HTTPError(403, "Öz məşğulluq cədvəlinizi özünüz təsdiq edə bilməzsiniz")
    teacher_for(c, user, t, uid, write=True)
    st = repo.availability_status_of(c, t["id"], uid) or {}
    if not st.get("pending"):
        raise HTTPError(409, "Təsdiq gözləyən məşğulluq cədvəli yoxdur")
    stamp, over = iso(now()), None
    if approve:
        days, periods = _grid_size(c)
        cells, problem = domain.availability_input(J(st["pending"], []), days, periods, domain.term_weeks(t))
        if problem:                                   # the settings changed since: the teacher enters the grid again
            raise HTTPError(409, "Gözləyən cədvəl cari ayarlara uyğun deyil: müəllim onu yenidən daxil etməlidir")
        repo.replace_availability(c, t["id"], "teacher", uid, cells, user["id"], stamp)
        over = _feedback(c, t, uid, cells)["over_cap"] or None
    repo.set_availability_status(c, t["id"], uid, pending=None, pending_at=None, over_cap_cells=over, decided_by=user["id"], decided_at=stamp)
    notify(c, [uid], "timetable", T3("Məşğulluq cədvəliniz təsdiqləndi") if approve else T3("Məşğulluq cədvəliniz qəbul edilmədi"), "",
           "/teacher/availability")
    audit(c, user["id"], "tt_availability_decide", "user", f"{uid} · {'approved' if approve else 'refused'}")
    return {"approved": approve, "over_cap_cells": over}


def reopen_availability(c, user, tid: int, uid: int, until) -> dict:
    t = term(c, tid)
    if user["id"] == uid:
        raise HTTPError(403, "Öz məşğulluq cədvəlinizin müddətini özünüz uzada bilməzsiniz")
    teacher_for(c, user, t, uid, write=True)
    day = _date(until, "until")
    if not day or not _today() <= day <= t["teaching_end"]:
        raise HTTPError(400, "Yeni son tarix bu gündən semestrin sonunadək olmalıdır")
    repo.set_availability_status(c, t["id"], uid, reopened_until=day)
    notify(c, [uid], "timetable", T3("Məşğulluq vaxtlarınızı {date} tarixinədək dəyişə bilərsiniz", date=day), "", "/teacher/availability")
    audit(c, user["id"], "tt_availability_reopen", "user", f"{uid} · {day}")
    return {"reopened_until": day}


# ---------------------------------------------------------------- the snapshot a run solves (one read transaction, C3)
def _obstacle(r: dict, ug: dict[int, list[int]], times: list[list[str]]) -> dict | None:
    span = domain.pairs_of(times, r["start"], r["end"])
    if not span:
        return None
    return {"key": f"row:{r['id']}", "weekday": r["weekday"], "period": span[0], "duration": span[1], "weeks": r["weeks"] or "all",
            "teacher_id": r["teacher_id"], "groups": [[g, r["subgroup"]] for g in ug.get(r["unit_id"], [])] if r["unit_id"] else [],
            "room_id": r["room_id"]}


def _problem(c, t: dict, units_: list[dict], ug: dict, obstacles: list[dict], reference: list[dict], locked: list[dict]) -> dict:
    st, (_, times) = settings(c), bell(c)
    ids = [u["id"] for u in units_]
    gids = sorted({g for u in units_ for g in ug.get(u["id"], [])} | {g for o in obstacles for g, _ in o["groups"]})
    gt, sizes = repo.group_terms(c, t["id"]), repo.registry_sizes(c, gids)
    teachers = sorted({u["teacher_id"] for u in units_ if u["teacher_id"]})
    needs = repo.needs_of(c, ids)
    rooms = repo.rooms(c)
    avail = [a for a in repo.subjects_availability(c, t["id"], "teacher", teachers) + repo.subjects_availability(c, t["id"], "room", [r["id"] for r in rooms])
             if a["level"] in ("unavailable", "undesired")]
    return {"weeks": domain.term_weeks(t), "lesson_times": times, "settings": st,
            "rooms": [{k: r[k] for k in ("id", "kind", "capacity", "building_id", "schedulable", "dedicated")} for r in rooms],
            "groups": [{"id": g, "shift": (gt.get(g) or {}).get("shift"), "home_building_id": (gt.get(g) or {}).get("home_building_id"),
                        "size": sizes.get(g, 0)} for g in gids],
            "units": [{"id": u["id"], "course_id": u["course_id"], "kind": u["kind"], "teacher_id": u["teacher_id"], "subgroup": u["subgroup"],
                       "groups": ug.get(u["id"], []), "hours": u["hours"], "students": u["students"]} for u in units_],
            "needs": [{"unit_id": k, **(_needs_out(n) or {})} for k, n in sorted(needs.items())],
            "availability": sorted(avail, key=lambda a: (a["subject_type"], a["subject_id"], a["weekday"], a["period"])),
            "blocks": repo.term_blocks(c, t["id"]), "obstacles": obstacles, "reference": reference, "locked": locked}


def snapshot(c, t: dict, scope: dict, base_version_id: int | None = None) -> tuple[dict, list[int]]:
    """The problem of a run over the units in ``scope`` and the units kept out of it because they have hand-written rows
    (adopting those rows as a version comes later, so their rows stay obstacles and the run never doubles them). Rows of
    other units are obstacles; the published rows of the scope's units are the stability reference."""
    _, times = bell(c)
    s = _scope_from_run(scope)
    all_units, ug, trows = repo.term_units(c, t["id"]), repo.term_unit_groups(c, t["id"]), repo.term_rows(c, t["id"])
    manual = {r["unit_id"] for r in trows if r["unit_id"] and not r["meeting_key"]}
    mine = [u for u in all_units if covers(s, u) and u["id"] not in manual]
    kept = sorted(u["id"] for u in all_units if covers(s, u) and u["id"] in manual)
    ids = {u["id"] for u in mine}
    obstacles = [o for o in (_obstacle(r, ug, times) for r in trows if r["unit_id"] not in ids) if o]
    reference = [{"key": r["meeting_key"], "weekday": r["weekday"], "period": r["period"], "weeks": r["weeks"], "room_id": r["room_id"]}
                 for r in trows if r["unit_id"] in ids and r["meeting_key"] and r["period"]]
    locked = [{"key": p["meeting_key"], "weekday": p["weekday"], "period": p["period"], "weeks": p["weeks"], "room_id": p["room_id"]}
              for p in repo.placements(c, base_version_id) if p["locked"]] if base_version_id else []
    return _problem(c, t, mine, ug, obstacles, reference, locked), kept


def _as_meeting(p: dict) -> dict:
    return {"key": p["meeting_key"], "unit_id": p["unit_id"], "weekday": p["weekday"], "period": p["period"], "duration": p["duration"],
            "weeks": p["weeks"], "room_id": p["room_id"]}


# ---------------------------------------------------------------- runs (design §8)
def run_out(r: dict) -> dict:
    return {**{k: r[k] for k in ("id", "term_id", "kind", "base_version_id", "version_id", "effective_from", "status", "cancel", "seed",
                                 "iter_budget", "time_budget_s", "iterations", "cpu_ms", "stopped", "error", "requested_by", "requested_at",
                                 "started_at", "finished_at")},
            "scope": J(r["scope"], {}), "params": J(r["params"], {}), "progress": J(r["progress"], {}),
            "error": J(r["error"], r["error"])}         # older rows hold a plain text


def start_run(c, user, tid: int, body) -> dict:
    t, s = term(c, tid), scope_of(c, user)
    kind = body.get("kind")
    if kind not in RUN_KINDS:
        raise HTTPError(400, "Hesablamanın növü düzgün deyil")
    deps = body.ids("departments", 500) if body.get("departments") is not None else None
    if deps is None and not s["all"]:
        raise HTTPError(400, "Hesablamaya daxil olan kafedraları seçin")
    for d in deps or []:
        if not _covers_department(c, s, d):
            raise HTTPError(404, "Kafedra tapılmadı")
    scope = {"all": True} if deps is None else {"departments": sorted(set(deps))}
    vid = base = None
    if kind == "check":
        v = version_for(c, user, body.integer("version_id", 0))
        if not _covers_scope(c, s, J(v["scope"], {"all": True}) or {}):      # the run takes the version's scope (SEC-TT-2)
            raise HTTPError(404, "Cədvəl versiyası tapılmadı")
        if v["term_id"] != t["id"] or v["status"] not in EDITABLE:
            raise HTTPError(409, "Yalnız bu semestrin layihəsi və ya rəydəki versiyası yoxlanılır")
        vid, scope = v["id"], J(v["scope"], {"all": True})
    elif body.get("base_version_id") is not None:
        b = version_for(c, user, body.integer("base_version_id", 0))
        if b["term_id"] != t["id"] or not _covers_scope(c, s, J(b["scope"], {"all": True}) or {}):
            raise HTTPError(404, "Cədvəl versiyası tapılmadı")
        base = b["id"]
    if kind != "check":
        lines = domain.gate(domain.readiness(_facts(c, t, _scope_from_run(scope)), settings(c), _today()), "run")
        if lines:
            raise Refused(409, E("Hazırlıq siyahısında hesablamanı dayandıran bənd var"), lines=titled(lines))
    sol = settings(c)["solver"]
    hi = tenant.SOLVER_LIMITS["iter_budget"][1]
    stamp = iso(now())
    try:
        rid = repo.insert_run(c, {"term_id": t["id"], "kind": kind, "scope": json.dumps(scope), "base_version_id": base, "version_id": vid,
                                  "params": json.dumps({"name": body.text("name", 100) or None}, ensure_ascii=False), "status": "queued",
                                  "seed": body.integer("seed", 1, lo=0, hi=2 ** 31 - 1), "time_budget_s": sol["time_budget_s"],
                                  "iter_budget": body.integer("budget", sol["iter_budget"], lo=1, hi=hi),
                                  "requested_by": user["id"], "requested_at": stamp})
    except sqlite3.IntegrityError:
        raise HTTPError(409, "Bu semestr üçün başqa hesablama gedir") from None
    audit(c, user["id"], "tt_run", "term", f"{t['code']} · #{rid} {kind}")
    return run_out(repo.run(c, rid))


def _run_for(c, user, rid: int, blobs: bool = False) -> dict:
    """A run the caller's scope covers: a university-wide run only to an unscoped holder, a run of departments to one that
    covers each of them (an id outside the scope answers 404, design §7.1)."""
    r = repo.run(c, rid, blobs=blobs)
    s = scope_of(c, user)
    if not r or not _covers_scope(c, s, J(r["scope"], {}) or {}):
        raise HTTPError(404, "Hesablama tapılmadı")
    return r


def get_run(c, user, rid: int) -> dict:
    r = _run_for(c, user, rid, blobs=True)
    rep = {k: (v[:200] if isinstance(v, list) else v) for k, v in (_unz(r["report"]) or {}).items()}
    for k in ("precheck", "excluded"):
        if rep.get(k):
            rep[k] = named(c, rep[k])
    return {**run_out(r), "report": rep}


def cancel_run(c, user, rid: int) -> dict:
    r = _run_for(c, user, rid)
    if r["status"] not in ("queued", "running") or r["kind"] == "publish":
        raise HTTPError(409, "Bu hesablama dayandırıla bilməz")
    repo.update_run(c, rid, cancel=1)
    audit(c, user["id"], "tt_run_cancel", "term", f"#{rid}")
    return run_out(repo.run(c, rid))


def _tx(c, fn):
    """One short write transaction; its length goes to the run's progress (tx_ms_max, design §8.1)."""
    t0 = time.monotonic()
    c.execute("BEGIN IMMEDIATE")
    try:
        out = fn()
        c.commit()
    except BaseException:
        c.rollback()
        raise
    return out, round((time.monotonic() - t0) * 1000)


def _err(message: dict) -> str:
    """A run's error as stored: the message in every language (run_out reads it back; ``localize`` picks one)."""
    return json.dumps(message, ensure_ascii=False)


def _progress(r: dict, **v) -> str:
    return json.dumps({**(J(r["progress"], {}) or {}), **v})


def work(c) -> str:
    """The job ``timetable.work``: one chunk of the oldest active run (design §8)."""
    c.commit()
    r = repo.next_run(c)
    if not r:
        return "idle"
    if r["cancel"] and r["kind"] != "publish":
        _tx(c, lambda: repo.update_run(c, r["id"], status="cancelled", state=None, finished_at=iso(now())))
        CACHE.pop(r["id"], None)
        return f"run {r['id']}: cancelled"
    from ..exam import service as exam                          # here: the exam module imports the legacy layer
    sol = settings(c)["solver"]
    busy = exam.open_count(c) > 0
    budget = sol["chunk_exam_s"] if busy else sol["chunk_s"]
    try:
        if r["kind"] == "publish":
            out = publish_step(c, r, budget)
        elif r["kind"] == "check":
            out = _check_run(c, r, busy, sol)
        else:
            out = _solve_step(c, r, budget, busy, sol)
        if r["fails"]:                                         # three failures in a row fail a run, not three in its life
            _tx(c, lambda: repo.update_run(c, r["id"], fails=0, error=None))
        return out
    except Exception as ex:                                    # noqa: BLE001  a failing run is recorded on the run itself
        c.rollback()
        fails, detail = r["fails"] + 1, f"{type(ex).__name__}: {ex}"[:500]
        # a publication past its check may have written rows already: it never gives up half applied, it retries from its
        # stored step and cursor and keeps the term locked (design §8.2)
        r = repo.run(c, r["id"]) or r                         # its steps may have moved on within this call
        holding = r["kind"] == "publish" and (J(r["progress"], {}) or {}).get("step", "check") != "check"
        failed = fails >= 3 and not holding
        error = _err(T3("Dərcin bu mərhələsi uğursuz oldu: dövri iş onu avtomatik təkrarlayır, bu müddətdə semestrin cədvəli kilidli qalır") if holding
                     else T3("Hesablama sistem xətası səbəbindən dayandı: onu yenidən başladın, xəta təkrarlanarsa, administratora bildirin"))
        _tx(c, lambda: repo.update_run(c, r["id"], fails=fails, error=error, progress=_progress(r, detail=detail),
                                       **({"status": "failed", "finished_at": iso(now()), "state": None} if failed else {})))
        if failed:
            CACHE.pop(r["id"], None)
            _tx(c, lambda: notify(c, [r["requested_by"]], "timetable", T3("Cədvəlin hesablanması uğursuz oldu"), "", "/admin/timetable/build"))
        elif holding and fails == 3:
            _tx(c, lambda: notify(c, [r["requested_by"]], "timetable", T3("Cədvəlin dərci yarımçıq qalıb: dövri iş onu təkrarlayır"), "",
                                  "/admin/timetable/build"))
        return f"run {r['id']}: error {fails}"


def _waits(busy: bool, r: dict, sol: dict) -> bool:
    """While an exam is open, an atomic step estimated above atomic_exam_max_s waits (meetings x 1 ms, §8.1)."""
    est = ((J(r["progress"], {}) or {}).get("meetings") or 0) / 1000
    return busy and est > sol["atomic_exam_max_s"]


def _solve_step(c, r: dict, budget: float, busy: bool, sol: dict) -> str:
    t = term(c, r["term_id"])
    if r["input"] is None:
        if _waits(busy, r, sol):
            return f"run {r['id']}: waiting, an exam is open"
        c.execute("BEGIN")                                     # one deferred read transaction: every read sees one state
        try:
            problem, kept = snapshot(c, t, J(r["scope"], {"all": True}), r["base_version_id"])
        finally:
            c.rollback()
        blob = _z(problem)
        sha = hashlib.sha256(blob).hexdigest()
        model = solver.prepare(problem)
        report = {"precheck": solver.precheck(model), "excluded": model.excluded, "kept_manual": kept}
        done = r["kind"] == "precheck"
        _, ms = _tx(c, lambda: repo.update_run(c, r["id"], input=blob, input_sha256=sha, report=_z(report), started_at=iso(now()),
                                               status="done" if done else "running", finished_at=iso(now()) if done else None,
                                               progress=_progress(r, phase="done" if done else "snapshot", meetings=model.N, units=len(problem["units"]),
                                                                  kept_manual=len(kept), tx_ms_max=0)))
        if not done:
            CACHE.clear()
            CACHE[r["id"]] = (sha, model)
        return f"run {r['id']}: snapshot, {model.N} meetings"
    cached = CACHE.get(r["id"])
    if cached and cached[0] == r["input_sha256"]:
        model = cached[1]
    else:
        if _waits(busy, r, sol):
            return f"run {r['id']}: waiting, an exam is open"
        model = solver.prepare(_unz(r["input"]) or {})
        CACHE.clear()
        CACHE[r["id"]] = (r["input_sha256"], model)
    t0 = time.monotonic()
    state = solver.run(model, _unz(r["state"]), seed=r["seed"], budget=r["iter_budget"], deadline=t0 + budget, now=time.monotonic)
    cpu = r["cpu_ms"] + round((time.monotonic() - t0) * 1000)
    if state["phase"] != "done" and cpu < r["time_budget_s"] * 1000:
        prog = _progress(r, phase=state["phase"], iterations=state["it"], unplaced=len(state["unplaced"]), score=state.get("score"))
        _tx(c, lambda: repo.update_run(c, r["id"], state=_z(state), iterations=state["it"], cpu_ms=cpu, heartbeat_at=iso(now()), progress=prog))
        return f"run {r['id']}: {state['phase']} {state['it']}"
    if state["phase"] != "done":
        state = {**state, "stopped": "deadline"}
    return _write_version(c, r, t, model, state, cpu)


def _write_version(c, r: dict, t: dict, model: solver.Model, state: dict, cpu: int) -> str:
    out = solver.result(model, state)
    problem = model.problem
    hard = domain.check(problem, out["placements"])
    card = domain.scorecard(problem, out["placements"])
    seen = {m["unit_id"] for m in model.meetings} | {e["unit_id"] for e in model.excluded}
    lost = {u["id"] for u in problem["units"]} ^ seen
    if lost:                                                       # nothing silent: each unit is placed, unplaced or excluded
        raise LookupError(f"units neither placed, unplaced nor excluded: {sorted(lost)[:20]}")
    pub = repo.published_version(c, t["id"])
    params = J(r["params"], {}) or {}
    stamp = iso(now())

    def write():
        vid = repo.insert_version(c, {"term_id": t["id"], "run_id": r["id"], "parent_id": pub["id"] if pub else None, "status": "draft",
                                      "name": params.get("name"), "rev": 0, "checked_rev": 0, "violations": len(hard),
                                      "score": json.dumps({**card, "hard": len(hard), "problems": hard[:200],
                                                           "kept_manual": (J(r["progress"], {}) or {}).get("kept_manual", 0)}),
                                      "inputs_fp": r["input_sha256"], "scope": r["scope"],
                                      "unplaced": out["counts"]["unplaced"], "excluded": out["counts"]["excluded"],
                                      "created_by": r["requested_by"], "created_at": stamp})
        repo.insert_placements(c, vid, out["placements"], "solver", stamp)
        repo.insert_unplaced(c, vid, out["unplaced"])
        repo.update_run(c, r["id"], status="done", version_id=vid, state=None, iterations=state["it"], cpu_ms=cpu, stopped=state.get("stopped"),
                        finished_at=stamp, progress=_progress(r, phase="done", placed=out["counts"]["placed"], unplaced=out["counts"]["unplaced"],
                                                              excluded=out["counts"]["excluded"], hard=len(hard)))
        notify(c, [r["requested_by"]], "timetable", T3("Cədvəl layihəsi hazırdır"), "", "/admin/timetable/build")
        return vid

    vid, ms = _tx(c, write)
    CACHE.pop(r["id"], None)
    _tx(c, lambda: repo.update_run(c, r["id"], progress=_progress(repo.run(c, r["id"]), tx_ms_max=ms)))
    return f"run {r['id']}: version {vid}"


def _score(v: dict, card: dict, hard: list[dict]) -> str:
    """A version's stored scorecard after a check: the violations themselves too (the grid marks their placements)."""
    return json.dumps({**card, "hard": len(hard), "problems": hard[:200], "kept_manual": (J(v["score"], {}) or {}).get("kept_manual", 0)})


def _check_run(c, r: dict, busy: bool, sol: dict) -> str:
    """The full check after manual edits: checked_rev becomes the rev read (moves are refused meanwhile, C18)."""
    v, t = repo.version(c, r["version_id"]), term(c, r["term_id"])
    if busy and (v["unplaced"] + len(repo.placements(c, v["id"]))) / 1000 > sol["atomic_exam_max_s"]:
        return f"run {r['id']}: waiting, an exam is open"
    c.execute("BEGIN")
    try:
        problem, _ = snapshot(c, t, J(v["scope"], {"all": True}))
        pls = [_as_meeting(p) for p in repo.placements(c, v["id"])]
        rev = repo.version(c, v["id"])["rev"]
    finally:
        c.rollback()
    hard, card = domain.check(problem, pls), domain.scorecard(problem, pls)
    stamp = iso(now())

    def write():
        repo.update_version(c, v["id"], checked_rev=rev, violations=len(hard), score=_score(v, card, hard))
        repo.update_run(c, r["id"], status="done", started_at=stamp, finished_at=stamp,
                        progress=_progress(r, phase="done", hard=len(hard), violations=hard[:50]))

    _tx(c, write)
    return f"run {r['id']}: check, {len(hard)} violations"


# ---------------------------------------------------------------- versions, grid and the editor (design §7.4)
def versions(c, user, tid: int) -> list[dict]:
    term(c, tid)
    s = scope_of(c, user)
    return [{**v, "scope": J(v["scope"], {})} for v in repo.versions(c, tid) if _visible(c, user, v, s)]


def _version_out(v: dict) -> dict:
    return {k: v[k] for k in ("id", "term_id", "status", "name", "rev", "checked_rev", "violations", "unplaced", "excluded", "effective_from",
                              "parent_id", "published_at")}


def grid(c, user, vid: int, group_id: int | None, teacher_id: int | None, room_id: int | None) -> dict:
    v = version_for(c, user, vid)
    if sum(x is not None for x in (group_id, teacher_id, room_id)) != 1:
        raise HTTPError(400, "Qrup, müəllim və ya otaq seçin")
    t = term(c, v["term_id"])
    if group_id is not None:
        group_for(c, user, t, group_id, write=False)
    elif teacher_id is not None:
        teacher_for(c, user, t, teacher_id, write=False)
    items = _in_scope(c, user, repo.grid(c, vid, group_id, teacher_id, room_id))
    fixed = _in_scope(c, user, _fixed_rows(c, v, t, group_id, teacher_id, room_id))
    _, times = bell(c)
    names = repo.groups_of_units(c, sorted({x["unit_id"] for x in items + fixed if x["unit_id"]}))
    info = repo.groups_info(c, sorted({g for v_ in names.values() for g in v_}))
    bad: dict[str, list[dict]] = {}
    for x in (J(v["score"], {}) or {}).get("problems") or []:
        for k in x["keys"]:
            bad.setdefault(k, []).append({"code": x["code"], "slot": x.get("slot")})
    out, rows_ = [], []
    for x in items:
        span = domain.pair_span(times, x["period"], x["duration"]) or ("", "")
        out.append({**x, "start": span[0], "end": span[1], "groups": [info[g]["name"] for g in names.get(x["unit_id"], []) if g in info],
                    "problems": titled(bad.get(x["meeting_key"], []), slot=True)})
    for r in fixed:
        pairs = domain.pairs_of(times, r["start"], r["end"])
        if pairs:
            rows_.append({"id": r["id"], "weekday": r["weekday"], "period": pairs[0], "duration": pairs[1], "start": r["start"], "end": r["end"],
                          "course": r["course"], "kind": r["unit_kind"] or r["kind"], "subgroup": r["subgroup"], "weeks": r["weeks"] or "all",
                          "teacher": r["teacher"], "room": r["room"], "groups": [info[g]["name"] for g in names.get(r["unit_id"], []) if g in info]})
    return {"version": _version_out(v), "items": out, "fixed": rows_, "times": times, "days": settings(c)["days"]}


def _fixed_rows(c, v: dict, t: dict, group_id: int | None, teacher_id: int | None, room_id: int | None) -> list[dict]:
    """The active rows of the term the version does not hold (hand-written rows, rows of units outside its scope): the
    run kept them as obstacles, so the editor shows them read-only."""
    if room_id is not None:
        rs = repo.room_rows(c, t["id"], [room_id])
    else:
        ids = repo.group_term_units(c, t["id"], [group_id]) if group_id is not None else repo.teacher_term_units(c, t["id"], teacher_id or 0)
        rs = repo.unit_rows(c, ids)
    held = {x["unit_id"] for x in repo.placements_of_units(c, v["id"], sorted({r["unit_id"] for r in rs if r["unit_id"]}))}
    return [r for r in rs if r["unit_id"] not in held]


def unplaced(c, user, vid: int) -> list[dict]:
    v = version_for(c, user, vid)
    s = scope_of(c, user)
    items = repo.unplaced(c, v["id"])
    us = {u["id"]: u for u in repo.units_by_id(c, sorted({x["unit_id"] for x in items})) if covers(s, u)}
    return [{**x, **{k: us[x["unit_id"]][k] for k in ("course", "kind", "teacher_id", "subgroup")}, "reasons": titled(J(x["reasons"], []) or [])}
            for x in items if x["unit_id"] in us]


def scorecard(c, user, vid: int) -> dict:
    v = version_for(c, user, vid)
    return {"version": _version_out(v), "score": J(v["score"], {}), "stale": v["checked_rev"] != v["rev"]}


def _neighbourhood(c, v: dict, t: dict, p: dict, extra_rooms: tuple = ()) -> tuple[dict, list[dict]]:
    """The placements and obstacles a move of ``p`` can meet, read through indexes (C6): the units of its teacher and its
    groups this term with their placements in the version (or their rows, when they have none), and the rooms it may
    take with what else is in them."""
    unit = repo.units_by_id(c, [p["unit_id"]])
    if not unit:
        raise HTTPError(409, "Tədris vahidi artıq aktiv deyil: hesablamanı yenidən başladın")
    u = unit[0]
    mine = repo.groups_of_units(c, [u["id"]]).get(u["id"], [])
    ids = sorted({u["id"]} | set(repo.teacher_term_units(c, t["id"], u["teacher_id"]) if u["teacher_id"] else [])
                 | set(repo.group_term_units(c, t["id"], mine)))
    us = repo.units_by_id(c, ids)
    ug = repo.groups_of_units(c, [x["id"] for x in us])
    pls = repo.placements_of_units(c, v["id"], [x["id"] for x in us])
    placed = {x["unit_id"] for x in pls}
    _, times = bell(c)
    obstacles = [o for o in (_obstacle(r, ug, times) for r in repo.unit_rows(c, ids) if r["unit_id"] not in placed) if o]
    problem = _problem(c, t, us, ug, obstacles, [], [_as_meeting(x) for x in pls if x["locked"]])
    m = next((x for x in domain.meetings_of(problem)[0] if x["key"] == p["meeting_key"]), None)
    rooms = sorted({r["id"] for r in problem["rooms"] if m and domain.room_fits(m, r)} | {r for r in extra_rooms if r})
    seen = {x["id"] for x in pls}
    others = [x for x in repo.placements_in_rooms(c, v["id"], rooms) if x["id"] not in seen]
    in_rooms = repo.room_rows(c, t["id"], rooms)
    in_version = {x["unit_id"] for x in repo.placements_of_units(c, v["id"], sorted({x["unit_id"] for x in in_rooms if x["unit_id"]}))}
    for x in others:
        problem["obstacles"].append({**_as_meeting(x), "key": f"p:{x['id']}", "teacher_id": None, "groups": []})
    for r in in_rooms:
        if r["unit_id"] not in in_version and r["unit_id"] not in ids:
            o = _obstacle(r, {}, times)
            if o:
                problem["obstacles"].append({**o, "teacher_id": None, "groups": []})
    return problem, [_as_meeting(x) for x in pls]


def _placement(c, user, vid: int, pid: int) -> dict:
    """A placement of a unit in the caller's scope (a faculty's academic office never edits another faculty's units)."""
    p = repo.placement(c, vid, pid)
    if not p or not covers(scope_of(c, user), (repo.units_by_id(c, [p["unit_id"]]) or [{}])[0]):
        raise HTTPError(404, "Yerləşdirmə tapılmadı")
    return p


def _in_scope(c, user, items: list[dict]) -> list[dict]:
    """The items (with ``unit_id``) of units the caller's scope covers."""
    s = scope_of(c, user)
    if s["all"]:
        return items
    ok = {u["id"] for u in repo.units_by_id(c, sorted({x["unit_id"] for x in items if x.get("unit_id")})) if covers(s, u)}
    return [x for x in items if x.get("unit_id") in ok]


def options(c, user, vid: int, pid: int) -> dict:
    v = version_for(c, user, vid)
    p = _placement(c, user, vid, pid)
    problem, pls = _neighbourhood(c, v, term(c, v["term_id"]), p)
    opts = domain.options(problem, pls, p["meeting_key"])
    return {"placement": p, "rev": v["rev"], "options": [{**o, "reasons": titled([{"code": x} for x in o["reasons"]], slot=True)} for o in opts]}


def _editable(c, v: dict):
    if v["status"] not in EDITABLE:
        raise HTTPError(409, "Bu versiya dəyişdirilə bilməz")
    if repo.version_busy(c, v["term_id"], v["id"]):
        raise HTTPError(409, "Versiya yoxlanılır və ya dərc olunur: bir az sonra yenidən cəhd edin")


def move(c, user, vid: int, pid: int, body) -> dict:
    """A move with the live clash check: every hard rule against the neighbourhood, read without the write lock; then
    the optimistic lock on ``rev`` inside one short write (design §7.4)."""
    v = version_for(c, user, vid)
    _editable(c, v)
    p = _placement(c, user, vid, pid)
    rev = body.integer("rev", None)
    wd, period = body.integer("weekday", None), body.integer("period", None)
    room = body.get("room_id", p["room_id"])
    if (rev is None or wd is None or period is None or not 1 <= wd <= 7 or not 1 <= period <= len(bell(c)[1])
            or (room is not None and (type(room) is not int or room < 1))):
        raise HTTPError(400, "Yeni vaxtı, otağı və versiyanın düzəliş nömrəsini göndərin")
    if rev != v["rev"]:
        raise HTTPError(409, "Layihə dəyişib: səhifəni yeniləyin")
    to = {**_as_meeting(p), "weekday": wd, "period": period, "weeks": body.text("weeks", 100) or p["weeks"], "room_id": room}
    problem, pls = _neighbourhood(c, v, term(c, v["term_id"]), p, (room,))
    found = domain.move_problems(problem, pls, to)
    if found:
        raise Refused(409, E("Bu vaxtda toqquşma var"), reasons=titled([{k: x[k] for k in ("code", "keys", "slot")} for x in found], slot=True))
    if not repo.bump_rev(c, vid, rev):                # the write lock from here: rev, the busy check again, the move, the audit
        raise HTTPError(409, "Layihə dəyişib: səhifəni yeniləyin")
    if repo.version_busy(c, v["term_id"], vid):
        raise HTTPError(409, "Versiya yoxlanılır və ya dərc olunur: bir az sonra yenidən cəhd edin")
    to["weeks"] = domain.week_text(domain.week_mask(to["weeks"], problem["weeks"]), problem["weeks"])
    repo.move_placement(c, pid, to, user["id"], iso(now()))
    audit(c, user["id"], "tt_move", "tt_version", f"{vid} · {p['meeting_key']} · {p['weekday']}/{p['period']} {p['weeks']} #{p['room_id']} → "
                                                   f"{wd}/{period} {to['weeks']} #{room}")
    return {"rev": rev + 1, "placement": repo.placement(c, vid, pid)}


def lock(c, user, vid: int, body) -> dict:
    v = version_for(c, user, vid)
    _editable(c, v)
    ids, locked, rev = body.ids("ids", 2000), body.get("locked"), body.integer("rev", None)
    if not ids or not isinstance(locked, bool) or rev is None:
        raise HTTPError(400, "Yerləşdirmələri, kilidin vəziyyətini və versiyanın düzəliş nömrəsini göndərin")
    if not scope_of(c, user)["all"]:                     # only placements of units in the caller's scope
        mine = {x["id"] for x in _in_scope(c, user, repo.placements(c, vid))}
        ids = [i for i in ids if i in mine]
        if not ids:
            raise HTTPError(404, "Yerləşdirmə tapılmadı")
    if not repo.bump_rev(c, vid, rev):
        raise HTTPError(409, "Layihə dəyişib: səhifəni yeniləyin")
    n = repo.set_locked(c, vid, ids, locked, user["id"], iso(now()))
    audit(c, user["id"], "tt_lock", "tt_version", f"{vid} · {n} · {'locked' if locked else 'unlocked'}")
    return {"rev": rev + 1, "changed": n}


# ---------------------------------------------------------------- publishing (design §7.5, §8.2)
def _gate(c, v: dict, t: dict, eff, accept, reason: str) -> list[dict]:
    st = settings(c)
    out: list[str] = []
    if v["status"] not in EDITABLE:
        out.append("status")
    if v["checked_rev"] != v["rev"] or v["violations"] != 0:
        out.append("unchecked")
    pub = repo.published_version(c, t["id"])
    if (pub["id"] if pub else None) != v["parent_id"]:
        out.append("stale_parent")
    if set(st["publish_requires"]) - set(st["confirmed"]):
        out.append("unconfirmed")
    if domain.gate(domain.readiness(_facts(c, t, {"all": True, "faculties": set(), "departments": set(), "courses": set()}), st, _today()), "publish"):
        out.append("readiness")
    earliest = (now().date() + timedelta(days=st["notice_days"])).isoformat()
    if not (isinstance(eff, str) and _iso_day(eff) and t["teaching_start"] <= eff <= t["teaching_end"] and eff >= earliest):
        out.append("effective_from")
    if accept != v["unplaced"]:
        out.append("unplaced_count")
    if st["review_required"] and len(reason) < 10:      # the review step comes with the pages; until then a reason is required
        out.append("review")
    return titled([{"code": x} for x in out])


def _iso_day(v: str) -> bool:
    try:
        return date.fromisoformat(v).isoformat() == v
    except ValueError:
        return False


def publish(c, user, vid: int, body) -> dict:
    v = version_for(c, user, vid)
    if not scope_of(c, user)["all"]:
        raise HTTPError(403, "Cədvəli yalnız bütün universitet üzrə səlahiyyəti olan tədris hissəsi dərc edir")
    t = term(c, v["term_id"])
    eff, accept, reason = body.text("effective_from", 10), body.integer("accept_unplaced", None, lo=0), body.text("override_reason", 500)
    gate = _gate(c, v, t, eff, accept, reason)
    if gate:
        raise Refused(409, E("Cədvəl dərc oluna bilməz"), gate=gate)
    try:
        rid = repo.insert_run(c, {"term_id": t["id"], "kind": "publish", "version_id": v["id"], "effective_from": eff, "scope": v["scope"],
                                  "params": json.dumps({"accept_unplaced": accept, "override_reason": reason or None}, ensure_ascii=False),
                                  "status": "queued", "seed": 0, "iter_budget": 0, "time_budget_s": 0,
                                  "progress": json.dumps({"step": "check", "cursor": 0}), "requested_by": user["id"], "requested_at": iso(now())})
    except sqlite3.IntegrityError:
        raise HTTPError(409, "Bu semestr üçün başqa hesablama gedir") from None
    audit(c, user["id"], "tt_publish_requested", "tt_version", f"{v['id']} · {eff} · {reason}"[:500])
    return run_out(repo.run(c, rid))


def _fail(c, r: dict, problems: list[dict], message: dict, version: dict | None = None) -> str:
    """A publication refused before any row is written: why, in every language, with each problem titled and named."""
    found = named(c, problems[:50], slot=True)

    def write():
        if version:                                     # the check found what the list and the grid must show
            repo.update_version(c, version["id"], **version["values"])
        repo.update_run(c, r["id"], status="failed", finished_at=iso(now()), state=None, error=_err(message),
                        progress=_progress(r, step="failed", problems=found))
        notify(c, [r["requested_by"]], "timetable", T3("Cədvəl dərc olunmadı: yoxlamadan keçmədi"), "", "/admin/timetable/build")
    _tx(c, write)
    return f"run {r['id']}: publish refused"


def publish_step(c, r: dict, budget: float) -> str:
    """Steps check -> rows -> drop -> lessons -> notify -> done; each step or batch writes its effect and its cursor in
    one short transaction, so a crash repeats nothing and loses nothing (design §8.2)."""
    deadline = time.monotonic() + budget
    while True:
        r = repo.run(c, r["id"], blobs=True)
        step = (J(r["progress"], {}) or {}).get("step", "check")
        out = {"check": _p_check, "rows": _p_rows, "drop": _p_drop, "lessons": _p_lessons, "notify": _p_notify, "done": _p_done}[step](c, r)
        r = repo.run(c, r["id"])
        if r["status"] != "running" or time.monotonic() >= deadline:
            return out


def _p_save(c, r: dict, state: dict | None, **progress):
    """The bookkeeping of a step, in the transaction of its effect."""
    p = {**(J(r["progress"], {}) or {}), **progress}
    repo.update_run(c, r["id"], progress=json.dumps(p), **({"state": _z(state)} if state is not None else {}), heartbeat_at=iso(now()))


def _timed(c, r: dict, fn) -> None:
    _, ms = _tx(c, fn)
    p = J(repo.run(c, r["id"])["progress"], {}) or {}
    if ms > p.get("tx_ms_max", 0):
        _tx(c, lambda: repo.update_run(c, r["id"], progress=json.dumps({**p, "tx_ms_max": ms})))


def _p_check(c, r: dict) -> str:
    v, t = repo.version(c, r["version_id"]), term(c, r["term_id"])
    params = J(r["params"], {}) or {}
    gate = _gate(c, v, t, r["effective_from"], params.get("accept_unplaced"), params.get("override_reason") or "")
    if gate:
        return _fail(c, r, [{"code": x["code"]} for x in gate], T3("Dərc dayandırıldı: versiya dərcin şərtlərinə cavab vermir"))
    c.execute("BEGIN")
    try:
        problem, kept = snapshot(c, t, J(v["scope"], {"all": True}))
        pls = repo.placements(c, v["id"])
        trows = repo.term_rows(c, t["id"])
        units_ = {u["id"]: u for u in repo.term_units(c, t["id"])}
        ug = repo.term_unit_groups(c, t["id"])
        codes = {x["id"]: x["code"] for x in repo.rooms(c)}
    finally:
        c.rollback()
    hard = domain.check(problem, [_as_meeting(p) for p in pls])
    if hard:
        card = domain.scorecard(problem, [_as_meeting(p) for p in pls])
        return _fail(c, r, hard, T3("Dərc dayandırıldı: yoxlama qaydaların pozuntusunu tapdı"),
                     {"id": v["id"], "values": {"checked_rev": v["rev"], "violations": len(hard), "score": _score(v, card, hard)}})
    _, times = bell(c)
    st = settings(c)
    wanted = [domain.published_row(p, times, st["pair_hours"]) for p in pls]
    if any(w is None for w in wanted):
        return _fail(c, r, [{"code": "duration", "keys": [p["meeting_key"]]} for p, w in zip(pls, wanted, strict=True) if w is None],
                     T3("Dərc dayandırıldı: dərslərdən biri zəng cədvəlindən kənara çıxır"))
    s = _scope_from_run(J(v["scope"], {"all": True}))
    # a unit with hand-written rows was kept out of the run: its builder rows are obstacles and stay (design §16.4)
    published = [x for x in trows if x["meeting_key"] and x["unit_id"] in units_ and x["unit_id"] not in set(kept)
                 and covers(s, units_[x["unit_id"]])]
    plan = domain.publish_plan(published, wanted)                                 # type: ignore[arg-type]
    replaced = {x["id"] for x in plan["update"]} | set(plan["deactivate"])
    slots = [{"id": f"k:{w['meeting_key']}", "weekday": w["weekday"], "start": w["start"], "end": w["end"], "weeks": w["weeks"],
              "room": f"#{w['room_id']}" if w["room_id"] else None, "teacher_id": units_[w["unit_id"]]["teacher_id"] if w["unit_id"] in units_ else None,
              "groups": [(g, units_[w["unit_id"]]["subgroup"]) for g in ug.get(w["unit_id"], [])] if w["unit_id"] in units_ else []}
             for w in wanted if w] + [
             {"id": f"r:{x['id']}", "weekday": x["weekday"], "start": x["start"], "end": x["end"], "weeks": x["weeks"] or "all",
              "room": f"#{x['room_id']}" if x["room_id"] else x["room"], "teacher_id": x["teacher_id"],
              "groups": [(g, x["subgroup"]) for g in ug.get(x["unit_id"], [])] if x["unit_id"] else []}
             for x in trows if x["id"] not in replaced and x["id"] not in plan["unchanged"]]
    clashes = domain.conflicts_all(slots)
    if clashes:
        return _fail(c, r, [{"code": f"{x['what']}_clash", "keys": [k[2:] for k in (x["a"], x["b"]) if k.startswith("k:")]} for x in clashes],
                     T3("Dərc dayandırıldı: yeni sətirlər cədvəldəki başqa sətirlərlə toqquşur"))
    ops = ([{"op": "update", **x} for x in plan["update"]] + [{"op": "insert", **x} for x in plan["insert"]]
           + [{"op": "deactivate", "id": x} for x in plan["deactivate"]])
    for o in ops:
        if o["op"] != "deactivate":
            u = units_[o["unit_id"]]
            o.update(course_id=u["course_id"], kind=domain.KIND_LABEL.get(u["kind"], u["kind"]), room=codes.get(o["room_id"]))
    changed = sorted({o["unit_id"] for o in ops if o["op"] != "deactivate"} | {x["unit_id"] for x in published if x["id"] in plan["deactivate"]})
    state = {"ops": ops, "made": [], "drop": [], "units": changed, "counts": {k: len(v_) for k, v_ in plan.items()}}
    _timed(c, r, lambda: (repo.update_run(c, r["id"], status="running", started_at=iso(now())),
                          _p_save(c, r, state, step="rows", cursor=0, counts=state["counts"])))
    return f"run {r['id']}: checked"


def _p_rows(c, r: dict) -> str:
    state = _unz(r["state"]) or {}
    cur = (J(r["progress"], {}) or {}).get("cursor", 0)
    part = state["ops"][cur:cur + ROWS_BATCH]
    v = repo.version(c, r["version_id"])
    params = J(r["params"], {}) or {}

    def write():
        stamp = iso(now())
        for o in part:
            if o["op"] == "insert":
                state["made"].append(repo.insert_published(c, o, o["course_id"], o["kind"], o["room"], v["id"], stamp))
            elif o["op"] == "update":
                repo.update_published(c, o["id"], o, o["room"], v["id"], stamp)
                state["made"].append(o["id"])
                state["drop"].append(o["id"])
            else:
                repo.deactivate_row(c, o["id"], stamp)
                state["drop"].append(o["id"])
        last = cur + len(part) >= len(state["ops"])
        if last:
            repo.supersede(c, v["term_id"], v["id"])
            repo.update_version(c, v["id"], status="published", published_by=r["requested_by"], published_at=stamp,
                                effective_from=r["effective_from"], publish_note=params.get("override_reason"))
            repo.link_rows(c, v["id"])
        _p_save(c, r, state, **({"step": "drop", "cursor": 0} if last else {"cursor": cur + len(part)}))

    _timed(c, r, write)
    return f"run {r['id']}: rows {cur + len(part)}"


def _p_drop(c, r: dict) -> str:
    state = _unz(r["state"]) or {}
    cur = (J(r["progress"], {}) or {}).get("cursor", 0)
    part = state["drop"][cur:cur + DROP_BATCH]

    def write():
        n = sum(repo.drop_lessons_from(c, rid, r["effective_from"]) for rid in part)
        state["counts"]["lessons_dropped"] = state["counts"].get("lessons_dropped", 0) + n
        done = cur + len(part) >= len(state["drop"])
        _p_save(c, r, state, **({"step": "lessons", "cursor": 0} if done else {"cursor": cur + len(part)}))

    _timed(c, r, write)
    return f"run {r['id']}: drop {cur + len(part)}"


def _p_lessons(c, r: dict) -> str:
    state = _unz(r["state"]) or {}
    cur = (J(r["progress"], {}) or {}).get("cursor", 0)
    part = state["made"][cur:cur + LESSON_BATCH]
    t = term(c, r["term_id"])

    def write():
        made = rows_service.make_lessons(c, [repo.row_by_id(c, rid) for rid in part], t, date.fromisoformat(r["effective_from"]))
        state["counts"]["lessons_made"] = state["counts"].get("lessons_made", 0) + made
        done = cur + len(part) >= len(state["made"])
        _p_save(c, r, state, **({"step": "notify", "cursor": 0} if done else {"cursor": cur + len(part)}))

    _timed(c, r, write)
    return f"run {r['id']}: lessons {cur + len(part)}"


def _p_notify(c, r: dict) -> str:
    """One notification per affected person: the students of the changed units' groups and their teachers."""
    state = _unz(r["state"]) or {}
    cur = (J(r["progress"], {}) or {}).get("cursor", 0)
    if "people" not in state:
        us = repo.units_by_id(c, state["units"])
        groups_ = sorted({g for v_ in repo.groups_of_units(c, [u["id"] for u in us]).values() for g in v_})
        teachers = sorted({u["teacher_id"] for u in us if u["teacher_id"]})
        state["people"] = [[s, "s"] for s in repo.students_of_groups(c, groups_) if s not in teachers] + [[x, "t"] for x in teachers]
        state["people"].sort()
    part = state["people"][cur:cur + NOTIFY_BATCH]

    def write():
        day = date.fromisoformat(r["effective_from"])                  # the date as the portal writes dates in each language
        title = {lg: S(S_("Dərs cədvəliniz {date} tarixindən dəyişir"), lg, date=day.strftime("%d/%m/%Y" if lg == "en" else "%d.%m.%Y"))
                 for lg in LANGS}
        for who, link in (("s", "/student/schedule"), ("t", "/teacher/schedule")):
            ids = [x for x, k in part if k == who]
            if ids:
                notify(c, ids, "schedule", title, "", link)
        done = cur + len(part) >= len(state["people"])
        state["counts"]["notified"] = state["counts"].get("notified", 0) + len(part)
        _p_save(c, r, state, **({"step": "done", "cursor": 0} if done else {"cursor": cur + len(part)}))

    _timed(c, r, write)
    return f"run {r['id']}: notified {cur + len(part)}"


def _p_done(c, r: dict) -> str:
    state = _unz(r["state"]) or {}

    def write():
        counts = state.get("counts", {})
        audit(c, r["requested_by"], "timetable_publish", "tt_version", f"{r['version_id']} · {r['effective_from']} · "
              + ", ".join(f"{k} {x}" for k, x in sorted(counts.items())))
        notify(c, [r["requested_by"]], "timetable", T3("Cədvəl dərc olundu"), "", "/admin/timetable/build")
        repo.update_run(c, r["id"], status="done", finished_at=iso(now()), progress=_progress(r, step="done", counts=counts))

    _tx(c, write)
    return f"run {r['id']}: published"
