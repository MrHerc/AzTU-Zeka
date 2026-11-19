"""Clubs and channels (tasks/todo.md, Task 35).

Who sees a channel: the club's members, nobody else (403 on every channel route). Who writes: a member who accepted
the code of conduct and is not muted; in an announcement channel only the leader. Who moderates: community.moderate
(every club) and a club's leader (inside the club); each step is audited. A dean's office approves a club.
"""
from __future__ import annotations

from datetime import timedelta

from ...core import perms
from ...core.i18n import S, T3
from ...core.security import LIMITS
from ...legacy.store import audit, iso, notify, now, setting
from . import domain, repo

WRITERS = ("student", "teacher", "dept_head")


def _member(c, uid: int, cid: int):
    m = repo.membership(c, cid, uid)
    return m if m and m["status"] == "member" else None


def _moderates(c, user, cid: int) -> bool:
    if perms.has(user["role"], "community.moderate"):
        return True
    m = _member(c, user["id"], cid)
    return bool(m and m["role"] == "leader")


def clubs(c, user) -> list[dict]:
    return repo.clubs_for(c, user["id"])


def propose(c, user, body) -> tuple[str, object]:
    if user["role"] not in WRITERS:
        return "forbidden", T3("Klubu tələbə və ya müəllim təklif edir")
    v, problem = domain.club_input(body)
    if problem:
        return "invalid", problem
    if not LIMITS["club_ask"].hit(f"u{user['id']}"):
        return "limited", T3("Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    cid = repo.add_club(c, v, user["id"], iso(now()))
    audit(c, user["id"], "club_propose", "club", f"#{cid} {v['name'][:60]}")
    return "ok", repo.club(c, cid)


def pending(c) -> list[dict]:
    return repo.pending(c)


def decide(c, user, cid: int, body) -> tuple[str, object]:
    cl = repo.club(c, cid)
    if not cl or cl["status"] != "pending":
        return "missing", None
    approve = body.get("approve")
    if not isinstance(approve, bool):
        return "invalid", T3("Qərar: təsdiq və ya rədd")
    note = " ".join(body.text("note", 400).split())[:300] or None
    at = iso(now())
    repo.decide(c, cid, "approved" if approve else "rejected", user["id"], note, at)
    if approve:
        for name, kind in domain.DEFAULT_CHANNELS:
            repo.add_channel(c, cid, S(name, "az"), kind, at)
    notify(c, cl["leader_id"], "event", T3("Klub təsdiqləndi: {name}", name=cl["name"]) if approve else T3("Klub rədd edildi: {name}", name=cl["name"]),
           note or "", f"/clubs/{cid}")
    audit(c, user["id"], "club_decide", "club", f"#{cid} {'approved' if approve else 'rejected'}")
    return "ok", repo.club(c, cid)


def club(c, user, cid: int) -> dict | None:
    cl = repo.club(c, cid)
    if not cl or (cl["status"] != "approved" and cl["leader_id"] != user["id"] and not perms.has(user["role"], "clubs.approve")):
        return None
    m = repo.membership(c, cid, user["id"])
    member = bool(m and m["status"] == "member")
    return {"club": {k: cl[k] for k in ("id", "name", "description", "status", "leader_id", "leader", "note")},
            "membership": {k: m[k] for k in ("role", "status", "muted_until", "conduct_at")} if m else None,
            "channels": repo.channels(c, cid) if member else [], "moderates": _moderates(c, user, cid)}


def join(c, user, cid: int) -> tuple[str, object]:
    cl = repo.club(c, cid)
    if not cl or cl["status"] != "approved" or user["role"] not in WRITERS:
        return "missing", None
    m = repo.membership(c, cid, user["id"])
    if m and m["status"] == "removed":
        return "forbidden", T3("Siz bu klubdan çıxarılmısınız")
    if m and m["status"] != "left":
        return "ok", club(c, user, cid)
    if not LIMITS["club_ask"].hit(f"u{user['id']}"):           # a leave and join loop does not flood the leader (TM-E3)
        return "limited", T3("Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    (repo.rejoin if m else repo.request_join)(c, cid, user["id"], iso(now()))
    notify(c, cl["leader_id"], "event", T3("Kluba üzvlük sorğusu: {name}", name=cl["name"]), user["full_name"], f"/clubs/{cid}")
    return "ok", club(c, user, cid)


def leave(c, user, cid: int) -> tuple[str, object]:
    if repo.leave(c, cid, user["id"]):
        audit(c, user["id"], "club_leave", "club", f"#{cid}")
    return "ok", {"ok": True}


def conduct(c, user, cid: int) -> tuple[str, object]:
    if not _member(c, user["id"], cid):
        return "forbidden", T3("Yalnız klubun üzvləri üçün")
    repo.set_member(c, cid, user["id"], conduct_at=iso(now()))
    return "ok", club(c, user, cid)


def members(c, user, cid: int) -> tuple[str, object]:
    if not (_member(c, user["id"], cid) or perms.has(user["role"], "community.moderate")):
        return "forbidden", T3("Yalnız klubun üzvləri üçün")
    out = repo.members(c, cid)
    if not _moderates(c, user, cid):                            # members see the members, not requests, removals or mutes
        out = [{"user_id": m["user_id"], "full_name": m["full_name"], "role": m["role"]} for m in out if m["status"] == "member"]
    return "ok", out


def manage_member(c, user, cid: int, uid: int, action: str, body) -> tuple[str, object]:
    """approve (the leader), remove or mute (the leader, community.moderate); never the leader themself."""
    if not _moderates(c, user, cid):
        return "forbidden", T3("Bu əməliyyat yalnız klubun rəhbəri və moderatorlar üçündür")
    m = repo.membership(c, cid, uid)
    if not m or m["role"] == "leader":
        return "missing", None
    until = None
    if action == "approve":
        if m["status"] != "requested":
            return "invalid", T3("Bu sorğu artıq baxılıb")
        repo.set_member(c, cid, uid, status="member")
        notify(c, uid, "event", T3("Kluba qəbul olundunuz: {name}", name=repo.club(c, cid)["name"]), "", f"/clubs/{cid}")
    elif action == "remove":
        repo.set_member(c, cid, uid, status="removed")
    elif action == "mute":
        v, problem = domain.mute_input(body)
        if problem:
            return "invalid", problem
        until = iso(now() + timedelta(minutes=v["minutes"]))
        repo.set_member(c, cid, uid, muted_until=until)
        notify(c, uid, "event", T3("Klubda yazmağınız {until} qədər dayandırılıb", until=until.replace("T", " ")[:16]), v["reason"], f"/clubs/{cid}")
    else:
        return "missing", None
    audit(c, user["id"], f"club_{action}", "club", f"#{cid} user #{uid}" + (f" until {until}" if action == "mute" else ""))
    return "ok", repo.members(c, cid)


def _channel_for(c, user, chid: int):
    """(channel, membership) when the user is a member of the channel's club; else None (the route answers 403)."""
    ch = repo.channel(c, chid)
    m = _member(c, user["id"], ch["club_id"]) if ch else None
    return (ch, m) if m else None


def messages(c, user, chid: int, since_id: int) -> tuple[str, object]:
    found = _channel_for(c, user, chid)
    if not found:
        return "forbidden", T3("Yalnız klubun üzvləri üçün")
    ch, _ = found
    mod = _moderates(c, user, ch["club_id"])
    page = (repo.messages(c, chid, since_id, domain.PAGE, mod) if since_id else repo.last_messages(c, chid, domain.PAGE, mod))
    hidden = [] if mod or not since_id else repo.hidden_ids(c, chid, domain.PAGE * 4)
    return "ok", {"channel": ch, "messages": page, "moderates": mod, "hidden": hidden}


def post(c, user, chid: int, body) -> tuple[str, object]:
    found = _channel_for(c, user, chid)
    if not found:
        return "forbidden", T3("Yalnız klubun üzvləri üçün")
    ch, m = found
    if ch["kind"] == "announce" and m["role"] != "leader":
        return "forbidden", T3("Elanlar kanalına yalnız klubun rəhbəri yazır")
    if not m["conduct_at"]:
        return "conduct", T3("Əvvəlcə davranış qaydalarını qəbul edin")
    if m["muted_until"] and m["muted_until"] > iso(now()):
        return "forbidden", T3("Yazmağınız {until} qədər dayandırılıb", until=m["muted_until"].replace("T", " ")[:16])
    text, problem = domain.message_input(body)
    if problem:
        return "invalid", problem
    if not LIMITS["club_post"].hit(f"u{user['id']}"):
        return "limited", T3("Çox sayda mesaj. Bir az sonra yenidən yazın.")
    mid = repo.add_message(c, chid, user["id"], text, iso(now()))
    return "ok", {"id": mid}


def report(c, user, mid: int, body) -> tuple[str, object]:
    msg = repo.message(c, mid)
    if not msg or not _member(c, user["id"], msg["club_id"]):
        return "forbidden", T3("Yalnız klubun üzvləri üçün")
    reason, problem = domain.reason_input(body)
    if problem:
        return "invalid", problem
    same = repo.open_report(c, mid, user["id"])
    if same:                                                    # one open report per person and message
        return "ok", {"id": same["id"]}
    if not LIMITS["club_ask"].hit(f"u{user['id']}"):
        return "limited", T3("Çox sayda sorğu. Bir az sonra yenidən cəhd edin.")
    pid = repo.add_report(c, mid, user["id"], reason, iso(now()))
    audit(c, user["id"], "club_report", "club_message", f"#{mid} club #{msg['club_id']}")
    return "ok", {"id": pid}


def queue(c, user) -> tuple[str, object]:
    if perms.has(user["role"], "community.moderate"):
        return "ok", repo.open_reports(c, None)
    led = repo.led_clubs(c, user["id"])
    if not led:
        return "forbidden", T3("Bu əməliyyat yalnız klubun rəhbəri və moderatorlar üçündür")
    # a leader neither learns who reported nor sees the reports on their own messages: those stay for the office (TM-E4)
    return "ok", [{k: v for k, v in r.items() if k != "reporter"} for r in repo.open_reports(c, led, not_author=user["id"])]


def hide(c, user, mid: int, outcome: str = "hide") -> tuple[str, object]:
    msg = repo.message(c, mid)
    if not msg:
        return "missing", None
    if not _moderates(c, user, msg["club_id"]):
        return "forbidden", T3("Bu əməliyyat yalnız klubun rəhbəri və moderatorlar üçündür")
    if outcome == "keep" and msg["author_id"] == user["id"] and not perms.has(user["role"], "community.moderate"):
        return "forbidden", T3("Öz mesajınız haqqında şikayətə moderator baxır")
    if outcome == "hide":
        repo.hide_message(c, mid)
    repo.resolve_reports(c, mid, user["id"], outcome, iso(now()))
    audit(c, user["id"], f"club_message_{outcome}", "club_message", f"#{mid} club #{msg['club_id']}")
    return "ok", {"ok": True}


def resolve(c, user, pid: int, body) -> tuple[str, object]:
    p = repo.report(c, pid)
    if not p or p["resolved_at"]:
        return "missing", None
    action = body.text("action", 10)
    if action not in ("hide", "keep"):
        return "invalid", T3("Əməliyyat: gizlət və ya saxla")
    return hide(c, user, p["message_id"], action)


def purge(c) -> int:
    """The periodic purge: messages older than the retention period (``limits.community_retention_days``, 180)."""
    days = (setting(c, "limits") or {}).get("community_retention_days")
    if not isinstance(days, int) or isinstance(days, bool) or days < 1:     # a bad setting keeps the default (SF-E13)
        days = domain.RETENTION_DAYS
    return repo.purge_messages(c, iso(now() - timedelta(days=days)))
