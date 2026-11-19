"""The attendance journal (tasks/todo.md, Task 20): a lesson's list and marks, the teacher's edit window, corrections by a
department head with a reason, a substitute teacher, and each student's share of missed hours per course."""
from __future__ import annotations

from datetime import timedelta

from ...core import perms, tenant
from ...core.web import an_id
from ...core.i18n import E
from ...legacy.store import J, audit, iso, now
from ..timetable import domain as timetable_rules
from ..timetable import service as timetable
from . import domain, repo

READERS = ("admin", "academic_office", "leader", "office")          # see every course (a dean's office: its faculty's students)


def _today() -> str:
    return now().date().isoformat()


def head_covers(c, uid: int, course_id: int, department_id: int | None) -> bool:
    """Whether a department head's grants cover the course (as for the journal; also a request's step, Task 46)."""
    return repo.dept_head_covers(c, uid, course_id, department_id)


def may_correct(c, user, course: dict) -> bool:
    """An administrator, or a department head whose grant covers the course (Checkpoint C, J1): a grant of its department,
    of its faculty, of the course itself or one with no scope; a department head with no grant, of the department the
    person belongs to. ``course`` is a course row or a row of one (a lesson, an opening) with ``course_id``."""
    if not perms.has(user["role"], "journal.correct"):
        return False
    if user["role"] == "dept_head":
        return repo.dept_head_covers(c, user["id"], course.get("course_id") or course["id"], course.get("department_id"))
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
    if any(m == "excused" and current[uid]["status"] != "excused" for uid, m in marks.items()):
        return "invalid", E("Qeyd iştirak, qayıb və ya gecikmə olmalıdır")          # 'excused' comes from an approved request
    changes = [(uid, current[uid]["status"], m) for uid, m in marks.items()
               if current[uid]["status"] != m and not (current[uid]["status"] == "excused" and current[uid]["request_id"])]
    if not view["corrector"] and any(current[uid]["source"] == "legacy" for uid, _, _ in changes):
        return "forbidden", E("İdxal olunmuş davamiyyəti yalnız kafedra müdiri səbəblə dəyişir")
    if view["before_cutover"]:
        # before the cut-over only imported rows count (Checkpoint C, J7): a new row there would change nothing, so a mark
        # sent for a student with no imported row is refused and the "present" every other student defaults to is not written
        named = {int(k) for k in (body.get("marks") or {}) if str(k).isdigit()}
        if any(current[uid]["source"] != "legacy" and uid in named for uid, _, _ in changes):
            return "forbidden", E("Kəsid tarixinə qədərki dərsin davamiyyəti köhnə sistemdən idxal olunur; onu kafedra müdiri düzəldir")
        changes = [x for x in changes if current[x[0]]["source"] == "legacy"]
    if changes:
        repo.write_marks(c, lid, [(uid, new) for uid, _, new in changes], user["id"], iso(now()))
        refresh_finals(c, view["lesson"]["course_id"], [uid for uid, _, _ in changes])
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
    tid = an_id(body.get("teacher_id"))
    new = repo.teacher(c, tid) if tid else None
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
    today = _today()
    out = []
    for s in repo.enrolments(c, course_id, uid):
        mine = [x for x in lessons if timetable_rules.on_list(s, x, aud)]
        opening = opens.get(s["id"])
        st = domain.standing(mine, {x["id"]: recs[(s["id"], x["id"])] for x in mine if (s["id"], x["id"]) in recs},
                             cutover=opening["as_of"] if opening else cutover, opening=opening,
                             excused_counts=att["excused_counts_toward_limit"], limit_percent=limit)
        out.append({"student_id": s["id"], "full_name": s["full_name"], "student_no": s["student_no"], "group": s["grp"],
                    "planned_lessons": len(mine), "opening_id": opening["id"] if opening else None,
                    "held_hours": sum(domain.hours(x) for x in mine if x["day"] <= today), **st})
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
    refresh_finals(c, o["course_id"], [o["student_id"]])
    audit(c, user["id"], "opening_corrected", "attendance_opening",
          f"#{oid} · " + ", ".join(f"{k}: {o[k]} → {values[k]}" for k in values if o[k] != values[k]) + f" · {reason}")
    return "ok", {**o, **values}


def teacher_lessons(c, user, day: str | None) -> list[dict]:
    d = day or _today()
    first = (now().date() - timedelta(days=14)).isoformat() if not day else d
    return repo.lessons_of_teacher(c, user["id"], first, d)


# ---------------------------------------------------------------- grades (Task 21)
def columns(c, co: dict) -> list[dict]:
    """The course's components: the published syllabus's scheme (Task 25), the university's until there is one."""
    return domain.scheme(course_grading(c, co))


def course_grading(c, co: dict) -> dict:
    """The grading scheme a course is marked by: the components and exam of its published syllabus; the pass mark,
    the letter scale and the exam minimum are always the university's."""
    grading = tenant.load(c)["grading"]
    own = J(co.get("grading"), None) if co.get("grading") else None
    return {**grading, **own} if isinstance(own, dict) else grading


def _writable(c, user, co: dict, students: list[dict]) -> set[int]:
    """The students whose scores this user writes: a corrector all of them; a teacher the students on the lists of their
    own units of the course (all of them for the course's teacher when the course has no units)."""
    if may_correct(c, user, co):
        return {s["id"] for s in students}
    mine = repo.units_of(c, co["id"], user["id"])
    if not mine:
        return {s["id"] for s in students} if co["teacher_id"] == user["id"] and not repo.units_of(c, co["id"]) else set()
    aud = timetable.audience(c, [u["id"] for u in mine])
    return {s["id"] for s in students if any(timetable_rules.attends(s, *aud[u["id"]]) for u in mine)}


def _attendance_cell(c, co: dict, cols: list[dict], standing: dict | None, rules: dict | None = None) -> float | None:
    col = next((x for x in cols if x["kind"] == "attendance"), None)
    if not col or not standing:
        return None
    return domain.attendance_score(standing, col["max"], (rules or tenant.load(c))["attendance"]["points_rule"])


def _result(c, cols: list[dict], cells: dict, attendance: float | None, rules: dict | None = None) -> dict:
    """The outcome by the columns' own components and exam (a course's published scheme or the university's)."""
    base = (rules or tenant.load(c))["grading"]
    exam_col = next(x for x in cols if x["kind"] == "exam")
    grading = {**base, "components": [{"name": x["key"], "max": x["max"]} for x in cols if x["kind"] != "exam"],
               "exam": {**base["exam"], "name": exam_col["key"], "max": exam_col["max"]}}
    scores = {x["key"]: (attendance if x["kind"] == "attendance" else cells.get(x["key"])) for x in cols if x["kind"] != "exam"}
    exam = next((cells.get(x["key"]) for x in cols if x["kind"] == "exam"), None)
    return tenant.outcome(scores, exam, grading)


def grade_table(c, user, course_id: int) -> dict | None:
    """The course's grade table for staff: every component, drafts included, with what this user may write."""
    co = repo.course(c, course_id)
    if not co or not can_read_course(c, user, course_id):
        return None
    cols = columns(c, co)
    students = repo.enrolments(c, course_id)
    rows_ = repo.grade_rows(c, course_id)
    stand = {x["student_id"]: x for x in course_standing(c, course_id)}
    writable = _writable(c, user, co, students)
    rules = tenant.load(c)
    out = []
    for s in students:
        cells = {x["key"]: rows_.get((s["id"], x["key"])) for x in cols if x["kind"] != "attendance"}
        att = _attendance_cell(c, co, cols, stand.get(s["id"]), rules)
        out.append({"id": s["id"], "full_name": s["full_name"], "student_no": s["student_no"], "group": s["grp"], "writable": s["id"] in writable,
                    "cells": {k: ({"score": v["score"], "status": v["status"], "source": v["source"]} if v else None) for k, v in cells.items()},
                    "attendance": att, "result": _result(c, cols, {k: v["score"] if v else None for k, v in cells.items()}, att, rules)})
    drafts = sum(1 for r in rows_.values() if r["status"] == "draft")
    return {"course": {k: co[k] for k in ("id", "code", "name", "credits")}, "columns": cols, "students": out, "drafts": drafts,
            "corrector": may_correct(c, user, co)}


def save_grades(c, user, course_id: int, body, answer: bool = True) -> tuple[str, object]:
    """('ok', table) | ('missing', None) | ('forbidden', reason) | ('invalid', reason) | ('cells', errors). A new score is a
    draft; a change of a published one needs a reason and goes to the grade journal."""
    table = grade_table(c, user, course_id)
    if not table:
        return "missing", None
    cells = body.get("cells")
    if not isinstance(cells, list) or len(cells) > 5000:
        return "invalid", E("Xanalar siyahı kimi göndərilməlidir")
    cols = {x["key"]: x for x in table["columns"]}
    students = {s["id"]: s for s in table["students"]}
    errors: list[dict] = []
    todo: list[tuple[int, dict, float | None]] = []
    for cell in cells:
        if not isinstance(cell, dict):
            return "invalid", E("Xanalar siyahı kimi göndərilməlidir")
        sid, key = cell.get("student_id"), cell.get("component")
        col, s = cols.get(key) if isinstance(key, str) else None, students.get(sid) if isinstance(sid, int) else None
        if not col or not s:
            errors.append({"student_id": sid, "component": key, "reason": E("Belə tələbə və ya komponent yoxdur")})
            continue
        if col["kind"] == "attendance":
            errors.append({"student_id": sid, "component": key, "reason": E("Davamiyyət balı jurnaldan hesablanır: cədvələ yazılmır")})
            continue
        if not s["writable"]:
            return "forbidden", E("Bu tələbə sizin tədris vahidinizin siyahısında deyil")
        if col["kind"] == "exam" and repo.exam_locked(c, course_id, s["id"]):
            return "forbidden", E("İmtahan cədvəli dekanlıqda bağlanıb: bu balı yalnız dekanlıq apellyasiya və ya əmrlə dəyişir")
        value, problem = domain.cell_value(cell.get("score"), col["max"])
        if problem:
            errors.append({"student_id": sid, "component": key, "reason": problem})
            continue
        todo.append((s["id"], col, value))
    if errors:
        return "cells", errors
    reason = " ".join(str(body.get("reason") or "").split())[:300]
    rows_ = repo.grade_rows(c, course_id)
    at = iso(now())
    published_changes = [(sid, col, v) for sid, col, v in todo
                         if (cur := rows_.get((sid, col["key"]))) and cur["status"] == "published" and cur["score"] != v]
    if published_changes and len(reason) < 3:
        return "invalid", E("Dərc olunmuş balın dəyişməsinin səbəbini yazın")
    touched = set()
    for sid, col, v in dict(((sid, col["key"]), (sid, col, v)) for sid, col, v in todo).values():   # one cell twice: the last wins
        cur = rows_.get((sid, col["key"]))
        if cur and cur["score"] == v:
            continue
        status = "published" if cur and cur["status"] == "published" else "draft"
        repo.put_grade(c, sid, course_id, col["key"], v, col["max"], status, user["id"], at)
        if status == "published":
            repo.add_change(c, sid, course_id, col["key"], cur["score"] if cur else None, v, user["id"], reason, at)
            touched.add(sid)
    refresh_finals(c, course_id, touched)
    if published_changes:
        audit(c, user["id"], "grades_changed", "course", f"#{course_id} · {len(published_changes)} · {reason}")
    if touched:                                                     # a published score changed: other systems hear it (Task 37)
        _published(c, course_id, len(touched))
    return "ok", grade_table(c, user, course_id) if answer else None


def _published(c, course_id: int, n: int):
    from ..integration import webhooks                          # here: integration reads the journal
    co = repo.course(c, course_id)
    webhooks.emit(c, "grade.published", {"course_id": course_id, "course_code": co["code"] if co else None, "scores": n})


def publish_grades(c, user, course_id: int) -> tuple[str, object]:
    table = grade_table(c, user, course_id)
    if not table:
        return "missing", None
    mine = [s["id"] for s in table["students"] if s["writable"]]
    if not mine:
        return "forbidden", E("Bu fənndə sizin tədris vahidinizin tələbəsi yoxdur")
    changed = repo.publish(c, course_id, mine, iso(now()))
    refresh_finals(c, course_id, changed)
    audit(c, user["id"], "grades_published", "course", f"#{course_id} · {len(changed)}")
    if changed:
        _published(c, course_id, len(changed))
    return "ok", grade_table(c, user, course_id)


def log_change(c, uid: int, course_id: int, component: str, old, new, by: int | None, reason: str, at: str):
    """A change of a published score made outside the table (an import), in the grade journal like the table's own."""
    repo.add_change(c, uid, course_id, component, old, new, by, reason, at)


def excuse(c, by: int, request_id: int, student_id: int, lesson_ids: list[int]) -> None:
    """The effect ``attendance.excuse`` of an approved absence excuse (Task 46): the absences become excused, with who and
    when (an export --since sees them, Task 37), and the final grades they move are recomputed."""
    if lesson_ids:
        for cid in repo.excuse(c, request_id, student_id, lesson_ids, by, iso(now())):
            refresh_finals(c, cid, [student_id])


def refresh_final(c, uid: int, course_id: int):
    refresh_finals(c, course_id, [uid])


def refresh_finals(c, course_id: int, uids) -> None:
    """The students' final grades in the course from the published scores and the journal's attendance: written once the
    exam is in, removed when not. A scheme with an attendance component and no attendance to count it from (no lesson
    held, no opening balance) gives no final grade: missing is not zero (Checkpoint C, J2). Called after every change
    that moves a total: a score, a mark, an opening balance, an excuse, the university's rules (J3)."""
    uids = set(uids)
    co = repo.course(c, course_id) if uids else None
    if not co:
        return
    has_attendance = any(x["kind"] == "attendance" for x in columns(c, co))
    t = repo.term(c, co["term_id"])
    for uid, (att, res) in published_results(c, co, uids).items():
        if res["total"] is None or (has_attendance and att is None):
            repo.drop_final(c, uid, course_id)
            continue
        repo.upsert_final(c, {"user_id": uid, "course_id": course_id, "term_id": co["term_id"], "term_name": t["name"] if t else "—",
                              "term_name_en": t["name"] if t else None, "term_start": t["teaching_start"] if t else None,
                              "course_code": co["code"], "course_name": co["name"], "course_name_en": None, "credits": co["credits"] or 0,
                              "score": res["total"], "letter": res["letter"], "passed": int(bool(res["passed"])), "published_at": iso(now())})


def published_results(c, co: dict, uids) -> dict[int, tuple[float | None, dict]]:
    """(attendance cell, result) of each student from the published scores, as ``student_grades`` gives one student's,
    in a fixed number of queries for any number of students (Checkpoint D, AR-4)."""
    uids = set(uids)
    if not uids:
        return {}
    cols, rules = columns(c, co), tenant.load(c)
    one = next(iter(uids)) if len(uids) == 1 else None
    published: dict[int, dict] = {}
    for (uid, key), r in repo.grade_rows(c, co["id"], one).items():
        if uid in uids and r["status"] == "published":
            published.setdefault(uid, {})[key] = r["score"]
    stand = {x["student_id"]: x for x in course_standing(c, co["id"], one)}
    out = {}
    for uid in uids:
        att = _attendance_cell(c, co, cols, stand.get(uid), rules)
        out[uid] = (att, _result(c, cols, published.get(uid, {}), att, rules))
    return out


def refresh_all_finals(c) -> None:
    """Every course's final grades again, after the university's grading or attendance rules changed."""
    for cid in repo.courses_with_published(c):
        refresh_finals(c, cid, [s["id"] for s in repo.enrolments(c, cid)])


def student_grades(c, uid: int, course: dict) -> dict:
    """What a student sees of one course: only published scores, the attendance component from the journal."""
    cols = columns(c, course)
    rows_ = {k[1]: r for k, r in repo.grade_rows(c, course["id"], uid).items() if r["status"] == "published"}
    st = next(iter(course_standing(c, course["id"], uid)), None)
    att = _attendance_cell(c, course, cols, st)
    items = []
    for x in cols:
        if x["kind"] == "exam":
            continue
        if x["kind"] == "attendance":
            items.append({"name": x["name"], "max": x["max"], "score": att, "note": "cari göstərici"})
        else:
            r = rows_.get(x["key"])
            items.append({"name": x["name"], "max": x["max"], "score": r["score"] if r else None, "note": "" if r else "hələ keçirilməyib"})
    return {"items": items, "result": _result(c, cols, {k: r["score"] for k, r in rows_.items()}, att), "exam_name": cols[-1]["name"]}


def transcript(c, uid: int) -> list[dict]:
    """The student's final grades by term, oldest first: the only source of a transcript."""
    out: list[dict] = []
    for r in repo.finals_of(c, uid):
        key = (r["term_start"], r["term_name"])
        if not out or out[-1]["_key"] != key:
            out.append({"_key": key, "name": r["term_name"], "name_en": r["term_name_en"] or r["term_name"], "courses": []})
        out[-1]["courses"].append({"name": r["course_name"], "name_en": r["course_name_en"] or r["course_name"], "credits": r["credits"],
                                   "score": r["score"], "letter": r["letter"], "passed": bool(r["passed"])})
    for t in out:
        t.pop("_key")
    return out


def transcript_ready(c, uid: int) -> bool:
    """A transcript is issued once the student's history before Zəka is reconciled; a student admitted in or after Zəka's
    first term has none to reconcile."""
    s = repo.student(c, uid)
    if not s:
        return False
    first = repo.first_term_start(c)
    return bool(s["history_reconciled_at"]) or bool(first and s["admission_year"] and int(s["admission_year"]) >= int(first[:4]))


def reconcile(c, user, sid: int) -> bool:
    s = repo.student(c, sid)
    if not s or s["role"] != "student":
        return False
    repo.set_reconciled(c, sid, iso(now()))
    audit(c, user["id"], "history_reconciled", "user", f"#{sid}")
    return True


DEBT_PAGE = 200


def debts(c, scope: str = "1=1", args: tuple = (), page: int | None = None) -> dict:
    """The final grades that did not pass: the academic debts, a page of them (``page``) or all (for the CSV)."""
    limit, offset = (DEBT_PAGE, (page - 1) * DEBT_PAGE) if page else (-1, 0)
    items = [{k: r[k] for k in ("user_id", "full_name", "student_no", "grp", "term_name", "course_code", "course_name", "credits", "score",
                                "letter")} for r in repo.failed_finals(c, scope, args, limit, offset)]
    total = repo.count_failed(c, scope, args) if page else len(items)
    return {"items": items, "total": total, "page": page or 1, "pages": max(1, -(-total // DEBT_PAGE)) if page else 1}


def write_cell(c, user, course_id: int, student_id: int, component: str, value: float | None, reason: str) -> tuple[str, object]:
    """One score from another module (an assignment, Task 22), by the table's rules: the student must be on the user's
    units, a new score is a draft, a change of a published one is logged with ``reason``."""
    status, value_ = save_grades(c, user, course_id, {"cells": [{"student_id": student_id, "component": component, "score": value}],
                                                      "reason": reason}, answer=False)
    if status == "cells":
        return "invalid", value_[0]["reason"]                # type: ignore[index]
    return status, value_


def put_exam_score(c, by: int, course_id: int, student_id: int, score: float, exam_id: int, attempt_no: int, reason: str,
                   source: str = "exam") -> None:
    """An exam's score into the journal's exam component (Task 30): published at once with its exam and attempt number;
    a different published score before it (an earlier exam, an appeal) goes to the grade journal with ``reason``."""
    co = repo.course(c, course_id)
    col = next(x for x in columns(c, co) if x["kind"] == "exam")
    cur = repo.grade_rows(c, course_id, student_id).get((student_id, col["key"]))
    at = iso(now())
    repo.put_exam_grade(c, student_id, course_id, col["key"], score, col["max"], by, at, exam_id, attempt_no, source)
    if cur and cur["status"] == "published" and cur["score"] != score:
        repo.add_change(c, student_id, course_id, col["key"], cur["score"], score, by, reason, at)
    refresh_finals(c, course_id, [student_id])


def put_exam_scores(c, by: int, course_id: int, scores: list[tuple[int, float]], exam_id: int, attempt_no: int, reason: str
                    ) -> tuple[list[int], list[dict]]:
    """A released exam's scores in one pass (Checkpoint D, AR-2): the course's rows read once, the finals refreshed once.
    A score of another exam stays when that exam's attempt is later (a retake over a main exam) or, for the same attempt
    number, when the dean's office has closed its statement (TM-6, CR-7); those come back as skipped with the reason."""
    co = repo.course(c, course_id)
    col = next(x for x in columns(c, co) if x["kind"] == "exam")
    current = repo.grade_rows(c, course_id)
    locked = repo.locked_students(c, course_id)
    at = iso(now())
    written, skipped = [], []
    for sid, score in scores:
        cur = current.get((sid, col["key"]))
        if cur and cur["exam_id"] and cur["exam_id"] != exam_id:
            theirs = cur["attempt_no"] or 1
            if theirs > attempt_no:
                skipped.append({"student_id": sid, "reason": "newer_exam", "exam_id": cur["exam_id"]})
                continue
            if theirs == attempt_no and sid in locked:
                skipped.append({"student_id": sid, "reason": "statement_closed", "exam_id": cur["exam_id"]})
                continue
        repo.put_exam_grade(c, sid, course_id, col["key"], score, col["max"], by, at, exam_id, attempt_no, "exam")
        if cur and cur["status"] == "published" and cur["score"] != score:
            repo.add_change(c, sid, course_id, col["key"], cur["score"], score, by, reason, at)
        written.append(sid)
    refresh_finals(c, course_id, written)
    return written, skipped


def exam_cell(c, course_id: int, student_id: int) -> dict | None:
    """The student's exam-component row (with exam_id and attempt_no), or None."""
    col = exam_column(c, course_id)
    return repo.grade_rows(c, course_id, student_id).get((student_id, col["key"]))


def exam_column(c, course_id: int) -> dict:
    """The course's exam component (key, max) by its grading scheme."""
    return next(x for x in columns(c, repo.course(c, course_id)) if x["kind"] == "exam")
