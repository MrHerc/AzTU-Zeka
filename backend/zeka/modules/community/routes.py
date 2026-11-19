"""HTTP routes of clubs and channels (tasks/todo.md, Task 35). A channel route answers 403 to anyone who is not a
member of the channel's club (tests/security/test_community_access.py)."""
from __future__ import annotations

from ...core.i18n import S_
from ...core.web import HTTPError
from ...legacy.common import R
from . import service

CODES = {"missing": 404, "forbidden": 403, "invalid": 400, "conduct": 409, "limited": 429}
NO_CLUB = S_("Klub tapılmadı")


def _answer(status, value, missing=NO_CLUB):
    if status == "ok":
        return value
    raise HTTPError(CODES[status], missing if status == "missing" else value)


@R("GET", "/api/clubs")
def clubs(req):
    return service.clubs(req.db, req.user)


@R("POST", "/api/clubs")
def propose(req):
    return _answer(*service.propose(req.db, req.user, req.json()))


@R("GET", "/api/clubs/pending", perm="clubs.approve")
def pending(req):
    return service.pending(req.db)


@R("POST", "/api/clubs/{id:int}/decide", perm="clubs.approve")
def decide(req):
    return _answer(*service.decide(req.db, req.user, req.params["id"], req.json()))


@R("GET", "/api/clubs/{id:int}")
def club(req):
    out = service.club(req.db, req.user, req.params["id"])
    return _answer("missing" if out is None else "ok", out)


@R("POST", "/api/clubs/{id:int}/join")
def join(req):
    return _answer(*service.join(req.db, req.user, req.params["id"]))


@R("POST", "/api/clubs/{id:int}/leave")
def leave(req):
    return _answer(*service.leave(req.db, req.user, req.params["id"]))


@R("POST", "/api/clubs/{id:int}/conduct")
def conduct(req):
    return _answer(*service.conduct(req.db, req.user, req.params["id"]))


@R("GET", "/api/clubs/{id:int}/members")
def members(req):
    return _answer(*service.members(req.db, req.user, req.params["id"]))


@R("POST", "/api/clubs/{id:int}/members/{uid:int}/{action}")
def manage_member(req):
    return _answer(*service.manage_member(req.db, req.user, req.params["id"], req.params["uid"], str(req.params["action"]), req.json()))


@R("GET", "/api/channels/{id:int}/messages")
def messages(req):
    return _answer(*service.messages(req.db, req.user, req.params["id"], req.qint("since_id", 0, lo=0)))


@R("POST", "/api/channels/{id:int}/messages")
def post(req):
    return _answer(*service.post(req.db, req.user, req.params["id"], req.json()))


@R("POST", "/api/club-messages/{id:int}/report")
def report(req):
    return _answer(*service.report(req.db, req.user, req.params["id"], req.json()), S_("Mesaj tapılmadı"))


@R("POST", "/api/club-messages/{id:int}/hide")
def hide(req):
    return _answer(*service.hide(req.db, req.user, req.params["id"]), S_("Mesaj tapılmadı"))


@R("GET", "/api/community/reports")
def queue(req):
    return _answer(*service.queue(req.db, req.user))


@R("POST", "/api/community/reports/{id:int}/resolve")
def resolve(req):
    return _answer(*service.resolve(req.db, req.user, req.params["id"], req.json()), S_("Şikayət tapılmadı"))
