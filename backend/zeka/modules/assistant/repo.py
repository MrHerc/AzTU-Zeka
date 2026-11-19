"""SQL of the campus assistant's knowledge base (tasks/todo.md, Task 32)."""
from __future__ import annotations

from ...legacy.store import row, rows

FIELDS = ("heading", "text", "request", "action_label", "source", "source_ref", "review_at", "status")


def articles(c) -> list[dict]:
    return rows(c, "SELECT id, heading, request, source, source_ref, review_at, status, version, updated_at FROM campus_kb ORDER BY heading")


def article(c, kid: int):
    return row(c, "SELECT * FROM campus_kb WHERE id=?", (kid,))


def versions(c, kid: int) -> list[dict]:
    return rows(c, "SELECT v.version, v.heading, v.status, v.changed_at, u.full_name AS changed_by FROM campus_kb_versions v "
                   "LEFT JOIN users u ON u.id=v.changed_by WHERE v.kb_id=? ORDER BY v.version DESC", (kid,))


def has_versions(c, kid: int) -> bool:
    return bool(row(c, "SELECT 1 FROM campus_kb_versions WHERE kb_id=? LIMIT 1", (kid,)))


def add_version(c, a: dict, by: int | None, at: str):
    c.execute("INSERT INTO campus_kb_versions(kb_id,version,heading,text,request,action_label,source,source_ref,review_at,status,changed_by,changed_at) "
              "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (a["id"], a["version"], *(a[k] for k in FIELDS), by, at))


def insert(c, v: dict, by: int, at: str) -> int:
    return c.execute("INSERT INTO campus_kb(heading,text,request,action_label,source,source_ref,review_at,status,version,updated_at,updated_by) "
                     "VALUES(?,?,?,?,?,?,?,?,1,?,?)", (*(v[k] for k in FIELDS), at, by)).lastrowid


def update(c, kid: int, v: dict, by: int, at: str):
    c.execute("UPDATE campus_kb SET heading=?, text=?, request=?, action_label=?, source=?, source_ref=?, review_at=?, status=?, "
              "version=version+1, updated_at=?, updated_by=? WHERE id=?", (*(v[k] for k in FIELDS), at, by, kid))


def request_codes(c) -> set[str]:
    return {r["code"] for r in rows(c, "SELECT code FROM request_types")}


def campus_message(c, mid: int, uid: int):
    return row(c, "SELECT * FROM messages WHERE id=? AND user_id=? AND channel='campus' AND role='assistant'", (mid, uid))


def campus_before(c, uid: int, mid: int, limit: int = 6) -> list[dict]:
    """The user's campus conversation up to and including message ``mid`` on that message's day, oldest first: an
    earlier day's question (a phone number, a FIN) does not go into a ticket (Checkpoint E, TM-E16)."""
    out = rows(c, "SELECT id, role, content FROM messages WHERE user_id=? AND channel='campus' AND id<=? "
                  "AND created_at>=(SELECT substr(created_at, 1, 10) FROM messages WHERE id=?) ORDER BY id DESC LIMIT ?",
               (uid, mid, mid, limit))
    return out[::-1]


def set_message_meta(c, mid: int, meta: str):
    c.execute("UPDATE messages SET meta=? WHERE id=?", (meta, mid))
