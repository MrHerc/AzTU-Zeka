"""SQL of clubs and channels (tasks/todo.md, Task 35)."""
from __future__ import annotations

from ...legacy.store import row, rows


def clubs_for(c, uid: int) -> list[dict]:
    """Approved clubs, and the ones this person leads in any status, with this person's membership."""
    return rows(c, "SELECT cl.id, cl.name, cl.description, cl.status, cl.leader_id, u.full_name AS leader, m.status AS my_status, m.role AS my_role, "
                   "(SELECT COUNT(*) FROM club_members x WHERE x.club_id=cl.id AND x.status='member') AS members "
                   "FROM clubs cl JOIN users u ON u.id=cl.leader_id LEFT JOIN club_members m ON m.club_id=cl.id AND m.user_id=? "
                   "WHERE cl.status='approved' OR cl.leader_id=? ORDER BY cl.name LIMIT 500", (uid, uid))


def club(c, cid: int):
    return row(c, "SELECT cl.*, u.full_name AS leader FROM clubs cl JOIN users u ON u.id=cl.leader_id WHERE cl.id=?", (cid,))


def pending(c) -> list[dict]:
    return rows(c, "SELECT cl.*, u.full_name AS leader, u.role AS leader_role FROM clubs cl JOIN users u ON u.id=cl.leader_id "
                   "WHERE cl.status='pending' ORDER BY cl.id")


def add_club(c, v: dict, leader: int, at: str) -> int:
    cid = c.execute("INSERT INTO clubs(name,description,leader_id,created_at) VALUES(?,?,?,?)", (v["name"], v["description"], leader, at)).lastrowid
    c.execute("INSERT INTO club_members(club_id,user_id,role,status,created_at) VALUES(?,?,'leader','member',?)", (cid, leader, at))
    return cid


def decide(c, cid: int, status: str, by: int, note: str | None, at: str):
    c.execute("UPDATE clubs SET status=?, decided_by=?, decided_at=?, note=? WHERE id=?", (status, by, at, note, cid))


def add_channel(c, cid: int, name: str, kind: str, at: str) -> int:
    return c.execute("INSERT INTO club_channels(club_id,name,kind,created_at) VALUES(?,?,?,?)", (cid, name, kind, at)).lastrowid


def channels(c, cid: int) -> list[dict]:
    return rows(c, "SELECT id, name, kind FROM club_channels WHERE club_id=? ORDER BY id", (cid,))


def channel(c, chid: int):
    return row(c, "SELECT * FROM club_channels WHERE id=?", (chid,))


def membership(c, cid: int, uid: int):
    return row(c, "SELECT * FROM club_members WHERE club_id=? AND user_id=?", (cid, uid))


def members(c, cid: int) -> list[dict]:
    return rows(c, "SELECT m.user_id, m.role, m.status, m.muted_until, m.created_at, u.full_name FROM club_members m "
                   "JOIN users u ON u.id=m.user_id WHERE m.club_id=? ORDER BY m.status, u.full_name", (cid,))


def request_join(c, cid: int, uid: int, at: str):
    c.execute("INSERT INTO club_members(club_id,user_id,created_at) VALUES(?,?,?)", (cid, uid, at))


def set_member(c, cid: int, uid: int, **fields):
    sets = ", ".join(f"{k}=?" for k in fields)              # keys are written in code: status, muted_until, conduct_at
    c.execute(f"UPDATE club_members SET {sets} WHERE club_id=? AND user_id=?", (*fields.values(), cid, uid))  # nosec B608


def rejoin(c, cid: int, uid: int, at: str):
    """A former member asks again: the row, and a mute on it, stays (Checkpoint E, SEC-E5)."""
    c.execute("UPDATE club_members SET status='requested', created_at=? WHERE club_id=? AND user_id=? AND status='left'", (at, cid, uid))


def leave(c, cid: int, uid: int) -> bool:
    """A member or a requester leaves: the row stays as ``left`` with its mute; a removal is never undone (SEC-E5)."""
    return c.execute("UPDATE club_members SET status='left' WHERE club_id=? AND user_id=? AND role<>'leader' AND status IN ('member','requested')",
                     (cid, uid)).rowcount > 0


def messages(c, chid: int, since_id: int, limit: int, with_hidden: bool) -> list[dict]:
    return rows(c, "SELECT m.id, m.author_id, m.text, m.hidden, m.created_at, u.full_name AS author FROM club_messages m "
                   "JOIN users u ON u.id=m.author_id WHERE m.channel_id=? AND m.id>? AND (?=1 OR m.hidden=0) ORDER BY m.id LIMIT ?",
                (chid, since_id, int(with_hidden), limit))


def last_messages(c, chid: int, limit: int, with_hidden: bool) -> list[dict]:
    out = rows(c, "SELECT m.id, m.author_id, m.text, m.hidden, m.created_at, u.full_name AS author FROM club_messages m "
                  "JOIN users u ON u.id=m.author_id WHERE m.channel_id=? AND (?=1 OR m.hidden=0) ORDER BY m.id DESC LIMIT ?",
               (chid, int(with_hidden), limit))
    return out[::-1]


def add_message(c, chid: int, uid: int, text: str, at: str) -> int:
    return c.execute("INSERT INTO club_messages(channel_id,author_id,text,created_at) VALUES(?,?,?,?)", (chid, uid, text, at)).lastrowid


def message(c, mid: int):
    return row(c, "SELECT m.*, ch.club_id FROM club_messages m JOIN club_channels ch ON ch.id=m.channel_id WHERE m.id=?", (mid,))


def hide_message(c, mid: int):
    c.execute("UPDATE club_messages SET hidden=1 WHERE id=?", (mid,))


def hidden_ids(c, chid: int, window: int) -> list[int]:
    """The hidden messages among the channel's last ``window``: a member's open page drops them (SF-E8)."""
    return [r["id"] for r in rows(c, "SELECT id FROM (SELECT id, hidden FROM club_messages WHERE channel_id=? ORDER BY id DESC LIMIT ?) "
                                     "WHERE hidden=1", (chid, window))]


def open_report(c, mid: int, uid: int):
    return row(c, "SELECT id FROM club_reports WHERE message_id=? AND reporter_id=? AND resolved_at IS NULL", (mid, uid))


def add_report(c, mid: int, uid: int, reason: str, at: str) -> int:
    return c.execute("INSERT INTO club_reports(message_id,reporter_id,reason,created_at) VALUES(?,?,?,?)", (mid, uid, reason, at)).lastrowid


def open_reports(c, club_ids: list[int] | None, not_author: int | None = None) -> list[dict]:
    """Open reports with the message, its author and club; ``club_ids`` None: all clubs; ``not_author``: leave out the
    reports on this person's own messages (a leader's own go to the office, TM-E4)."""
    sql = ("SELECT p.id, p.message_id, p.reason, p.created_at, m.text, m.author_id, a.full_name AS author, ch.club_id, cl.name AS club, "
           "r.full_name AS reporter FROM club_reports p JOIN club_messages m ON m.id=p.message_id JOIN club_channels ch ON ch.id=m.channel_id "
           "JOIN clubs cl ON cl.id=ch.club_id JOIN users a ON a.id=m.author_id JOIN users r ON r.id=p.reporter_id WHERE p.resolved_at IS NULL")
    if club_ids is None:
        return rows(c, sql + " ORDER BY p.id LIMIT 200")
    if not club_ids:
        return []
    return rows(c, sql + f" AND ch.club_id IN ({','.join('?' * len(club_ids))}) AND m.author_id<>? ORDER BY p.id LIMIT 200",  # nosec B608
                (*club_ids, not_author or 0))


def report(c, pid: int):
    return row(c, "SELECT * FROM club_reports WHERE id=?", (pid,))


def resolve_reports(c, mid: int, by: int, outcome: str, at: str):
    c.execute("UPDATE club_reports SET resolved_at=?, resolved_by=?, outcome=? WHERE message_id=? AND resolved_at IS NULL", (at, by, outcome, mid))


def led_clubs(c, uid: int) -> list[int]:
    return [r["club_id"] for r in rows(c, "SELECT club_id FROM club_members WHERE user_id=? AND role='leader' AND status='member'", (uid,))]


def purge_messages(c, before: str) -> int:
    """Messages past the retention period, with their reports."""
    c.execute("DELETE FROM club_reports WHERE message_id IN (SELECT id FROM club_messages WHERE created_at<?)", (before,))
    return c.execute("DELETE FROM club_messages WHERE created_at<?", (before,)).rowcount
