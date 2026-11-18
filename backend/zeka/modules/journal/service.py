"""The attendance journal (tasks/todo.md, Task 20): a lesson's list and marks, the teacher's edit window, corrections by a
department head with a reason, a substitute teacher, and each student's share of missed hours per course."""
from __future__ import annotations

from datetime import timedelta

from ...core import perms, tenant
from ...core.i18n import E
from ...legacy.store import audit, iso, now
from ..timetable import domain as timetable_rules
from ..timetable import service as timetable
from . import domain, repo

READERS = ("admin", "academic_office", "leader", "office")          # see every course (a dean's office: its faculty's students)


def _today() -> str:
    return now().date().isoformat()


def may_correct(c, user, course: dict) -> bool:
    """A department head (of the course's department when the role is scoped to departments) or an administrator."""
    if not perms.has(user["role"], "journal.correct"):
        return False
    if user["role"] == "dept_head":
        scopes = repo.dept_scopes(c, user["id"])
        return not scopes or course.get("department_id") in scopes
    return True


def _audience(c, lessons: list[dict]):
    return timetable.audience(c, sorted({x["unit_id"] for x in lessons if x.get("unit_id")}))


def roster(c, les: dict) -> list[dict]:
    """The students on a lesson's list: an enrolment in force on its day, the unit's group and subgroup."""
    aud = _audience(c, [les])
    return [s for s in repo.enrolments(c, les["course_id"]) if timetable_rules.on_list(s, les, aud)]


def lesson_view(c, user, lid: int) -> dict | None:
    """The lesson, its list with the marks, and what this user may do; None when the user may not see it."""
    les = repo.lesson(c, lid)
    if not les:
        return None
    corrector = may_correct(c, user, les)
    mine = les["teacher_id"] == user["id"] or les["course_teacher"] == user["id"]
    if not (mine or corrector or user["role"] in ("admin", "academic_office", "leader")):
        return None
    rules = tenant.load(c)["journal"]
    cutover = rules["cutover_date"]
    before = bool(cutover and les["day"] <= cutover)
    window = domain.window_open(les["day"], les["end"], now(), rules["edit_hours"])
    teacher_may = les["teacher_id"] == user["id"] and window and not before
    held = les["status"] != "cancelled" and les["day"] <= _today()
    marks = repo.marks(c, lid)
    students = [{"id": s["id"], "full_name": s["full_name"], "student_no": s["student_no"], "group": s["grp"], "subgroup": s["subgroup"],
                 "status": (marks.get(s["id"]) or {}).get("status"), "source": (marks.get(s["id"]) or {}).get("source"),
                 "request_id": (marks.get(s["id"]) or {}).get("request_id")} for s in roster(c, les)]
    return {"lesson": {k: les[k] for k in ("id", "course_id", "course", "course_code", "day", "start", "end", "kind", "room", "status",
                                           "note", "teacher_id", "teacher", "academic_hours", "unit_id")},
            "students": students, "recorded": bool(marks), "before_cutover": before, "window_open": window, "corrector": corrector,
            "edit_hours": rules["edit_hours"], "can_mark": held and (teacher_may or corrector), "needs_reason": held and corrector and not teacher_may,
            "can_substitute": corrector and les["day"] >= _today() and les["status"] != "cancelled"}


def save_marks(c, user, lid: int, body) -> tuple[str, object]:
    """('ok', view) | ('missing', None) | ('forbidden', reason) | ('invalid', reason). Saving the same marks again changes
    nothing; an excused absence (an approved request) is never overwritten by a mark."""
    view = lesson_view(c, user, lid)
    if not view:
        return "missing", None
    if not view["can_mark"]:
        les = view["lesson"]
        if les["status"] == "cancelled" or les["day"] > _today():
            return "forbidden", E("Bu dərs keçirilməyib: davamiyyət yazılmır")
        if view["before_cutover"]:
            return "forbidden", E("Kəsid tarixinə qədərki dərsin davamiyyəti köhnə sistemdən idxal olunur; onu kafedra müdiri düzəldir")
        return "forbidden", E("Düzəliş müddəti ({n} saat) bitib: dəyişikliyi kafedra müdiri səbəblə edir", n=view["edit_hours"])
    reason = " ".join(str(body.get("reason") or "").split())[:300]
    if view["needs_reason"] and len(reason) < 3:
        return "invalid", E("Düzəlişin səbəbini yazın")
    marks, problem = domain.marks_input(body, {s["id"] for s in view["students"]})
    if problem:
        return "invalid", problem
    current = {s["id"]: s for s in view["students"]}
    changes = [(uid, current[uid]["status"], m) for uid, m in marks.items()
               if current[uid]["status"] != m and not (current[uid]["status"] == "excused" and current[uid]["request_id"])]
    if not view["corrector"] and any(current[uid]["source"] == "legacy" for uid, _, _ in changes):
        return "forbidden", E("İdxal olunmuş davamiyyəti yalnız kafedra müdiri səbəblə dəyişir")
    if changes:
        repo.write_marks(c, lid, [(uid, new) for uid, _, new in changes], user["id"], iso(now()))
        if view["needs_reason"] or any(old is not None for _, old, _ in changes):
            audit(c, user["id"], "attendance_corrected" if view["needs_reason"] else "attendance_changed", "lesson",
                  f"#{lid} · " + ", ".join(f"#{uid}: {old or '-'} → {new}" for uid, old, new in changes if old is not None or view["needs_reason"])
                  + (f" · {reason}" if reason else ""))
    return "ok", lesson_view(c, user, lid)


def substitute(c, user, lid: int, body) -> tuple[str, object]:
    """A department head names another teacher for one lesson, with a reason; the change is in the audit log."""
    les = repo.lesson(c, lid)
    if not les or not may_correct(c, user, les):
        return "missing", None
    tid = body.get("teacher_id")
    new = repo.teacher(c, tid) if isinstance(tid, int) and not isinstance(tid, bool) else None
    reason = " ".join(str(body.get("reason") or "").split())[:300]
    if not new:
        return "invalid", E("Müəllimi seçin")
    if len(reason) < 3:
        return "invalid", E("Əvəzetmənin səbəbini yazın")
    if les["status"] == "cancelled" or les["day"] < _today():
        return "invalid", E("Yalnız qarşıdakı dərsin müəllimi dəyişdirilir")
    repo.set_teacher(c, lid, new["id"], iso(now()))
    audit(c, user["id"], "lesson_substitute", "lesson", f"#{lid} · {les['course']} {les['day']} {les['start']} · "
                                                        f"#{les['teacher_id']} → #{new['id']} · {reason}")
    return "ok", lesson_view(c, user, lid)


# ---------------------------------------------------------------- standing
def course_standing(c, course_id: int, uid: int | None = None) -> list[dict]:
    """Each active student's standing in the course (one student with ``uid``): hours, share, status."""
    co = repo.course(c, course_id)
    if not co:
        return []
    term = timetable.term(c, co["term_id"])
    rules = tenant.load(c)
    att, cutover = rules["attendance"], rules["journal"]["cutover_date"]
    limit = domain.effective_limit(att["limit_percent"], co.get("attendance_limit"))
    lessons = [x for x in repo.course_lessons(c, course_id, term["teaching_start"], term["teaching_end"]) if x["status"] != "cancelled"] \
        if term else []
    aud = _audience(c, lessons)
    recs = repo.records(c, course_id, uid)
    opens = repo.openings(c, course_id, term["id"] if term else None, uid)
    out = []
    for s in repo.enrolments(c, course_id, uid):
        mine = [x for x in lessons if timetable_rules.on_list(s, x, aud)]
        opening = opens.get(s["id"])
        st = domain.standing(mine, {x["id"]: recs[(s["id"], x["id"])] for x in mine if (s["id"], x["id"]) in recs},
                             cutover=opening["as_of"] if opening else cutover, opening=opening,
                             excused_counts=att["excused_counts_toward_limit"], limit_percent=limit)
        out.append({"student_id": s["id"], "full_name": s["full_name"], "student_no": s["student_no"], "group": s["grp"],
                    "planned_lessons": len(mine), "opening_id": opening["id"] if opening else None, **st})
    return out


def can_read_course(c, user, course_id: int) -> bool:
    co = repo.course(c, course_id)
    return bool(co) and (user["role"] in READERS or repo.teaches(c, user["id"], course_id) or may_correct(c, user, co))


def planned_until(c, student_id: int, course_id: int, as_of: str) -> int | None:
    """The hours Zəka planned for a student in a course up to ``as_of`` (an import compares the held hours with it)."""
    co = repo.course(c, course_id)
    term = timetable.term(c, co["term_id"]) if co else None
    if not term:
        return None
    lessons = [x for x in repo.course_lessons(c, course_id, term["teaching_start"], min(as_of, term["teaching_end"]))
               if x["status"] != "cancelled"]
    aud = _audience(c, lessons)
    s = repo.enrolments(c, course_id, student_id)
    return sum(domain.hours(x) for x in lessons if s and timetable_rules.on_list(s[0], x, aud))


def correct_opening(c, user, oid: int, body) -> tuple[str, object]:
    o = repo.opening(c, oid)
    if not o or not may_correct(c, user, o):
        return "missing", None
    values = {}
    for k in ("held_hours", "unexcused_hours", "excused_hours"):
        v = body.get(k, o[k])
        if type(v) is not int or not 0 <= v <= 5000:
            return "invalid", E("Saatlar 0 ilə 5000 arasında tam ədəd olmalıdır")
        values[k] = v
    if values["unexcused_hours"] + values["excused_hours"] > values["held_hours"]:
        return "invalid", E("Buraxılmış saatlar keçilmiş saatlardan çox ola bilməz")
    reason = " ".join(str(body.get("reason") or "").split())[:300]
    if len(reason) < 3:
        return "invalid", E("Düzəlişin səbəbini yazın")
    repo.update_opening(c, oid, values, iso(now()))
    audit(c, user["id"], "opening_corrected", "attendance_opening",
          f"#{oid} · " + ", ".join(f"{k}: {o[k]} → {values[k]}" for k in values if o[k] != values[k]) + f" · {reason}")
    return "ok", {**o, **values}


def teacher_lessons(c, user, day: str | None) -> list[dict]:
    d = day or _today()
    first = (now().date() - timedelta(days=14)).isoformat() if not day else d
    return repo.lessons_of_teacher(c, user["id"], first, d)
