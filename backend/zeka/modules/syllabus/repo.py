"""SQL of the syllabus module (tasks/todo.md, Task 23)."""
from __future__ import annotations

from ...legacy.store import row, rows

META = "v.id, v.course_id, v.version, v.status, v.created_at, v.note, v.decided_at, v.source, u.full_name author"


def course(c, cid: int):
    return row(c, "SELECT * FROM courses WHERE id=?", (cid,))


def units(c, cid: int) -> list[dict]:
    return rows(c, "SELECT kind, hours, students FROM teaching_units WHERE course_id=? AND active=1", (cid,))


def versions(c, cid: int) -> list[dict]:
    return rows(c, f"SELECT {META} FROM syllabus_versions v LEFT JOIN users u ON u.id=v.author_id "  # nosec B608 (constant columns)
                   "WHERE v.course_id=? ORDER BY v.version DESC", (cid,))


def version(c, cid: int, vid: int):
    return row(c, "SELECT * FROM syllabus_versions WHERE course_id=? AND id=?", (cid, vid))


def latest(c, cid: int):
    return row(c, "SELECT * FROM syllabus_versions WHERE course_id=? ORDER BY version DESC LIMIT 1", (cid,))


def published(c, cid: int):
    return row(c, "SELECT * FROM syllabus_versions WHERE course_id=? AND status='published' ORDER BY version DESC LIMIT 1", (cid,))


def published_of(c, cids: list[int]) -> dict[int, dict]:
    """{course id: its latest published version} for these courses, a read per 500 (the coverage report of a programme)."""
    out: dict[int, dict] = {}
    for k in range(0, len(cids), 500):
        part = cids[k:k + 500]
        for r in rows(c, f"SELECT * FROM syllabus_versions WHERE course_id IN ({_marks(len(part))}) AND status='published' "  # nosec B608
                         "ORDER BY course_id, version", tuple(part)):
            out[r["course_id"]] = r                      # the last of a course is its latest
    return out


def add_version(c, cid: int, data: str, author: int, at: str, source: str | None = None) -> int:
    """The next version number in the same statement: two saves at once cannot take one number."""
    return c.execute("INSERT INTO syllabus_versions(course_id,version,status,data,author_id,created_at,source) "
                     "SELECT ?, COALESCE(MAX(version), 0) + 1, 'draft', ?, ?, ?, ? FROM syllabus_versions WHERE course_id=?",
                     (cid, data, author, at, source, cid)).lastrowid


# ---------------------------------------------------------------- the course registry (prerequisites, copies)
def _marks(n: int) -> str:
    return ",".join("?" * n)


def registry_names(c, codes: list[str]) -> dict[str, str]:
    """{code: name} of the registry's courses with these codes (the latest offering's name)."""
    out: dict[str, str] = {}
    for k in range(0, len(codes), 500):
        part = codes[k:k + 500]
        out |= {r["code"]: r["name"] for r in rows(c, f"SELECT code, name FROM courses WHERE code IN ({_marks(len(part))}) "  # nosec B608
                                                      "ORDER BY id", tuple(part))}
    return out


REGISTRY_READ = 200      # rows one arm reads at most: two typed letters can start hundreds of offerings


def registry_search(c, prefixes: list[str], other_than: str, limit: int) -> list[dict]:
    """Active registry courses whose code or name starts with one of ``prefixes``, one per code (its latest offering's
    name) in code order, code and name only. One index range per arm (0231, 0232), each read in code order with its own
    limit, so no arm crowds another out (WF27F-1): ``LIKE '%q%'`` reads the whole registry, and an OR or a GROUP BY lets
    the planner choose a scan of the code index. A name arm sorts its range (the name index pinned: never that scan).
    shortcut: a code with more than REGISTRY_READ active offerings in one arm can show an older name; raise it then."""
    if not prefixes:
        return []
    end = "\U0010ffff"                                   # above every character: [p, p + end) is what starts with p
    arms = " UNION ALL ".join(f"SELECT * FROM (SELECT code, name, id FROM courses{pin} WHERE active=1 AND {col}>=? AND {col}<? "
                              "ORDER BY code LIMIT ?)"
                              for _ in prefixes for col, pin in (("code", ""), ("name", " INDEXED BY idx_courses_name")))
    found = rows(c, arms, tuple(x for p in prefixes for x in (p, p + end, REGISTRY_READ, p, p + end, REGISTRY_READ)))  # nosec B608 (placeholders)
    latest: dict[str, dict] = {}
    for r in found:
        if r["code"] != other_than and (r["code"] not in latest or r["id"] > latest[r["code"]]["id"]):
            latest[r["code"]] = r
    return [{"code": k, "name": latest[k]["name"]} for k in sorted(latest)[:limit]]


def registry_match(c, texts: list[str]) -> dict[str, str]:
    """{text: code} for free-text prerequisites that name a registry course exactly, by its code or its name."""
    if not texts:
        return {}
    found = rows(c, f"SELECT code, name FROM courses WHERE code IN ({_marks(len(texts))}) OR name IN ({_marks(len(texts))}) "  # nosec B608
                    "ORDER BY id", (*texts, *texts))
    return {r["name"]: r["code"] for r in found} | {r["code"]: r["code"] for r in found}


def term_start(c, term_id: int | None) -> str | None:
    t = row(c, "SELECT teaching_start FROM academic_terms WHERE id=?", (term_id,)) if term_id else None
    return t["teaching_start"] if t else None


def copy_sources(c, cid: int, code: str, uid: int) -> list[dict]:
    """The latest published version of every other course with this code, or that this user heads or teaches a unit of
    (``mine``)."""
    mine = "(co.teacher_id=? OR co.id IN (SELECT course_id FROM teaching_units WHERE teacher_id=? AND active=1))"
    return rows(c, f"SELECT co.id course_id, co.code, co.name, t.name term, t.teaching_start, v.id version_id, v.version, v.decided_at, "  # nosec B608
                   f"{mine} mine FROM syllabus_versions v JOIN courses co ON co.id=v.course_id LEFT JOIN academic_terms t ON t.id=co.term_id "
                   f"WHERE v.status='published' AND co.id<>? AND (co.code=? OR {mine}) "
                   "AND v.version=(SELECT MAX(x.version) FROM syllabus_versions x WHERE x.course_id=co.id AND x.status='published') "
                   "ORDER BY t.teaching_start DESC, co.code, co.id", (uid, uid, cid, code, uid, uid))


def authored(c, code: str, uid: int, other: int) -> list[int]:
    """The other courses of this code the user heads."""
    return [r["id"] for r in rows(c, "SELECT id FROM courses WHERE code=? AND teacher_id=? AND id<>?", (code, uid, other))]


def replace_map(c, cid: int, pairs: list[tuple[str, int]], by: int, at: str):
    """The course's outcome map becomes ``pairs`` (outcome, item id): a copy brings its source's tags."""
    c.execute("DELETE FROM outcome_items WHERE course_id=?", (cid,))
    c.executemany("INSERT OR IGNORE INTO outcome_items(course_id,outcome,item_id,mapped_by,mapped_at) VALUES(?,?,?,?,?)",
                  [(cid, o, i, by, at) for o, i in pairs])


def live_map(c, cid: int) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for r in rows(c, "SELECT outcome, item_id FROM outcome_items WHERE course_id=? ORDER BY outcome, item_id", (cid,)):
        out.setdefault(r["outcome"], []).append(r["item_id"])
    return out


# ---------------------------------------------------------------- the overview of a term
def terms(c) -> list[dict]:
    return rows(c, "SELECT id, code, name FROM academic_terms ORDER BY teaching_start DESC, id DESC")


def term_courses(c, term_id: int) -> list[dict]:
    """Every active course of a term with its department, head and the state of its syllabus (indexed lookups per course)."""
    return rows(c, "SELECT co.id, co.id course_id, co.code, co.name, co.department_id, d.faculty_id, d.name department, "
                   "u.full_name teacher, (SELECT v.status FROM syllabus_versions v WHERE v.course_id=co.id ORDER BY v.version DESC LIMIT 1) status, "
                   "(SELECT MAX(v.version) FROM syllabus_versions v WHERE v.course_id=co.id) latest, "
                   "(SELECT MAX(v.version) FROM syllabus_versions v WHERE v.course_id=co.id AND v.status='published') published "
                   "FROM courses co LEFT JOIN departments d ON d.id=co.department_id LEFT JOIN users u ON u.id=co.teacher_id "
                   "WHERE co.term_id=? AND co.active=1 ORDER BY co.code, co.id", (term_id,))


def legacy(c, cid: int):
    """A syllabus saved before Task 23 (one row per course, the assistant's shape)."""
    return row(c, "SELECT data FROM syllabi WHERE course_id=?", (cid,))


# ---------------------------------------------------------------- approval and publication (Task 25)
def set_status(c, vid: int, status: str, note: str, by: int, at: str):
    c.execute("UPDATE syllabus_versions SET status=?, note=?, decided_by=?, decided_at=? WHERE id=?", (status, note or None, by, at, vid))


def add_step(c, vid: int, action: str, by: int, note: str, at: str):
    c.execute("INSERT INTO syllabus_steps(version_id,action,user_id,note,at) VALUES(?,?,?,?,?)", (vid, action, by, note or None, at))


def steps(c, vid: int) -> list[dict]:
    return rows(c, "SELECT s.action, s.note, s.at, u.full_name who FROM syllabus_steps s LEFT JOIN users u ON u.id=s.user_id "
                   "WHERE s.version_id=? ORDER BY s.id", (vid,))


def has_grades(c, cid: int) -> bool:
    return row(c, "SELECT 1 FROM grades WHERE course_id=? AND score IS NOT NULL LIMIT 1", (cid,)) is not None


def publish_course(c, cid: int, grading: str, limit: float, modes: str, locked: int):
    """What a published syllabus configures on its course (Task 25)."""
    c.execute("UPDATE courses SET grading=?, attendance_limit=?, tutor_modes=?, tutor_locked=? WHERE id=?", (grading, limit, modes, locked, cid))


def pending(c, statuses: tuple[str, ...]) -> list[dict]:
    """The versions waiting in these statuses, without their data: the queue reads the data of one page only (AR-11)."""
    return rows(c, "SELECT v.id, v.course_id, v.version, v.status, v.created_at, co.code, co.name, co.teacher_id, co.department_id, "  # nosec B608
                   "d.faculty_id, u.full_name author FROM syllabus_versions v JOIN courses co ON co.id=v.course_id "
                   "LEFT JOIN departments d ON d.id=co.department_id LEFT JOIN users u ON u.id=v.author_id "
                   f"WHERE v.status IN ({_marks(len(statuses))}) ORDER BY v.created_at, v.id", statuses)


def decided(c, cids: list[int]) -> list[dict]:
    """The returned, approved and published versions of these courses, without data: a queue page's published versions
    and the returns its resubmissions answer."""
    if not cids:
        return []
    return rows(c, "SELECT id, course_id, version, status, note FROM syllabus_versions "  # nosec B608 (placeholders)
                   f"WHERE course_id IN ({_marks(len(cids))}) AND status IN ('returned','approved','published')", tuple(cids))


def data_of(c, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    return {r["id"]: r["data"] for r in rows(c, f"SELECT id, data FROM syllabus_versions WHERE id IN ({_marks(len(ids))})", tuple(ids))}  # nosec B608


def units_of(c, cids: list[int]) -> list[dict]:
    if not cids:
        return []
    return rows(c, f"SELECT course_id, kind, hours, students FROM teaching_units WHERE course_id IN ({_marks(len(cids))}) AND active=1",  # nosec B608
                tuple(cids))


def enrolled(c, cid: int, uid: int) -> bool:
    return row(c, "SELECT 1 FROM enrollments WHERE course_id=? AND user_id=?", (cid, uid)) is not None


def students(c, cid: int) -> list[int]:
    return [r["user_id"] for r in rows(c, "SELECT user_id FROM enrollments WHERE course_id=?", (cid,))]


# ---------------------------------------------------------------- frameworks and the outcome map (Task 24)
FW = "id, key, version, title, source_url, sha256, size, counts, links, builtin, imported_at"
ITEM = "i.id, i.code, i.kind, i.parent, i.title, i.text"


def frameworks(c) -> list[dict]:
    return rows(c, f"SELECT {FW} FROM frameworks")                    # nosec B608 (constant columns); a row per version


def framework(c, fid: int):
    return row(c, f"SELECT {FW} FROM frameworks WHERE id=?", (fid,))  # nosec B608


def framework_version(c, key: str, version: str):
    return row(c, f"SELECT {FW} FROM frameworks WHERE key=? AND version=?", (key, version))  # nosec B608


def add_framework(c, key: str, version: str, title: str, url: str | None, sha: str, size: int, counts: str, links: int, at: str) -> int:
    return c.execute("INSERT INTO frameworks(key,version,title,source_url,sha256,size,counts,links,builtin,imported_at) "
                     "VALUES(?,?,?,?,?,?,?,?,0,?)", (key, version, title, url, sha, size, counts, links, at)).lastrowid


def add_items(c, fid: int, items: list[dict]) -> dict[str, int]:
    c.executemany("INSERT INTO framework_items(framework_id,code,kind,parent,title,text) VALUES(?,?,?,?,?,?)",
                  [(fid, i["code"], i["kind"], i["parent"], i["title"], i["text"]) for i in items])
    return {r["code"]: r["id"] for r in rows(c, "SELECT id, code FROM framework_items WHERE framework_id=?", (fid,))}


def add_links(c, pairs: list[tuple[int, int]]):
    c.executemany("INSERT OR IGNORE INTO framework_links(source_id,dest_id) VALUES(?,?)", pairs)


def put_builtin(c, key: str, version: str, title: str, url: str | None, counts: str, at: str) -> int:
    """A built-in framework's row; written only when something changed (every start calls it)."""
    c.execute("INSERT INTO frameworks(key,version,title,source_url,counts,builtin,imported_at) VALUES(?,?,?,?,?,1,?) "
              "ON CONFLICT(key, version) DO UPDATE SET title=excluded.title, source_url=excluded.source_url, counts=excluded.counts "
              "WHERE title IS NOT excluded.title OR source_url IS NOT excluded.source_url OR counts IS NOT excluded.counts",
              (key, version, title, url, counts, at))
    return row(c, "SELECT id FROM frameworks WHERE key=? AND version=?", (key, version))["id"]


def put_item(c, fid: int, code: str, kind: str, parent: str | None, title: str, text: str):
    c.execute("INSERT INTO framework_items(framework_id,code,kind,parent,title,text) VALUES(?,?,?,?,?,?) "
              "ON CONFLICT(framework_id, code) DO UPDATE SET kind=excluded.kind, parent=excluded.parent, title=excluded.title, "
              "text=excluded.text WHERE kind IS NOT excluded.kind OR parent IS NOT excluded.parent OR title IS NOT excluded.title "
              "OR text IS NOT excluded.text", (fid, code, kind, parent, title, text))


def kind_counts(c, fid: int) -> dict[str, int]:
    return {r["kind"]: r["n"] for r in rows(c, "SELECT kind, COUNT(*) n FROM framework_items WHERE framework_id=? GROUP BY kind ORDER BY kind", (fid,))}


def link_count(c, fid: int) -> int:
    return row(c, "SELECT COUNT(*) n FROM framework_items i JOIN framework_links l ON l.source_id=i.id WHERE i.framework_id=?", (fid,))["n"]


def item(c, fid: int, code: str):
    return row(c, "SELECT id, kind FROM framework_items WHERE framework_id=? AND code=?", (fid, code))


def search_items(c, fid: int, kind: str | None, like: str | None, role_id: int | None, limit: int, offset: int,
                 written: bool = False) -> list[dict]:
    """A page of a framework's items in (kind, code) order, or with ``written`` in the order they were written (a built-in
    framework: Bloom's levels low to high, D6); ``role_id``: the items that work role links to."""
    sql = f"SELECT {ITEM} FROM framework_items i"                      # nosec B608 (constant fragments)
    args: list[object] = []
    if role_id:
        sql += " JOIN framework_links l ON l.dest_id=i.id AND l.source_id=?"
        args.append(role_id)
    sql += " WHERE i.framework_id=?"
    args.append(fid)
    if kind:
        sql += " AND i.kind=?"
        args.append(kind)
    if like:
        sql += " AND (i.code LIKE ? ESCAPE '\\' OR i.title LIKE ? ESCAPE '\\' OR i.text LIKE ? ESCAPE '\\')"
        args += [like, like, like]
    return rows(c, sql + (" ORDER BY i.kind, i.id" if written else " ORDER BY i.kind, i.code") + " LIMIT ? OFFSET ?", (*args, limit, offset))


def items_by_ids(c, ids: list[int]) -> list[dict]:
    if not ids:
        return []
    return rows(c, f"SELECT id, kind FROM framework_items WHERE id IN ({','.join('?' * len(ids))})", tuple(ids))  # nosec B608 (placeholders)


def items_of_kind(c, fid: int, kind: str) -> list[dict]:
    return rows(c, "SELECT id, code, parent, title, text FROM framework_items WHERE framework_id=? AND kind=? ORDER BY code", (fid, kind))


def role_statements(c, fid: int, kinds: tuple[str, ...]) -> list[dict]:
    """Every work role's linked statements of these kinds: (role_id, id, code, kind, text)."""
    return rows(c, "SELECT l.source_id role_id, i.id, i.code, i.kind, i.text FROM framework_items r "  # nosec B608 (placeholders)
                   "JOIN framework_links l ON l.source_id=r.id JOIN framework_items i ON i.id=l.dest_id "
                   f"WHERE r.framework_id=? AND r.kind='work_role' AND i.kind IN ({','.join('?' * len(kinds))}) "
                   "ORDER BY l.source_id, i.kind, i.code", (fid, *kinds))


def outcome_item_ids(c, cid: int, oid: str) -> list[int]:
    return [r["item_id"] for r in rows(c, "SELECT item_id FROM outcome_items WHERE course_id=? AND outcome=?", (cid, oid))]


def map_item(c, cid: int, oid: str, iid: int, by: int, at: str):
    c.execute("INSERT OR IGNORE INTO outcome_items(course_id,outcome,item_id,mapped_by,mapped_at) VALUES(?,?,?,?,?)", (cid, oid, iid, by, at))


def unmap_item(c, cid: int, oid: str, iid: int):
    c.execute("DELETE FROM outcome_items WHERE course_id=? AND outcome=? AND item_id=?", (cid, oid, iid))


def unmap_gone(c, cid: int, keep: list[str]) -> int:
    """The tags of the outcomes a saved version no longer has (BR-F2): a later outcome given that code starts empty."""
    return c.execute(f"DELETE FROM outcome_items WHERE course_id=? AND outcome NOT IN ({','.join('?' * len(keep))})",  # nosec B608
                     (cid, *keep)).rowcount


def freeze_tags(c, vid: int, cid: int):
    """A submitted version keeps the course's outcome map as it is now (SEC-FW-1): {outcome: [item id …]}."""
    c.execute("UPDATE syllabus_versions SET tags=COALESCE((SELECT json_group_object(outcome, json(ids)) FROM ("
              "SELECT outcome, json_group_array(item_id) ids FROM (SELECT outcome, item_id FROM outcome_items WHERE course_id=? "
              "ORDER BY outcome, item_id) GROUP BY outcome)), '{}') WHERE id=?", (cid, vid))


def items_full(c, ids: list[int]) -> list[dict]:
    """Items with their framework, for a version's own map."""
    out: list[dict] = []
    for k in range(0, len(ids), 500):
        part = ids[k:k + 500]
        out += rows(c, f"SELECT {ITEM}, f.id framework_id, f.key, f.version, f.builtin FROM framework_items i "  # nosec B608 (placeholders)
                       f"JOIN frameworks f ON f.id=i.framework_id WHERE i.id IN ({','.join('?' * len(part))})", tuple(part))
    return out


def course_items(c, cid: int) -> list[dict]:
    return rows(c, f"SELECT o.outcome, o.mapped_at, {ITEM}, f.id framework_id, f.key, f.version, f.builtin FROM outcome_items o "  # nosec B608
                   "JOIN framework_items i ON i.id=o.item_id JOIN frameworks f ON f.id=i.framework_id "
                   "WHERE o.course_id=? ORDER BY o.outcome, f.key, f.version, i.kind, i.code", (cid,))


def maps_for_courses(c, cids: list[int], fid: int) -> list[dict]:
    out: list[dict] = []
    for k in range(0, len(cids), 500):
        part = cids[k:k + 500]
        out += rows(c, "SELECT o.course_id, o.outcome, o.item_id FROM outcome_items o JOIN framework_items i ON i.id=o.item_id "  # nosec B608
                       f"WHERE o.course_id IN ({','.join('?' * len(part))}) AND i.framework_id=?", (*part, fid))
    return out


def specialties(c) -> list[dict]:
    return rows(c, "SELECT id, code, name, faculty_id, department_id FROM specialties WHERE active=1 ORDER BY code")


def specialty(c, sid: int):
    return row(c, "SELECT id, code, name, faculty_id, department_id FROM specialties WHERE id=?", (sid,))


def programme_courses(c, sid: int) -> list[dict]:
    """A programme's courses: those with an active teaching unit for one of the programme's groups (Forma №3, Task 16)."""
    return rows(c, "SELECT DISTINCT co.id, co.code, co.name FROM study_groups g JOIN teaching_unit_groups ug ON ug.group_id=g.id "
                   "JOIN teaching_units u ON u.id=ug.unit_id AND u.active=1 JOIN courses co ON co.id=u.course_id "
                   "WHERE g.specialty_id=? ORDER BY co.code, co.id", (sid,))
