"""SQL of the identity module (Task 10). Only this file talks to the database."""
from __future__ import annotations

from datetime import datetime, timedelta

from ...legacy.store import iso, now, row, rows
from . import domain


def find_login(c, login: str):
    """The account for a typed login: the user name or the e-mail address (both stored in lower case)."""
    return row(c, "SELECT * FROM users WHERE username=? OR email=?", (login, login))


def user(c, uid: int):
    return row(c, "SELECT * FROM users WHERE id=?", (uid,))


def block_wait(c, account: str, client: str, t: float) -> float:
    r = row(c, "SELECT until FROM login_blocks WHERE account=? AND client=?", (account, client))
    return max(0.0, (r["until"] or 0) - t) if r else 0.0


def lock_wait(u) -> float:
    if not u or not u["locked_until"]:
        return 0.0
    return max(0.0, (datetime.fromisoformat(u["locked_until"]) - now()).total_seconds())


def record_failure(c, account: str, client: str, t: float) -> bool:
    """Count one failure of this client for this account; True when it starts a block."""
    c.execute("DELETE FROM login_blocks WHERE first<? AND (until IS NULL OR until<?)", (t - domain.WINDOW, t))
    r = row(c, "SELECT failures, first FROM login_blocks WHERE account=? AND client=?", (account, client))
    failures, first = (r["failures"] + 1, r["first"]) if r and r["first"] >= t - domain.WINDOW else (1, t)
    blocked = failures >= domain.CLIENT_LIMIT
    if blocked:                                  # the block runs from now; counting starts again after it
        failures, first = 0, t
    c.execute("INSERT INTO login_blocks(account,client,failures,first,until) VALUES(?,?,?,?,?) ON CONFLICT(account,client) "
              "DO UPDATE SET failures=excluded.failures, first=excluded.first, until=excluded.until",
              (account, client, failures, first, t + domain.BLOCK if blocked else None))
    return blocked


def account_failure(c, uid: int) -> bool:
    """Count one consecutive failure of the account; True when it locks the account."""
    c.execute("UPDATE users SET failed_count=failed_count+1 WHERE id=?", (uid,))
    if row(c, "SELECT failed_count FROM users WHERE id=?", (uid,))["failed_count"] < domain.ACCOUNT_LIMIT:
        return False
    c.execute("UPDATE users SET failed_count=0, locked_until=? WHERE id=?",
              (iso(now() + timedelta(seconds=domain.BLOCK)), uid))
    return True


def unknown_failure(c, account: str, t: float):
    """A failure for a name no account has: counted in a row of its own ("*") and locked after as many as a real
    account, so the answer to a locked name is the same whether it exists or not."""
    r = row(c, "SELECT failures FROM login_blocks WHERE account=? AND client='*'", (account,))
    n = (r["failures"] if r else 0) + 1
    locked = n >= domain.ACCOUNT_LIMIT
    c.execute("INSERT INTO login_blocks(account,client,failures,first,until) VALUES(?,'*',?,?,?) ON CONFLICT(account,client) "
              "DO UPDATE SET failures=excluded.failures, first=excluded.first, until=excluded.until",
              (account, 0 if locked else n, t, t + domain.BLOCK if locked else None))


def signed_in(c, account: str, client: str, uid: int, new_hash: str | None, complete: bool = True):
    """The password was right. Failure counts clear only when the sign-in is complete: while a second factor is
    pending they stay, or every correct password would buy five more code guesses (Task 12)."""
    if new_hash:
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, uid))
    if complete:
        clear_failures(c, account, client, uid)


def clear_failures(c, account: str, client: str, uid: int):
    c.execute("DELETE FROM login_blocks WHERE account=? AND client=?", (account, client))
    c.execute("UPDATE users SET failed_count=0, locked_until=NULL WHERE id=?", (uid,))


def set_password(c, uid: int, password_hash: str, must_change: bool):
    c.execute("UPDATE users SET password_hash=?, must_change=?, failed_count=0, locked_until=NULL WHERE id=?",
              (password_hash, int(must_change), uid))


def unlock(c, u):
    c.execute("UPDATE users SET failed_count=0, locked_until=NULL WHERE id=?", (u["id"],))
    c.execute("DELETE FROM login_blocks WHERE account IN (?, ?)", (u["username"], u["email"] or u["username"]))


# ---------------------------------------------------------------- sessions (Task 11)
def sessions_of(c, uid: int) -> list:
    return rows(c, "SELECT id, created_at, last_seen, ip, agent FROM sessions WHERE user_id=? ORDER BY last_seen DESC", (uid,))


def end_session(c, uid: int, session_id: int) -> bool:
    return c.execute("DELETE FROM sessions WHERE id=? AND user_id=?", (session_id, uid)).rowcount == 1


def end_sessions(c, uid: int, keep: int | None = None) -> int:
    """End every session of the account except ``keep``; returns how many ended."""
    return c.execute("DELETE FROM sessions WHERE user_id=? AND id IS NOT ?", (uid, keep)).rowcount


# ---------------------------------------------------------------- second factor (Task 12)
def set_session_scope(c, session_id: int, scope: str):
    c.execute("UPDATE sessions SET scope=?, mfa_at=?, mfa_failures=0 WHERE id=?",
              (scope, iso(now()) if scope == "full" else None, session_id))


def mfa_failure(c, session_id: int) -> int:
    c.execute("UPDATE sessions SET mfa_failures=mfa_failures+1 WHERE id=?", (session_id,))
    r = row(c, "SELECT mfa_failures FROM sessions WHERE id=?", (session_id,))
    return r["mfa_failures"] if r else 0


def start_totp(c, uid: int, secret: str):
    c.execute("UPDATE users SET totp_secret=?, totp_last=NULL, totp_enabled_at=NULL WHERE id=?", (secret, uid))


def enable_totp(c, uid: int, step: int, code_hashes: list[str]):
    c.execute("UPDATE users SET totp_last=?, totp_enabled_at=? WHERE id=?", (step, iso(now()), uid))
    c.execute("DELETE FROM recovery_codes WHERE user_id=?", (uid,))
    c.executemany("INSERT INTO recovery_codes(user_id,code_hash) VALUES(?,?)", [(uid, h) for h in code_hashes])


def accept_step(c, uid: int, step: int) -> bool:
    """Record the accepted 30-second step; False when another request used this or a later step first."""
    return c.execute("UPDATE users SET totp_last=? WHERE id=? AND (totp_last IS NULL OR totp_last<?)",
                     (step, uid, step)).rowcount == 1


def use_recovery_code(c, uid: int, code_hash: str) -> bool:
    return c.execute("UPDATE recovery_codes SET used_at=? WHERE user_id=? AND code_hash=? AND used_at IS NULL",
                     (iso(now()), uid, code_hash)).rowcount == 1


def recovery_left(c, uid: int) -> int:
    return row(c, "SELECT COUNT(*) n FROM recovery_codes WHERE user_id=? AND used_at IS NULL", (uid,))["n"]


def reset_totp(c, uid: int):
    c.execute("UPDATE users SET totp_secret=NULL, totp_last=NULL, totp_enabled_at=NULL WHERE id=?", (uid,))
    c.execute("DELETE FROM recovery_codes WHERE user_id=?", (uid,))


# ---------------------------------------------------------------- roles (Task 13)
def roles_of(c, u) -> list[dict]:
    """The primary role first, then every granted role with its scope."""
    primary = u.get("primary_role") or u["role"]
    return [{"id": None, "role": primary, "scope_type": None, "scope_id": None, "primary": True}] + [
        {**g, "primary": False} for g in rows(c, "SELECT id, role, scope_type, scope_id FROM role_grants WHERE user_id=? "
                                                 "ORDER BY role, scope_type, scope_id", (u["id"],))]


def set_session_role(c, session_id: int, role: str | None):
    c.execute("UPDATE sessions SET role=? WHERE id=?", (role, session_id))


def grant_role(c, uid: int, role: str, scope_type: str | None, scope_id: int | None, by: int) -> int:
    return c.execute("INSERT INTO role_grants(user_id,role,scope_type,scope_id,granted_by,granted_at) VALUES(?,?,?,?,?,?)",
                     (uid, role, scope_type, scope_id, by, iso(now()))).lastrowid


def grant(c, uid: int, grant_id: int):
    return row(c, "SELECT * FROM role_grants WHERE id=? AND user_id=?", (grant_id, uid))


def drop_grant(c, grant_id: int):
    c.execute("DELETE FROM role_grants WHERE id=?", (grant_id,))


# ---------------------------------------------------------------- single sign-on (Task 14)
def add_pending(c, state: str, browser_hash: str, nonce: str, verifier: str, link_user_id: int | None, t: float):
    c.execute("DELETE FROM sso_pending WHERE created_at<?", (t - domain.SSO_PENDING,))
    c.execute("INSERT INTO sso_pending(state,browser_hash,nonce,verifier,link_user_id,created_at) VALUES(?,?,?,?,?,?)",
              (state, browser_hash, nonce, verifier, link_user_id, t))


def take_pending(c, state: str):
    """The started sign-in for ``state``, removed in the same statement: only one callback in any worker gets it."""
    return c.execute("DELETE FROM sso_pending WHERE state=? RETURNING *", (state,)).fetchone()


def sso_user(c, iss: str, sub: str):
    return row(c, "SELECT u.* FROM sso_identities i JOIN users u ON u.id=i.user_id WHERE i.iss=? AND i.sub=?", (iss, sub))


def students_by_number(c, number: str) -> list:
    return rows(c, "SELECT * FROM users WHERE student_no=? AND role='student'", (number,))


def by_email(c, email: str):
    return row(c, "SELECT * FROM users WHERE email=?", (email,))


def granted_roles(c, uid: int) -> set[str]:
    return {r["role"] for r in rows(c, "SELECT DISTINCT role FROM role_grants WHERE user_id=?", (uid,))}


def add_identity(c, uid: int, iss: str, sub: str, email: str | None, linked_by: str) -> bool:
    """False when this (iss, sub) is bound already, or the account already has a binding with this issuer."""
    return c.execute("INSERT OR IGNORE INTO sso_identities(user_id,iss,sub,email,linked_by,linked_at) VALUES(?,?,?,?,?,?)",
                     (uid, iss, sub, email, linked_by, iso(now()))).rowcount == 1


def identity_seen(c, iss: str, sub: str, email: str | None):
    c.execute("UPDATE sso_identities SET last_login=?, email=? WHERE iss=? AND sub=?", (iso(now()), email, iss, sub))


def identities_of(c, uid: int) -> list:
    return rows(c, "SELECT id, iss, sub, email, linked_by, linked_at, last_login FROM sso_identities WHERE user_id=? "
                   "ORDER BY id", (uid,))


def remove_identity(c, uid: int, identity_id: int):
    """The removed binding, or None."""
    return c.execute("DELETE FROM sso_identities WHERE id=? AND user_id=? RETURNING iss, sub", (identity_id, uid)).fetchone()


# ---------------------------------------------------------------- privacy (Task 40)
# The data inventory (docs/privacy/data-inventory.md is its readable form): every column that holds a person's id, how
# that person's export reads it and what an approved erasure does with it. The export part is a condition on the table
# with :uid, or None: the column does not put the row in the export (the reason is in the document). The erasure part:
# "delete" the rows, or "keep" them (an academic or legal record, or someone else's record naming the person as its
# actor); the users row itself is anonymised. tests/integration/test_privacy.py reads the schema and fails on a column
# that is missing here.
D, K = "delete", "keep"
RELEASED = "exam_id IN (SELECT id FROM exams WHERE status = 'released')"
INVENTORY: dict[tuple[str, str], tuple[str | None, str]] = {
    ("users", "id"): ("id = :uid", "anonymise"),
    ("academy_progress", "user_id"): ("user_id = :uid", D),
    ("activation_codes", "user_id"): ("user_id = :uid", D),
    ("api_tokens", "created_by"): (None, K),
    ("assignments", "created_by"): (None, K),
    ("attempts", "user_id"): ("user_id = :uid", K),
    ("attendance", "user_id"): ("user_id = :uid", K),
    ("attendance", "marked_by"): (None, K),
    ("attendance_opening", "student_id"): ("student_id = :uid", K),
    ("audit", "user_id"): ("user_id = :uid", K),
    ("campus_kb", "updated_by"): (None, K),
    ("campus_kb_versions", "changed_by"): (None, K),
    ("club_members", "user_id"): ("user_id = :uid", D),
    ("club_messages", "author_id"): ("author_id = :uid", D),
    ("club_reports", "reporter_id"): ("reporter_id = :uid", D),
    ("club_reports", "resolved_by"): (None, K),
    ("clubs", "leader_id"): ("leader_id = :uid", K),
    ("clubs", "decided_by"): (None, K),
    ("consents", "user_id"): ("user_id = :uid", K),
    ("course_tools", "added_by"): (None, K),
    ("courses", "teacher_id"): ("teacher_id = :uid", K),
    ("doc_keys", "user_id"): (None, D),
    ("documents", "holder_id"): ("holder_id = :uid AND kind NOT IN ('exam_protocol', 'exam_statement')", K),
    ("documents", "issued_by"): (None, K),
    ("enrollments", "user_id"): ("user_id = :uid", K),
    ("exam_attempts", "student_id"): ("student_id = :uid", K),
    ("exam_events", "actor_id"): (None, K),
    ("exam_events", "student_id"): (f"student_id = :uid AND {RELEASED}", K),
    ("exam_forms", "student_id"): (None, K),
    ("exam_proctors", "user_id"): ("user_id = :uid", K),
    ("exam_proctors", "added_by"): (None, K),
    ("exam_roster", "student_id"): ("student_id = :uid", K),
    ("exam_roster", "added_by"): (None, K),
    ("exam_statements", "closed_by"): (None, K),
    ("events", "user_id"): ("user_id = :uid", D),             # Task 39: activity counts, a year
    ("active_days", "user_id"): ("user_id = :uid", D),        # Task 42: the days of those events, for the active-user tiles
    ("exams", "created_by"): (None, K),
    ("feedback", "user_id"): ("user_id = :uid", D),
    ("files", "owner_id"): ("owner_id = :uid", K),
    ("final_grades", "user_id"): ("user_id = :uid", K),
    ("grade_changes", "user_id"): ("user_id = :uid", K),
    ("grade_changes", "changed_by"): (None, K),
    ("grades", "user_id"): ("user_id = :uid AND status = 'published'", K),
    ("grades", "entered_by"): (None, K),
    ("ical_feeds", "user_id"): ("user_id = :uid", D),
    ("interventions", "student_id"): ("student_id = :uid", D),
    ("interventions", "created_by"): (None, K),
    ("lessons", "teacher_id"): ("teacher_id = :uid", K),
    ("materials", "uploaded_by"): (None, K),
    ("messages", "user_id"): ("user_id = :uid", D),
    ("migration_files", "imported_by"): (None, K),             # Task 38: the staff member who loaded a file
    ("news", "author_id"): (None, K),
    ("news_reads", "user_id"): ("user_id = :uid", D),
    ("news_rsvp", "user_id"): ("user_id = :uid", D),
    ("news_saved", "user_id"): ("user_id = :uid", D),
    ("notifications", "user_id"): ("user_id = :uid", D),
    ("office_bookings", "student_id"): ("student_id = :uid", D),
    ("office_bookings", "teacher_id"): (None, K),
    ("office_bookings", "cancelled_by"): (None, K),
    ("office_hours", "teacher_id"): ("teacher_id = :uid", K),
    ("outbox", "user_id"): ("user_id = :uid", D),
    ("outcome_items", "mapped_by"): (None, K),
    ("privacy_requests", "user_id"): ("user_id = :uid", K),
    ("privacy_requests", "decided_by"): (None, K),
    ("qa_replies", "author_id"): ("author_id = :uid", D),
    ("qa_reports", "reporter_id"): ("reporter_id = :uid", D),
    ("qa_reports", "resolved_by"): (None, K),
    ("questions", "created_by"): (None, K),
    ("recovery_codes", "user_id"): ("user_id = :uid", D),
    ("request_events", "actor_id"): (None, K),
    ("request_messages", "author_id"): ("author_id = :uid", K),
    ("requests", "student_id"): ("student_id = :uid", K),
    ("role_grants", "user_id"): ("user_id = :uid", D),
    ("role_grants", "granted_by"): (None, K),
    ("sessions", "user_id"): ("user_id = :uid", D),
    ("sso_identities", "user_id"): ("user_id = :uid", D),
    ("sso_identities", "linked_by"): (None, K),
    ("sso_pending", "link_user_id"): (None, D),
    ("student_status_events", "student_id"): ("student_id = :uid", K),
    ("student_status_events", "entered_by"): (None, K),
    ("submissions", "student_id"): ("student_id = :uid", K),
    ("submissions", "graded_by"): (None, K),
    ("support_messages", "author_id"): ("author_id = :uid", D),
    ("support_tickets", "user_id"): ("user_id = :uid", D),
    ("support_tickets", "assignee_id"): (None, K),
    ("syllabi", "user_id"): (None, K),
    ("syllabus_steps", "user_id"): (None, K),
    ("syllabus_versions", "author_id"): (None, K),
    ("syllabus_versions", "decided_by"): (None, K),
    ("teacher_questions", "student_id"): ("student_id = :uid", D),
    ("teaching_units", "teacher_id"): ("teacher_id = :uid", K),
    # Task 48: the timetable builder; the teacher's own availability is in VIA, the deciders and authors are kept
    ("forma3_imports", "imported_by"): (None, K),
    ("tt_availability", "updated_by"): (None, K),
    ("tt_availability_status", "teacher_id"): ("teacher_id = :uid", K),
    ("tt_availability_status", "confirmed_by"): (None, K),
    ("tt_availability_status", "decided_by"): (None, K),
    ("tt_blocks", "updated_by"): (None, K),
    ("tt_dept_status", "set_by"): (None, K),
    ("tt_group_terms", "updated_by"): (None, K),
    ("tt_notes", "author_id"): ("author_id = :uid", K),
    ("tt_notes", "resolved_by"): (None, K),
    ("tt_placements", "changed_by"): (None, K),
    ("tt_reviews", "decided_by"): (None, K),
    ("tt_runs", "requested_by"): (None, K),
    ("tt_terms", "updated_by"): (None, K),
    ("tt_unit_needs", "updated_by"): (None, K),
    ("tt_versions", "created_by"): (None, K),
    ("tt_versions", "published_by"): (None, K),
    ("webhooks", "created_by"): (None, K),
}
# Rows without a person column that belong to the person's own records: a released exam's answers (never the form or
# the questions), the history of their requests, the replies to their support tickets (not the desk's internal notes).
VIA = {
    "exam_answers": "attempt_id IN (SELECT a.id FROM exam_attempts a JOIN exams e ON e.id = a.exam_id "
                    "WHERE a.student_id = :uid AND e.status = 'released')",
    "request_events": "request_id IN (SELECT id FROM requests WHERE student_id = :uid)",
    "request_messages": "request_id IN (SELECT id FROM requests WHERE student_id = :uid)",
    "support_messages": "internal = 0 AND ticket_id IN (SELECT id FROM support_tickets WHERE user_id = :uid)",
    "tt_availability": "subject_type = 'teacher' AND subject_id = :uid",
    "tt_blocks": "subject_type = 'teacher' AND subject_id = :uid",
}
# An attempt's score is in the export only once its exam is released.
SELECTS = {
    "exam_attempts": "SELECT a.id, a.exam_id, a.student_id, a.started_at, a.deadline_at, a.submitted_at, a.auto, a.status, a.paused_at, "
                     "CASE WHEN e.status = 'released' THEN a.score END AS score, CASE WHEN e.status = 'released' THEN a.max_score END "
                     "AS max_score FROM exam_attempts a JOIN exams e ON e.id = a.exam_id WHERE a.student_id = :uid ORDER BY a.id",
}
# Run before the person's own rows: what hangs off them is deleted (reports of their club messages, the replies and
# reports of their forum topics, the messages of their support tickets), and the free text of the timetable rows that are
# kept is cleared (a teacher's availability notes, a grid waiting for the head, a leave note; Task 48).
ERASE_FIRST = (
    "DELETE FROM club_reports WHERE message_id IN (SELECT id FROM club_messages WHERE author_id = :uid)",
    "DELETE FROM qa_reports WHERE topic_id IN (SELECT id FROM teacher_questions WHERE student_id = :uid) "
    "OR reply_id IN (SELECT id FROM qa_replies WHERE author_id = :uid)",
    "DELETE FROM qa_replies WHERE topic_id IN (SELECT id FROM teacher_questions WHERE student_id = :uid)",
    "DELETE FROM support_messages WHERE ticket_id IN (SELECT id FROM support_tickets WHERE user_id = :uid)",
    "UPDATE tt_availability SET note = NULL WHERE subject_type = 'teacher' AND subject_id = :uid",
    "UPDATE tt_availability_status SET pending = NULL, pending_at = NULL WHERE teacher_id = :uid",
    "UPDATE tt_blocks SET note = NULL WHERE subject_type = 'teacher' AND subject_id = :uid",
)
# The users row stays (the kept records point at it) without what identifies or reaches the person; the student number
# stays as the link to the state register (an owner's decision, docs/privacy/data-inventory.md).
ANONYMISE = ("UPDATE users SET username = 'erased-' || id, full_name = '#' || id, patronymic = NULL, email = NULL, password_hash = NULL, "
             "must_change = 0, totp_secret = NULL, totp_last = NULL, totp_enabled_at = NULL, prefs = '{}', consent_at = NULL, "
             "failed_count = 0, locked_until = NULL, status = 'erased' WHERE id = :uid")


def export_tables(c, uid: int) -> dict[str, list[dict]]:
    """The person's own rows, table by table (every table the inventory exports from, empty ones too)."""
    where: dict[str, list[str]] = {}
    for (t, _), (cond, _) in INVENTORY.items():
        if cond:
            where.setdefault(t, []).append(cond)
    for t, cond in VIA.items():
        where.setdefault(t, []).append(cond)
    # bandit B608: table names and conditions are the constants above
    return {t: rows(c, SELECTS.get(t) or f'SELECT * FROM "{t}" WHERE ' + " OR ".join(f"({x})" for x in conds), {"uid": uid})  # nosec B608
            for t, conds in sorted(where.items())}


def erase(c, uid: int) -> dict[str, int]:
    """Delete the person's rows the inventory deletes and anonymise the users row; the count per table.column."""
    out: dict[str, int] = {}
    for sql in ERASE_FIRST:
        c.execute(sql, {"uid": uid})
    for (t, col), (_, action) in INVENTORY.items():
        if action == D:
            n = c.execute(f'DELETE FROM "{t}" WHERE "{col}" = ?', (uid,)).rowcount  # nosec B608: the inventory's names
            if n:
                out[f"{t}.{col}"] = n
    c.execute(ANONYMISE, {"uid": uid})
    return out


def consent_of(c, uid: int, purpose: str):
    """The person's newest consent row of a purpose: their current choice."""
    return row(c, "SELECT * FROM consents WHERE user_id=? AND purpose=? ORDER BY id DESC LIMIT 1", (uid, purpose))


def consenting(c, purpose: str, version: str) -> set[int]:
    """Everyone whose newest choice of a purpose is a consent to ``version`` (``consent_of`` for all people at once)."""
    return {r["user_id"] for r in rows(c, "SELECT user_id FROM consents k WHERE purpose=? AND granted=1 AND version=? AND id="
                                          "(SELECT MAX(id) FROM consents WHERE user_id=k.user_id AND purpose=?)", (purpose, version, purpose))}


def add_consent(c, uid: int, purpose: str, version: str, granted: bool, method: str, lang: str, at: str, text: str):
    c.execute("INSERT OR IGNORE INTO consent_texts(version,purpose,text,first_at) VALUES(?,?,?,?)", (version, purpose, text, at))
    c.execute("INSERT INTO consents(user_id,purpose,version,granted,method,lang,at) VALUES(?,?,?,?,?,?,?)",
              (uid, purpose, version, int(granted), method, lang, at))


def set_consent_at(c, uid: int, at: str | None):
    c.execute("UPDATE users SET consent_at=? WHERE id=?", (at, uid))


def delete_chats(c, uid: int) -> int:
    """The person's AI tutor and campus assistant chats (``messages`` holds nothing else)."""
    return c.execute("DELETE FROM messages WHERE user_id=?", (uid,)).rowcount


def privacy_request(c, rid: int):
    return row(c, "SELECT * FROM privacy_requests WHERE id=?", (rid,))


def open_privacy_request(c, uid: int):
    return row(c, "SELECT id FROM privacy_requests WHERE user_id=? AND status='pending' LIMIT 1", (uid,))


def add_privacy_request(c, uid: int, reason: str, at: str) -> int:
    return c.execute("INSERT INTO privacy_requests(user_id,kind,reason,status,created_at) VALUES(?,'erase',?,'pending',?)",
                     (uid, reason, at)).lastrowid


def privacy_requests_of(c, uid: int) -> list:
    return rows(c, "SELECT id, kind, reason, status, created_at, decided_at, note FROM privacy_requests WHERE user_id=? "
                   "ORDER BY id DESC", (uid,))


def privacy_request_list(c, status: str | None) -> list:
    """The requests (of one status, or all), pending first and then the newest, with who asked. No limit here: the
    caller filters by the decider's scope first (one row per request, a small table)."""
    return rows(c, "SELECT r.*, u.full_name, u.username, u.role, u.student_no FROM privacy_requests r JOIN users u ON u.id=r.user_id "
                   "WHERE (? IS NULL OR r.status=?) ORDER BY r.status='pending' DESC, r.id DESC", (status, status))


def other_active_admins(c, uid: int) -> int:
    return row(c, "SELECT COUNT(*) n FROM users WHERE role='admin' AND status='active' AND id<>?", (uid,))["n"]


def decide_privacy_request(c, rid: int, status: str, by: int, at: str, note: str) -> bool:
    """True when this call decided the pending request (of two deciders at once, only one gets True)."""
    return c.execute("UPDATE privacy_requests SET status=?, decided_by=?, decided_at=?, note=? WHERE id=? AND status='pending'",
                     (status, by, at, note, rid)).rowcount == 1


def set_privacy_result(c, rid: int, result: str):
    c.execute("UPDATE privacy_requests SET result=? WHERE id=?", (result, rid))
