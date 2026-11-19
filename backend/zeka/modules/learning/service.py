"""Assignments: set by a course's teacher, submitted by its students, graded into the journal (tasks/todo.md, Task 22)."""
from __future__ import annotations

from ...core.web import an_id
from ...core.i18n import E
from ...legacy.store import audit, iso, now
from ..journal import service as journal
from . import domain, repo


def _components(c, co: dict) -> dict[str, float]:
    """The components a score may count toward: every column of the grade table but attendance and the exam."""
    return {x["key"]: x["max"] for x in journal.columns(c, co) if x["kind"] == "component"}


def may_teach(c, user, course_id: int) -> bool:
    return user["role"] in ("teacher", "dept_head") and repo.teaches(c, user["id"], course_id)


def enrolled(c, user, course_id: int) -> bool:
    """An active student enrolled in the course today."""
    return user["role"] == "student" and repo.enrolled(c, user["id"], course_id, now().date().isoformat())


def list_for(c, user, course_id: int) -> list[dict] | None:
    """A teacher's view (with counts) or a student's (with their own submission); None for anyone else."""
    if may_teach(c, user, course_id):
        return repo.of_course(c, course_id)
    if user["role"] == "student" and repo.enrolled(c, user["id"], course_id, now().date().isoformat()):
        out = []
        for a in repo.of_course(c, course_id):
            s = repo.submission_of(c, a["id"], user["id"])
            out.append({**{k: a[k] for k in ("id", "title", "body", "due_at", "max_score", "component", "late_rule")},
                        "submission": {k: s[k] for k in ("id", "submitted_at", "late", "score", "feedback", "file_id", "text")} if s else None})
        return out
    return None


def create(c, user, course_id: int, body) -> tuple[str, object]:
    co = repo.course(c, course_id)
    if not co or not may_teach(c, user, course_id):
        return "missing", None
    values, problem = domain.assignment_input(body, _components(c, co))
    if problem:
        return "invalid", problem
    at = iso(now())
    aid = repo.insert(c, course_id, values, user["id"], at)
    audit(c, user["id"], "assignment_create", "course", f"#{course_id} · {values['title']}")
    return "ok", repo.assignment(c, aid)


def submit(c, user, aid: int, body) -> tuple[str, object]:
    """('ok', submission) | ('missing', None) | ('invalid', reason) | ('late', reason). A new submission replaces the
    previous one until it is graded."""
    a = repo.assignment(c, aid)
    at = iso(now())
    if not a or user["role"] != "student" or not repo.enrolled(c, user["id"], a["course_id"], at[:10]):
        return "missing", None
    text = str(body.get("text") or "").strip()[:20000] or None
    fid = body.get("file_id")
    if fid is not None:
        f = repo.file_owner(c, fid) if an_id(fid) else None
        if not f or f["owner_id"] != user["id"]:
            return "invalid", E("Fayl tapılmadı")
    if not text and fid is None:
        return "invalid", E("Mətn yazın və ya fayl əlavə edin")
    prev = repo.submission_of(c, aid, user["id"])
    if prev and prev["score"] is not None:
        return "invalid", E("Göndəriş artıq qiymətləndirilib")
    late = domain.is_late(at, a["due_at"])
    if late and a["late_rule"] == "refuse":
        return "late", E("Son tarix keçib: bu tapşırıq gecikmiş göndərişi qəbul etmir")
    if not repo.save_submission(c, aid, user["id"], text, fid, at, late):
        return "invalid", E("Göndəriş artıq qiymətləndirilib")        # graded between the check above and this write
    return "ok", repo.submission_of(c, aid, user["id"])


def submissions(c, user, aid: int) -> list[dict] | None:
    a = repo.assignment(c, aid)
    return repo.submissions_of(c, aid) if a and may_teach(c, user, a["course_id"]) else None


def submission(c, user, sid: int):
    """Only its student and the course's teachers read a submission."""
    s = repo.submission(c, sid)
    if not s or not (s["student_id"] == user["id"] or may_teach(c, user, s["course_id"])):
        return None
    return s


def grade(c, user, sid: int, body) -> tuple[str, object]:
    """Score and feedback; the student's total of the component's graded assignments goes to the grade journal."""
    s = repo.submission(c, sid)
    if not s or not may_teach(c, user, s["course_id"]):
        return "missing", None
    v = body.get("score")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= s["max_score"]:
        return "invalid", E("Bal 0 ilə {max} arasında olmalıdır", max=s["max_score"])
    feedback = str(body.get("feedback") or "").strip()[:5000] or None
    co = repo.course(c, s["course_id"])
    comps = _components(c, co)
    if s["component"] not in comps:                     # the grading scheme changed after the assignment was set
        return "invalid", E("Komponent fənnin sxemində yoxdur: {x}", x=s["component"])
    at = iso(now())
    repo.grade(c, sid, round(float(v), 2), feedback, user["id"], at)
    total = domain.component_total(repo.graded_scores(c, s["course_id"], s["student_id"], s["component"]), comps[s["component"]])
    status, problem = journal.write_cell(c, user, s["course_id"], s["student_id"], s["component"], total, f"Tapşırıq: {s['title']}")
    if status != "ok":
        return status, problem
    audit(c, user["id"], "assignment_graded", "submission", f"#{sid} · {v}")
    return "ok", repo.submission(c, sid)


def may_read_file(c, user, file_id: int) -> bool:
    """A teacher of the course whose submission holds the file reads it (Task 22)."""
    course_id = repo.file_course(c, file_id)
    return course_id is not None and may_teach(c, user, course_id)
