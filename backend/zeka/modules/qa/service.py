"""The course forum (tasks/todo.md, Task 33).

Who reads a course's topics: its enrolled students and its teachers; nobody else (a moderator sees reported content in
the queue). An anonymous author is hidden from students and shown to the course's teachers and to qa.moderate. The AI
draft is the teacher's alone until the teacher publishes it as a reply. A topic with an accepted answer can move to
the course's FAQ: a section of the material "Fənnin FAQ-ı" that the tutor searches and cites.
"""
from __future__ import annotations

from ...core import perms
from ...core.i18n import S, T3
from ...legacy.store import audit, iso, log_index, notify, now
from ..learning import repo as learning
from . import domain, repo


def _today() -> str:
    return now().date().isoformat()


def teaches(c, user, cid: int) -> bool:
    return user["role"] in ("teacher", "dept_head") and learning.teaches(c, user["id"], cid)


def may_read(c, user, cid: int) -> bool:
    return teaches(c, user, cid) or (user["role"] == "student" and learning.enrolled(c, user["id"], cid, _today()))


def sees_authors(c, user, cid: int) -> bool:
    return teaches(c, user, cid) or perms.has(user["role"], "qa.moderate")


def _author(x: dict, user, show: bool) -> dict:
    anon = bool(x.get("anonymous"))
    mine = x.get("student_id", x.get("author_id")) == user["id"]
    name = x["author"] if (show or mine or not anon) else T3(domain.ANONYMOUS)
    return {"author": name, "anonymous": anon, "mine": mine, "by_teacher": x["author_role"] in ("teacher", "dept_head")}


def topics(c, user, cid: int) -> list[dict] | None:
    if not may_read(c, user, cid):
        return None
    show, teacher = sees_authors(c, user, cid), teaches(c, user, cid)
    out = []
    for t in repo.topics(c, cid):
        if t["hidden"] and not teacher:
            continue
        out.append({k: t[k] for k in ("id", "title", "tag", "status", "replies", "created_at", "hidden")} | {"faq": bool(t["faq_chunk_id"])}
                   | _author(t, user, show))
    return out


def topic(c, user, tid: int) -> dict | None:
    t = repo.topic(c, tid)
    if not t or not may_read(c, user, t["course_id"]):
        return None
    teacher = teaches(c, user, t["course_id"])
    if t["hidden"] and not teacher:
        return None
    show = sees_authors(c, user, t["course_id"])
    out = {k: t[k] for k in ("id", "course_id", "title", "tag", "status", "created_at", "hidden")} | {"text": t["question"], "faq": bool(t["faq_chunk_id"])}
    out |= _author(t, user, show)
    out["replies"] = [{k: r[k] for k in ("id", "text", "accepted", "hidden", "created_at")} | _author(r, user, True)
                      for r in repo.replies(c, tid) if teacher or not r["hidden"]]
    out["can_moderate_course"] = teacher
    if teacher:                                                 # the AI draft is the teacher's alone
        out["ai_draft"] = t["ai_draft"]
    return out


def create(c, user, cid: int, body) -> tuple[str, object]:
    if not may_read(c, user, cid):
        return "missing", None
    v, problem = domain.topic_input(body)
    if problem:
        return "invalid", problem
    tid = repo.add_topic(c, cid, user["id"], v, iso(now()))
    co = repo.course(c, cid)
    if co["teacher_id"] and co["teacher_id"] != user["id"]:
        notify(c, co["teacher_id"], "question", T3("Fənn forumunda yeni sual"), T3("{course}: {text}", course=co["name"], text=v["title"][:90]),
               f"/qa/{cid}/{tid}")
    audit(c, user["id"], "qa_topic", "course", f"{co['code']} #{tid}")
    return "ok", topic(c, user, tid)


def reply(c, user, tid: int, body) -> tuple[str, object]:
    t = repo.topic(c, tid)
    if not t or not may_read(c, user, t["course_id"]) or (t["hidden"] and not teaches(c, user, t["course_id"])):
        return "missing", None
    text, problem = domain.reply_input(body)
    if problem:
        return "invalid", problem
    repo.add_reply(c, tid, user["id"], text, iso(now()))
    if teaches(c, user, t["course_id"]) and t["student_id"] != user["id"]:
        notify(c, t["student_id"], "answer", T3("Müəllim sualınıza cavab yazdı"), t["title"][:90], f"/qa/{t['course_id']}/{tid}")
    return "ok", topic(c, user, tid)


def accept(c, user, rid: int) -> tuple[str, object]:
    r = repo.reply(c, rid)
    t = repo.topic(c, r["topic_id"]) if r else None
    if not t or not teaches(c, user, t["course_id"]):
        return "missing", None
    if r["hidden"]:
        return "invalid", T3("Gizlədilmiş cavab qəbul olunmur")
    repo.accept(c, t["id"], rid, r["text"], iso(now()))
    if t["student_id"] != user["id"]:
        notify(c, t["student_id"], "answer", T3("Sualınıza cavab təsdiqləndi"), t["title"][:90], f"/qa/{t['course_id']}/{t['id']}")
    audit(c, user["id"], "qa_accept", "topic", f"#{t['id']} reply #{rid}")
    if t["faq_chunk_id"]:                                       # the FAQ follows the accepted answer
        _faq_off(c, t)
        _faq_on(c, user, repo.topic(c, t["id"]), r["text"])
    return "ok", topic(c, user, t["id"])


def draft(c, user, tid: int, lang: str) -> tuple[str, object]:
    """An answer the AI writes from the course's materials, cited, kept for the teacher only."""
    t = repo.topic(c, tid)
    if not t or not teaches(c, user, t["course_id"]):
        return "missing", None
    from ...legacy import engine, tutor                        # here: legacy imports this module's routes
    from ...legacy.common import search_chunks
    question, _ = engine.mask_pii(f"{t['title']}. {t['question']}")
    hits = search_chunks(t["course_id"], question)
    result = tutor.compose_tutor("explain", question, hits, [], repo.course(c, t["course_id"]), lang)
    sources = [f"[{i}] {h['material']} · {h['heading']}" for i, h in enumerate((h for h in hits if h["id"] in result["cites"]), 1)]
    text = result["text"] + ("\n\n" + "\n".join(sources) if sources else "")
    repo.set_draft(c, tid, text)
    return "ok", {"ai_draft": text, "no_source": not hits}


def _faq_on(c, user, t: dict, answer: str):
    at = iso(now())
    mid = repo.faq_material(c, t["course_id"], S(domain.FAQ_TITLE, "az"), user["id"], at)
    chunk = repo.add_faq_chunk(c, mid, t["course_id"], t["title"], domain.faq_text({"text": t["question"]}, answer))
    repo.set_faq(c, t["id"], chunk)
    repo.refresh_faq_material(c, mid)
    log_index(c, "chunks", [chunk])                             # every worker's tutor finds it on its next request


def _faq_off(c, t: dict):
    repo.drop_faq_chunk(c, t["faq_chunk_id"])
    repo.set_faq(c, t["id"], None)
    m = repo.faq_material(c, t["course_id"], "", 0, "")
    repo.refresh_faq_material(c, m)
    log_index(c, "chunks", [t["faq_chunk_id"]], "delete")


def faq(c, user, tid: int, on: bool) -> tuple[str, object]:
    t = repo.topic(c, tid)
    if not t or not teaches(c, user, t["course_id"]):
        return "missing", None
    if on and not t["faq_chunk_id"]:
        a = repo.accepted(c, tid)
        if not a or t["hidden"]:
            return "invalid", T3("FAQ-a yalnız təsdiqlənmiş cavabı olan mövzu keçir")
        _faq_on(c, user, t, a["text"])
    elif not on and t["faq_chunk_id"]:
        _faq_off(c, t)
    audit(c, user["id"], "qa_faq", "topic", f"#{tid} {'on' if on else 'off'}")
    return "ok", topic(c, user, tid)


def report(c, user, body) -> tuple[str, object]:
    tid = body.integer("topic_id", lo=1)
    rid = body.integer("reply_id", lo=1)
    t = repo.topic(c, tid) if tid else None
    r = repo.reply(c, rid) if rid else None
    if not t or not may_read(c, user, t["course_id"]) or (rid and (not r or r["topic_id"] != tid)):
        return "missing", None
    reason, problem = domain.report_input(body)
    if problem:
        return "invalid", problem
    pid = repo.add_report(c, tid, rid, user["id"], reason, iso(now()))
    audit(c, user["id"], "qa_report", "topic", f"#{tid}" + (f" reply #{rid}" if rid else ""))
    return "ok", {"id": pid}


def queue(c) -> list[dict]:
    return repo.open_reports(c)


def resolve(c, user, pid: int, body) -> tuple[str, object]:
    """hide: the reported topic or reply is hidden from students; keep: the report is closed. Audited either way."""
    p = repo.report(c, pid)
    if not p or p["resolved_at"]:
        return "missing", None
    action = body.text("action", 10)
    if action not in ("hide", "keep"):
        return "invalid", T3("Əməliyyat: gizlət və ya saxla")
    if action == "hide":
        repo.set_hidden(c, "reply" if p["reply_id"] else "topic", p["reply_id"] or p["topic_id"], True)
        t = repo.topic(c, p["topic_id"])
        if t["faq_chunk_id"] and (not p["reply_id"] or (repo.reply(c, p["reply_id"]) or {}).get("accepted")):
            _faq_off(c, t)                                      # hidden content leaves the FAQ and the tutor
    repo.resolve(c, pid, user["id"], action, iso(now()))
    audit(c, user["id"], "qa_moderate", "report", f"#{pid} {action} topic #{p['topic_id']}" + (f" reply #{p['reply_id']}" if p["reply_id"] else ""))
    return "ok", {"ok": True}
