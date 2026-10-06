"""SQLite storage, seeding and index building for the Zəka demo."""
from __future__ import annotations

import hashlib
import json
import random
import re
import secrets
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path

from . import engine
from .i18n import T3, tr3

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UPLOADS = DATA / "uploads"
DB_PATH = DATA / "campus.db"
CONTENT = ROOT / "content"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS study_groups(id INTEGER PRIMARY KEY, name TEXT, year INT);
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, full_name TEXT, patronymic TEXT, role TEXT, title TEXT,
  group_id INT, color TEXT, consent_at TEXT, synthetic INT DEFAULT 0, student_no TEXT, admission_year INT, funding TEXT, form TEXT,
  dept TEXT, prefs TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS sessions(sid TEXT PRIMARY KEY, user_id INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, code TEXT, name TEXT, teacher_id INT, credits INT, color TEXT,
  description TEXT, suggestions TEXT, tutor_modes TEXT, tutor_rules TEXT, tutor_locked INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS enrollments(user_id INT, course_id INT, PRIMARY KEY(user_id, course_id));
CREATE TABLE IF NOT EXISTS timetable(id INTEGER PRIMARY KEY, course_id INT, weekday INT, start TEXT, end TEXT, kind TEXT, room TEXT);
CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, course_id INT, day TEXT, start TEXT, end TEXT, kind TEXT, room TEXT, topic TEXT);
CREATE TABLE IF NOT EXISTS attendance(lesson_id INT, user_id INT, status TEXT, request_id INT, PRIMARY KEY(lesson_id, user_id));
CREATE TABLE IF NOT EXISTS grades(user_id INT, course_id INT, component TEXT, score REAL, max REAL, updated_at TEXT,
  PRIMARY KEY(user_id, course_id, component));
CREATE TABLE IF NOT EXISTS materials(id INTEGER PRIMARY KEY, course_id INT, title TEXT, filename TEXT, text TEXT,
  chunk_count INT, term_count INT, uploaded_by INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS chunks(id INTEGER PRIMARY KEY, material_id INT, course_id INT, seq INT, heading TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS campus_kb(id INTEGER PRIMARY KEY, heading TEXT, text TEXT, request TEXT, action_label TEXT, source TEXT);
CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, user_id INT, course_id INT, channel TEXT, role TEXT,
  content TEXT, cites TEXT, meta TEXT, rating INT, created_at TEXT, synthetic INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS teacher_questions(id INTEGER PRIMARY KEY, course_id INT, student_id INT, anonymous INT,
  question TEXT, context TEXT, answer TEXT, status TEXT, created_at TEXT, answered_at TEXT);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY, course_id INT, chunk_id INT, qtype TEXT, text TEXT,
  options TEXT, answer TEXT, unit TEXT, explanation TEXT, bloom TEXT, difficulty TEXT, topic TEXT, status TEXT,
  origin TEXT, flags TEXT, created_by INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS quizzes(id INTEGER PRIMARY KEY, course_id INT, title TEXT, kind TEXT, question_ids TEXT,
  time_limit INT, attempts INT, show_explanations INT DEFAULT 1, published INT DEFAULT 1, created_at TEXT);
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY, quiz_id INT, user_id INT, answers TEXT, details TEXT,
  score REAL, max_score REAL, started_at TEXT, finished_at TEXT, synthetic INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS service_categories(key TEXT PRIMARY KEY, seq INT, name TEXT, icon TEXT, color TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS request_types(code TEXT PRIMARY KEY, seq INT, category TEXT, name TEXT, icon TEXT, sla_hours INT,
  document TEXT, document_en TEXT, prefix TEXT, description TEXT, needs TEXT, outcome TEXT, privacy TEXT, fields TEXT,
  attachments TEXT, steps TEXT, answer TEXT, popular INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS requests(id INTEGER PRIMARY KEY, type_code TEXT, student_id INT, data TEXT, status TEXT,
  step INT DEFAULT 0, created_at TEXT, updated_at TEXT, due_at TEXT, document_id INT, answer TEXT);
CREATE TABLE IF NOT EXISTS request_events(id INTEGER PRIMARY KEY, request_id INT, actor_id INT, action TEXT, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS request_messages(id INTEGER PRIMARY KEY, request_id INT, author_id INT, text TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, owner_id INT, request_id INT, filename TEXT, mime TEXT, size INT,
  sha256 TEXT, path TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY, kind TEXT, request_id INT, holder_id INT, title TEXT,
  reg_no TEXT UNIQUE, verify_code TEXT UNIQUE, data TEXT, hash TEXT, issued_by INT, issued_at TEXT, status TEXT,
  revoked_reason TEXT, revoked_at TEXT);
CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, user_id INT, kind TEXT, title TEXT, body TEXT, link TEXT,
  created_at TEXT, read_at TEXT);
CREATE TABLE IF NOT EXISTS news(id INTEGER PRIMARY KEY, kind TEXT, title TEXT, summary TEXT, body TEXT, cover TEXT,
  author_id INT, audience TEXT, pinned INT DEFAULT 0, important INT DEFAULT 0, published_at TEXT, event_start TEXT,
  event_end TEXT, location TEXT, capacity INT, registration INT DEFAULT 0, tags TEXT, status TEXT DEFAULT 'published');
CREATE TABLE IF NOT EXISTS news_rsvp(news_id INT, user_id INT, created_at TEXT, PRIMARY KEY(news_id, user_id));
CREATE TABLE IF NOT EXISTS news_saved(news_id INT, user_id INT, PRIMARY KEY(news_id, user_id));
CREATE TABLE IF NOT EXISTS news_reads(news_id INT, user_id INT, PRIMARY KEY(news_id, user_id));
CREATE TABLE IF NOT EXISTS academy_tracks(key TEXT PRIMARY KEY, seq INT, title TEXT, icon TEXT, color TEXT, level TEXT,
  audience TEXT, summary TEXT, outcomes TEXT);
CREATE TABLE IF NOT EXISTS academy_modules(id INTEGER PRIMARY KEY, track_key TEXT, seq INT, title TEXT, minutes INT,
  paragraphs TEXT, key_points TEXT, phrases TEXT, task TEXT, link TEXT, quiz TEXT);
CREATE TABLE IF NOT EXISTS academy_progress(user_id INT, module_id INT, status TEXT, score REAL, completed_at TEXT,
  PRIMARY KEY(user_id, module_id));
CREATE TABLE IF NOT EXISTS tools(key TEXT PRIMARY KEY, seq INT, name TEXT, areas TEXT, type TEXT, pricing TEXT, platform TEXT,
  url TEXT, summary TEXT, use_cases TEXT, steps TEXT, lesson_idea TEXT);
CREATE TABLE IF NOT EXISTS course_tools(course_id INT, tool_key TEXT, added_by INT, created_at TEXT, PRIMARY KEY(course_id, tool_key));
CREATE TABLE IF NOT EXISTS syllabi(course_id INT PRIMARY KEY, user_id INT, data TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts TEXT, user_id INT, action TEXT, entity TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS support_tickets(id INTEGER PRIMARY KEY, user_id INT, category TEXT, priority TEXT, subject TEXT, body TEXT,
  page TEXT, status TEXT, assignee_id INT, rating INT, created_at TEXT, updated_at TEXT, closed_at TEXT, synthetic INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS support_messages(id INTEGER PRIMARY KEY, ticket_id INT, author_id INT, text TEXT, internal INT DEFAULT 0,
  file_id INT, created_at TEXT);
CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, user_id INT, role TEXT, area TEXT, score INT, nps INT, comment TEXT,
  page TEXT, lang TEXT, created_at TEXT, synthetic INT DEFAULT 0);
CREATE INDEX IF NOT EXISTS idx_ticket_user ON support_tickets(user_id, status);
CREATE INDEX IF NOT EXISTS idx_msg_user ON messages(user_id, channel, course_id);
CREATE INDEX IF NOT EXISTS idx_msg_course ON messages(course_id, channel, role);
CREATE INDEX IF NOT EXISTS idx_att_user ON attendance(user_id);
CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications(user_id, read_at);
CREATE INDEX IF NOT EXISTS idx_req_student ON requests(student_id);
"""


def now() -> datetime:
    return datetime.now().replace(microsecond=0)


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def rows(c, sql, args=()):
    return [dict(r) for r in c.execute(sql, args).fetchall()]


def row(c, sql, args=()):
    r = c.execute(sql, args).fetchone()
    return dict(r) if r else None


def J(v, default=None):
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default


def audit(c, user_id, action, entity="", detail=""):
    c.execute("INSERT INTO audit(ts,user_id,action,entity,detail) VALUES(?,?,?,?,?)",
              (iso(now()), user_id, action, entity, detail))


def setting(c, key, default=None):
    r = row(c, "SELECT value FROM settings WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_setting(c, key, value):
    c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, json.dumps(value, ensure_ascii=False)))


def _txt(v):
    """Store i18n dicts ({az,en,ru}) as JSON text; the response layer localizes them."""
    return json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else (v or "")


def notify(c, user_ids, kind, title, body="", link="", when=None, read=False):
    t = iso(when or now())
    for uid in ([user_ids] if isinstance(user_ids, int) else user_ids):
        c.execute("INSERT INTO notifications(user_id,kind,title,body,link,created_at,read_at) VALUES(?,?,?,?,?,?,?)",
                  (uid, kind, _txt(title), _txt(body), link, t, t if read else None))


# ---------------------------------------------------------------- files
ALLOWED = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
           "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
MAX_FILE = 10 * 1024 * 1024


def sniff(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith(b"PK\x03\x04"):
        return "docx"
    return None


def save_file(c, owner_id, filename, data: bytes, accept="doc", when=None) -> dict:
    """Validate (type by magic bytes, size) and store a file; returns its row."""
    if not data:
        raise ValueError("Fayl boşdur")
    if len(data) > MAX_FILE:
        raise ValueError("Fayl 10 MB-dan böyükdür")
    kind = sniff(data)
    ext = Path(filename).suffix.lower().lstrip(".")
    if kind is None or (ext and ALLOWED.get(ext) != ALLOWED[kind]):
        raise ValueError("Yalnız PDF, JPG, PNG və DOCX fayllar qəbul olunur")
    if accept == "image" and kind not in ("png", "jpg"):
        raise ValueError("Bu sahə üçün yalnız şəkil (JPG, PNG) qəbul olunur")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    path = UPLOADS / f"{digest}.bin"
    if not path.exists():
        path.write_bytes(data)
    safe = re.sub(r"[^\wəıöüşçğƏİÖÜŞÇĞ .()-]", "_", Path(filename).name)[:120] or f"fayl.{kind}"
    fid = c.execute("INSERT INTO files(owner_id,request_id,filename,mime,size,sha256,path,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (owner_id, None, safe, ALLOWED[kind], len(data), digest, path.name, iso(when or now()))).lastrowid
    return row(c, "SELECT * FROM files WHERE id=?", (fid,))


def demo_pdf(lines: list[str]) -> bytes:
    """Tiny valid one-page PDF (ASCII text) used for synthetic attachments."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = "BT /F1 13 Tf 64 770 Td " + " ".join(f"({esc(l)}) Tj 0 -22 Td" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode() + b"".join(f"{o:010d} 00000 n \n".encode() for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


# ---------------------------------------------------------------- materials
def add_material(c, course_id, title, filename, text, user_id, created_at=None) -> dict:
    parts = engine.chunk_markdown(text)
    if not parts:
        raise ValueError("Materialda mətn tapılmadı")
    terms = engine.glossary(text)
    cur = c.execute("INSERT INTO materials(course_id,title,filename,text,chunk_count,term_count,uploaded_by,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (course_id, title, filename, text, len(parts), len(terms), user_id, created_at or iso(now())))
    mid = cur.lastrowid
    for seq, (heading, body) in enumerate(parts):
        cid = c.execute("INSERT INTO chunks(material_id,course_id,seq,heading,text) VALUES(?,?,?,?,?)",
                        (mid, course_id, seq, heading, body)).lastrowid
        engine.INDEX["chunks"].add(cid, body, {"course_id": course_id, "material_id": mid, "heading": heading,
                                                "material": title, "text": body}, boost=heading)
    return {"id": mid, "chunks": len(parts), "terms": len(terms), "chars": len(text),
            "headings": [h for h, _ in parts], "glossary": [t for t, _ in terms][:12]}


def delete_material(c, material_id):
    for r in rows(c, "SELECT id FROM chunks WHERE material_id=?", (material_id,)):
        engine.INDEX["chunks"].remove(r["id"])
    c.execute("DELETE FROM chunks WHERE material_id=?", (material_id,))
    c.execute("DELETE FROM materials WHERE id=?", (material_id,))


def index_question(q: dict):
    engine.INDEX["questions"].add(q["id"], f"{q['text']} {q.get('topic') or ''}",
                                  {"course_id": q["course_id"], "status": q["status"]})


def build_indexes(c):
    for k in engine.INDEX:
        engine.INDEX[k] = engine.BM25()
    for ch in rows(c, "SELECT ch.*, m.title AS material FROM chunks ch JOIN materials m ON m.id=ch.material_id"):
        engine.INDEX["chunks"].add(ch["id"], ch["text"], {"course_id": ch["course_id"], "material_id": ch["material_id"],
                                                          "heading": ch["heading"], "material": ch["material"],
                                                          "text": ch["text"]}, boost=ch["heading"])
    for kb in rows(c, "SELECT * FROM campus_kb"):
        engine.INDEX["campus"].add(kb["id"], kb["text"], {"heading": kb["heading"], "text": kb["text"],
                                                          "request": kb["request"], "action_label": kb["action_label"],
                                                          "material": kb["source"]}, boost=kb["heading"])
    for q in rows(c, "SELECT id, course_id, text, topic, status FROM questions"):
        index_question(q)


# ---------------------------------------------------------------- documents
_CODE_ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def issue_document(c, kind, holder_id, title, data, issued_by, prefix, request_id=None, issued_at=None) -> dict:
    when = issued_at or now()
    year = when.year
    seq = (row(c, "SELECT COUNT(*) AS n FROM documents WHERE reg_no LIKE ?", (f"AzTU-{prefix}-{year}-%",))["n"]) + 1
    reg_no = f"AzTU-{prefix}-{year}-{seq:06d}"
    while True:
        code = "".join(secrets.choice(_CODE_ALPHA) for _ in range(8))
        code = f"{code[:4]}-{code[4:]}"
        if not row(c, "SELECT 1 FROM documents WHERE verify_code=?", (code,)):
            break
    payload = json.dumps({"reg_no": reg_no, "title": title, "holder": holder_id, "data": data}, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    did = c.execute("INSERT INTO documents(kind,request_id,holder_id,title,reg_no,verify_code,data,hash,issued_by,issued_at,status)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,'valid')",
                    (kind, request_id, holder_id, title, reg_no, code, json.dumps(data, ensure_ascii=False), digest,
                     issued_by, iso(when))).lastrowid
    return row(c, "SELECT * FROM documents WHERE id=?", (did,))


def transcript_rows(c, user_id: int) -> list[dict]:
    """Deterministic synthetic grades of previous semesters for a student."""
    sems = setting(c, "past_semesters", [])
    rng = random.Random(user_id * 7919)
    out = []
    for s in sems:
        items = []
        for az, en, cr in s["courses"]:
            score = rng.randint(64, 98) if user_id != 1 else rng.randint(78, 98)
            items.append({"name": az, "name_en": en, "credits": cr, "score": score, "letter": letter(score)})
        out.append({"name": s["name"], "name_en": s["name_en"], "courses": items})
    return out


def letter(score: float) -> str:
    return "A" if score >= 91 else "B" if score >= 81 else "C" if score >= 71 else "D" if score >= 61 else "E" if score >= 51 else "F"


# ---------------------------------------------------------------- seeding
F_NAMES = "Aysel Leyla Günel Nərmin Sevinc Aytən Lalə Fidan Nigar Zəhra Aynur Səbinə Gülnar Kəmalə Ülviyyə Röya Nərgiz Aidə Mələk Fərqanə".split()
M_NAMES = "Murad Elvin Tural Orxan Kamran Nihad Fərid Elnur Ramil Ruslan Vüsal Səbuhi Anar Cavid Emil Kənan Toğrul Ayxan Nicat Rəşad".split()
SURN = ("Məmmədov Əliyev Həsənov Quliyev Hüseynov Abbasov Rzayev İsmayılov Babayev Süleymanov Cəfərov Nəsirov Kərimov "
        "Mustafayev Rəhimov Orucov Səfərov Bayramov Musayev Əhmədov").split()
COLORS = ["#1a2355", "#2b5aa8", "#5a9bd3", "#0e9f6e", "#d97706", "#ee7c7e", "#7c3aed", "#0891b2", "#db2777"]

SYNTH_Q = {
    "ELM-2105": [("Om qanunu nədir?", "Om qanunu"), ("Güc necə hesablanır?", "Elektrik gücü və enerji"),
                 ("Paralel birləşmədə müqavimət necə tapılır?", "Paralel birləşmə"),
                 ("Kirxhofun ikinci qanununda işarələr necə seçilir?", "Kirxhofun ikinci qanunu"),
                 ("Düyündə cərəyanların cəmi niyə sıfırdır?", "Kirxhofun birinci qanunu"), ("Zaman sabiti nəyi göstərir?", "Zaman sabiti"),
                 ("Effektiv qiymət nədir?", "Effektiv qiymət"), ("İnduktiv müqavimət necə hesablanır?", "Reaktiv müqavimətlər"),
                 ("mA-nı A-ə necə çevirim?", "Tipik səhvlər"), ("Transformatorun FİK-i necə hesablanır?", None)],
    "KOMP-1102": [("range(1, 5) niyə 5-i daxil etmir?", "for və while dövrləri"), ("Funksiya necə yazılır?", "Funksiyalar"),
                  ("Lüğətdə get() nə üçündür?", "Lüğətlər"), ("Siyahıya element necə əlavə olunur?", "Siyahılar"),
                  ("Faylı utf-8 ilə necə açım?", "Fayllarla iş"), ("Rekursiya nədir?", None)],
    "RİY-1101": [("Törəmənin həndəsi mənası nədir?", "Törəmənin həndəsi mənası"), ("Hasilin törəməsi necə tapılır?", "Əsas diferensiallama qaydaları"),
                 ("Nyuton–Leybnis düsturu nədir?", "Nyuton–Leybnis düsturu"), ("Mürəkkəb funksiyanın törəməsi nədir?", "Mürəkkəb funksiyanın törəməsi"),
                 ("Furye sırası nədir?", None)],
    "FİZ-1103": [("Bərabərtəcilli hərəkətin düsturları hansılardır?", "Bərabərtəcilli hərəkət"), ("Nyutonun ikinci qanunu nədir?", "Nyutonun ikinci qanunu"),
                 ("Sürtünmə qüvvəsi necə hesablanır?", "Sürtünmə qüvvəsi"), ("km/saat-ı m/s-ə necə çevirim?", "Tipik səhvlər"),
                 ("İmpulsun saxlanması qanunu nədir?", None)],
    "QRF-1104": [("Üst görünüş harada yerləşdirilir?", "Görünüşlərin yerləşdirilməsi"), ("Ştrix xətt nə vaxt istifadə olunur?", "Xətt növləri"),
                 ("Miqyas necə hesablanır?", "Miqyas"), ("Ölçü rəqəmi harada yazılır?", "Ölçülərin qoyulması qaydaları"), ("Aksonometriya nədir?", None)],
    "İNG-1105": [("“used to” və “used for” fərqi nədir?", "Describing function (Funksiyanı təsvir etmək)"),
                 ("3.5 kΩ necə oxunur?", "Saying numbers and units (Ədədlərin və vahidlərin oxunuşu)"),
                 ("How do I describe tolerances?", "Tolerances (Buraxılışlar)"), ("“consists of” necə işlədilir?", "Describing structure (Quruluşu təsvir etmək)")],
}


def _parse_kb(md: str):
    entries = []
    for block in re.split(r"^## ", md, flags=re.M)[1:]:
        lines = block.strip().splitlines()
        heading = lines[0].strip()
        meta = {}
        m = re.search(r"<!--(.*?)-->", block, flags=re.S)
        if m:
            for part in m.group(1).split("|"):
                if ":" in part:
                    k, v = part.split(":", 1)
                    meta[k.strip()] = v.strip()
        text = re.sub(r"<!--.*?-->", "", "\n".join(lines[1:]), flags=re.S).strip()
        entries.append((heading, text, meta.get("request"), meta.get("label"), meta.get("source", "Tələbə bələdçisi (demo)")))
    return entries


def semester_start(today: date) -> date:
    cands = [date(today.year, 9, 15), date(today.year, 2, 15), date(today.year - 1, 9, 15)]
    start = max(d for d in cands if d <= today)
    if (today - start).days < 14:
        start = today - timedelta(days=21)
    return start


def _load(name):
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


def seed(c):
    rng = random.Random(42)
    s = _load("seed.json")
    t0 = now()
    today = t0.date()
    for k in ("university", "faculty", "specialty", "demo_logins", "past_semesters"):
        set_setting(c, k, s[k])
    set_setting(c, "limits", {"daily_messages": 50, "pii_masking": True, "retention_days": 180, "socratic_default": True})
    sem0 = semester_start(today)
    set_setting(c, "semester_start", sem0.isoformat())

    gids = {g["name"]: c.execute("INSERT INTO study_groups(name,year) VALUES(?,?)", (g["name"], g["year"])).lastrowid for g in s["groups"]}
    uid = {}
    for u in s["users"]:
        uid[u["username"]] = c.execute(
            "INSERT INTO users(username,full_name,patronymic,role,title,group_id,color,student_no,admission_year,funding,form,dept)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (u["username"], u["full_name"], u.get("patronymic"), u["role"], u["title"], gids.get(u.get("group")), u["color"],
             u.get("student_no"), u.get("admission_year"), u.get("funding"), u.get("form"), u.get("dept"))).lastrowid
    students = [uid["aysel"]]
    used = {"Aysel Məmmədova"}
    while len(students) < 120:
        female = rng.random() < 0.45
        name = f"{rng.choice(F_NAMES if female else M_NAMES)} {rng.choice(SURN)}{'a' if female else ''}"
        if name in used:
            continue
        used.add(name)
        father = rng.choice(M_NAMES)
        students.append(c.execute(
            "INSERT INTO users(username,full_name,patronymic,role,title,group_id,color,consent_at,synthetic,student_no,admission_year,funding,form)"
            " VALUES(?,?,?,?,?,?,?,?,1,?,?,?,?)",
            (f"s{len(students):03d}", name, f"{father} {'qızı' if female else 'oğlu'}", "student", "Kompüter mühəndisliyi · 2-ci kurs",
             rng.choice(list(gids.values())), rng.choice(COLORS), iso(t0 - timedelta(days=15)), f"25-1{rng.randint(10000, 99999)}",
             2025, rng.choice(["Dövlət sifarişi", "Dövlət sifarişi", "Ödənişli"]), "Əyani")).lastrowid)
    depts = ["Elektronika", "Kompüter texnologiyaları", "Ali riyaziyyat", "Fizika", "Mühəndis qrafikası", "Xarici dillər"]
    teachers_synth = [c.execute("INSERT INTO users(username,full_name,role,title,color,synthetic,dept) VALUES(?,?,?,?,?,1,?)",
                                (f"t{i:02d}", f"{rng.choice(F_NAMES + M_NAMES)} {rng.choice(SURN)}", "teacher", "Müəllim",
                                 rng.choice(COLORS), depts[i % len(depts)])).lastrowid for i in range(18)]

    # ---- courses, materials, timetable, lessons
    course_ids, mats, chunk_by = {}, {}, {}
    for co in s["courses"]:
        cid = c.execute("INSERT INTO courses(code,name,teacher_id,credits,color,description,suggestions,tutor_modes,tutor_rules)"
                        " VALUES(?,?,?,?,?,?,?,?,?)",
                        (co["code"], co["name"], uid[co["teacher"]], co["credits"], co["color"], co["description"],
                         json.dumps(co["suggestions"], ensure_ascii=False), json.dumps(["socratic", "explain", "practice"]),
                         "Vahidləri həmişə SI sistemində göstər." if co["code"] == "ELM-2105" else "")).lastrowid
        course_ids[co["code"]] = cid
        c.executemany("INSERT INTO enrollments(user_id,course_id) VALUES(?,?)", [(st, cid) for st in students])
        mats[co["code"]] = []
        for i, (fname, title) in enumerate(co["materials"]):
            text = (CONTENT / "materials" / fname).read_text(encoding="utf-8")
            info = add_material(c, cid, title, fname, text, uid[co["teacher"]], iso(t0 - timedelta(days=16 - min(i * 5, 15))))
            mats[co["code"]].append(info["id"])
            for ch in rows(c, "SELECT id, heading FROM chunks WHERE material_id=?", (info["id"],)):
                chunk_by.setdefault((info["id"], re.sub(r"\s*\(\d+\)$", "", ch["heading"])), ch["id"])
        for wd, st_, en_, kind, room in co["schedule"]:
            c.execute("INSERT INTO timetable(course_id,weekday,start,end,kind,room) VALUES(?,?,?,?,?,?)", (cid, wd, st_, en_, kind, room))
    tt = rows(c, "SELECT t.*, co.code FROM timetable t JOIN courses co ON co.id=t.course_id")
    titles = {code: [m[1] for m in next(x for x in s["courses"] if x["code"] == code)["materials"]] for code in course_ids}
    lesson_count = {}
    d = sem0
    lessons = []
    while d < today:
        for t in tt:
            if t["weekday"] == d.isoweekday():
                n = lesson_count.get(t["course_id"], 0)
                lesson_count[t["course_id"]] = n + 1
                topics = titles[t["code"]]
                topic = topics[min(n // 3, len(topics) - 1)].split(". ", 1)[-1]
                lid = c.execute("INSERT INTO lessons(course_id,day,start,end,kind,room,topic) VALUES(?,?,?,?,?,?,?)",
                                (t["course_id"], d.isoformat(), t["start"], t["end"], t["kind"], t["room"], topic)).lastrowid
                lessons.append((lid, d, t["course_id"]))
        d += timedelta(days=1)
    # Demo student was ill on the last Monday and Tuesday before today.
    last_mon = today - timedelta(days=(today.isoweekday() - 1) or 7)
    if (today - last_mon).days < 2:
        last_mon -= timedelta(days=7)
    sick = {last_mon, last_mon + timedelta(days=1)}
    att = []
    for st in students:
        p_abs = 0.035 if st == uid["aysel"] else rng.choice([0.02, 0.04, 0.06, 0.09, 0.14])
        for lid, day, cid in lessons:
            if st == uid["aysel"]:
                status = "absent" if day in sick else ("late" if lid % 23 == 0 else "present")
            else:
                r = rng.random()
                status = "absent" if r < p_abs else "late" if r < p_abs + 0.03 else "present"
            att.append((lid, st, status))
    c.executemany("INSERT INTO attendance(lesson_id,user_id,status) VALUES(?,?,?)", att)
    # grades: current semester components
    gr = []
    for st in students:
        skill = rng.uniform(0.62, 0.97) if st != uid["aysel"] else 0.9
        for code, cid in course_ids.items():
            gr.append((st, cid, "Sərbəst iş 1", round(min(5, max(2, rng.gauss(5 * skill, 0.6))), 1), 5, iso(t0 - timedelta(days=4))))
            gr.append((st, cid, "Laboratoriya / məşğələ", round(min(10, max(4, rng.gauss(10 * skill, 1.1))), 1), 10, iso(t0 - timedelta(days=2))))
    c.executemany("INSERT INTO grades(user_id,course_id,component,score,max,updated_at) VALUES(?,?,?,?,?,?)", gr)

    for heading, text, req, label, source in _parse_kb((CONTENT / "campus_kb.md").read_text(encoding="utf-8")):
        c.execute("INSERT INTO campus_kb(heading,text,request,action_label,source) VALUES(?,?,?,?,?)", (heading, text, req, label, source))

    # ---- question bank & quizzes
    qids = []
    for q in s["question_bank"]:
        cid = course_ids[q["course"]]
        mid = mats[q["course"]][q["material"]]
        first = row(c, "SELECT id FROM chunks WHERE material_id=? ORDER BY seq", (mid,))["id"]
        qids.append(c.execute(
            "INSERT INTO questions(course_id,chunk_id,qtype,text,options,answer,unit,explanation,bloom,difficulty,topic,status,origin,flags,created_by,created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,'approved','manual','[]',?,?)",
            (cid, chunk_by.get((mid, q["topic"]), first), q["qtype"], q["text"], json.dumps(q.get("options", []), ensure_ascii=False),
             json.dumps(q["answer"]), q.get("unit", ""), q["explanation"], q["bloom"], q["difficulty"], q["topic"],
             row(c, "SELECT teacher_id FROM courses WHERE id=?", (cid,))["teacher_id"], iso(t0 - timedelta(days=12)))).lastrowid)
    quiz_ids = {}
    for i, qz in enumerate(s["quizzes"]):
        quiz_ids[qz["title"]] = c.execute(
            "INSERT INTO quizzes(course_id,title,kind,question_ids,time_limit,attempts,created_at) VALUES(?,?,?,?,?,?,?)",
            (course_ids[qz["course"]], qz["title"], qz["kind"], json.dumps([qids[k] for k in qz["questions"]]),
             qz["time_limit"], qz["attempts"], iso(t0 - timedelta(days=14 - i)))).lastrowid
    skill = {}
    for title, qzid in quiz_ids.items():
        qz = row(c, "SELECT * FROM quizzes WHERE id=?", (qzid,))
        if title.startswith("Kollokvium"):
            continue
        qlist = json.loads(qz["question_ids"])
        for st in rng.sample(students[1:], 85):
            skill.setdefault(st, rng.betavariate(5, 2.2))
            details = [{"qid": qid, "correct": rng.random() < min(0.97, skill[st] * (1.08 - 0.07 * k))} for k, qid in enumerate(qlist)]
            day = t0 - timedelta(days=rng.randint(1, 12), minutes=rng.randint(0, 600))
            c.execute("INSERT INTO attempts(quiz_id,user_id,answers,details,score,max_score,started_at,finished_at,synthetic) VALUES(?,?,?,?,?,?,?,?,1)",
                      (qzid, st, "{}", json.dumps(details), sum(d_["correct"] for d_ in details), len(qlist),
                       iso(day - timedelta(minutes=9)), iso(day)))
    for title, pattern in s["demo_attempts"]:
        qz = row(c, "SELECT * FROM quizzes WHERE id=?", (quiz_ids[title],))
        details = []
        for qid, ok in zip(json.loads(qz["question_ids"]), pattern):
            details.append({"qid": qid, "correct": ok, "topic": row(c, "SELECT topic FROM questions WHERE id=?", (qid,))["topic"]})
        day = t0 - timedelta(days=3, hours=qz["id"])
        c.execute("INSERT INTO attempts(quiz_id,user_id,answers,details,score,max_score,started_at,finished_at) VALUES(?,?,?,?,?,?,?,?)",
                  (qz["id"], students[0], "{}", json.dumps(details, ensure_ascii=False), sum(pattern), len(pattern),
                   iso(day - timedelta(minutes=8)), iso(day)))

    # ---- synthetic tutor usage
    msgs = []
    weights = {"ELM-2105": 520, "KOMP-1102": 380, "RİY-1101": 300, "FİZ-1103": 260, "QRF-1104": 170, "İNG-1105": 210}
    for code, items in SYNTH_Q.items():
        cid = course_ids[code]
        topic_chunk = {}
        for mid in mats[code]:
            for (m_, tp), chid in chunk_by.items():
                if m_ == mid:
                    topic_chunk.setdefault(tp, chid)
        for _ in range(weights[code]):
            text, topic = rng.choice(items)
            day = t0 - timedelta(days=int(55 * (1 - rng.random() ** 0.5)), minutes=rng.randint(0, 900))
            st = rng.choice(students[1:])
            chunk = topic_chunk.get(topic) if topic else None
            rating = rng.choices([1, -1, None], [0.31, 0.04, 0.65])[0]
            meta = json.dumps({"mode": rng.choice(["socratic", "socratic", "explain", "practice"]), "topic": topic,
                               "no_source": chunk is None}, ensure_ascii=False)
            msgs.append((st, cid, "tutor", "user", text, "[]", "{}", None, iso(day), 1))
            msgs.append((st, cid, "tutor", "assistant", "…", json.dumps([chunk] if chunk else []), meta, rating, iso(day + timedelta(seconds=4)), 1))
    c.executemany("INSERT INTO messages(user_id,course_id,channel,role,content,cites,meta,rating,created_at,synthetic) VALUES(?,?,?,?,?,?,?,?,?,?)", msgs)

    elm = course_ids["ELM-2105"]
    for st, q, anon, hrs in [(students[7], "Kirxhofun ikinci qanununda EHQ-nin işarəsini necə seçməliyəm? Laboratoriya işində nəticəm mənfi çıxdı.", 0, 5),
                             (students[23], "Ev tapşırığının 3-cü məsələsində paralel hissəni düzgün tapmışam, amma ümumi cərəyan uyğun gəlmir. Yoxlaya bilərsinizmi?", 1, 20),
                             (students[41], "RC dövrəsində kondensator boşalanda gərginlik hansı düsturla dəyişir? Materialda yalnız dolma var.", 0, 30)]:
        c.execute("INSERT INTO teacher_questions(course_id,student_id,anonymous,question,context,status,created_at) VALUES(?,?,?,?,?,'open',?)",
                  (elm, st, anon, q, "AI tutor söhbətindən göndərilib", iso(t0 - timedelta(hours=hrs))))

    # ---- e-services
    for i, cat in enumerate(s["service_categories"]):
        c.execute("INSERT INTO service_categories(key,seq,name,icon,color,text) VALUES(?,?,?,?,?,?)",
                  (cat["key"], i, cat["name"], cat["icon"], cat["color"], cat["text"]))
    for i, rt in enumerate(s["request_types"]):
        c.execute("INSERT INTO request_types(code,seq,category,name,icon,sla_hours,document,document_en,prefix,description,needs,outcome,"
                  "privacy,fields,attachments,steps,answer,popular) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (rt["code"], i, rt["category"], rt["name"], rt["icon"], rt["sla_hours"], rt.get("document"), rt.get("document_en"),
                   rt["prefix"], rt["description"], json.dumps(rt.get("needs", []), ensure_ascii=False), rt.get("outcome", ""),
                   rt.get("privacy", ""), json.dumps(rt["fields"], ensure_ascii=False), json.dumps(rt.get("attachments"), ensure_ascii=False),
                   json.dumps(rt["steps"], ensure_ascii=False), rt.get("answer", ""), 1 if rt.get("popular") else 0))
    rtypes = {rt["code"]: rt for rt in s["request_types"]}
    nigar = uid["nigar"]
    places = ["Hərbi komissarlıq", "Dövlət Sosial Müdafiə Fondu (DSMF)", "Bank", "İş yeri", "Səfirlik / viza"]

    def default_data(code, st):
        return {
            "enrollment_certificate": {"purpose": rng.choice(places), "purpose_other": "", "org": "", "lang": "Azərbaycan dili", "copies": "1", "delivery": "Elektron (QR kodlu PDF)"},
            "transcript": {"purpose": "Mübadilə proqramı (Erasmus+ və s.)", "lang": "İngilis dili", "scope": "Bütün semestrlər", "delivery": "Elektron (QR kodlu PDF)"},
            "absence_excuse": {"reason": "Xəstəlik", "period": {"from": (today - timedelta(days=9)).isoformat(), "to": (today - timedelta(days=8)).isoformat()}, "absences": [], "details": ""},
            "leave_permission": {"reason": "Olimpiada / müsabiqə", "period": {"from": (today + timedelta(days=5)).isoformat(), "to": (today + timedelta(days=6)).isoformat()},
                                 "courses": [course_ids["RİY-1101"], course_ids["FİZ-1103"]], "details": "Respublika tələbə riyaziyyat olimpiadasında iştirak"},
            "academic_leave": {"reason": "Səhhət", "period": "1 semestr", "start": "2026/2027 payız semestri", "details": "Uzunmüddətli müalicə tövsiyə olunub."},
            "grade_appeal": {"course": course_ids["KOMP-1102"], "exam_type": "Test", "score": "62", "details": "3-cü sualdakı cavabım düzgün qiymətləndirilməyib."},
            "dormitory": {"city": rng.choice(["Gəncə", "Şəki", "Lənkəran", "Quba", "Şamaxı"]), "basis": "Bölgədən gəlmişəm", "details": ""},
            "student_card": {"reason": "İtib", "details": ""},
            "free_application": {"to": "Dekanlıq", "subject": "Kurs layihəsinin mövzusunun dəyişdirilməsi", "body": "Kurs layihəsinin mövzusunu dəyişməyə icazə verməyinizi xahiş edirəm."},
        }[code]

    def make_request(st, code, status, hours_ago, step=0, data=None, attach=False):
        rt = rtypes[code]
        created = t0 - timedelta(hours=hours_ago)
        data = data or default_data(code, st)
        rid = c.execute("INSERT INTO requests(type_code,student_id,data,status,step,created_at,updated_at,due_at) VALUES(?,?,?,?,?,?,?,?)",
                        (code, st, json.dumps(data, ensure_ascii=False), status, step, iso(created), iso(created),
                         iso(created + timedelta(hours=rt["sla_hours"])))).lastrowid
        c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)", (rid, st, "submitted", "", iso(created)))
        if attach:
            stu = row(c, "SELECT full_name FROM users WHERE id=?", (st,))
            f = save_file(c, st, "hekim_arayisi.pdf", demo_pdf(["SINTETIK NUMUNE - REAL SENED DEYIL", "", "HEKIM ARAYISI (DEMO)",
                                                                engine.translit(stu["full_name"]), "Ambulator mualice tovsiye olunub."]),
                          when=created)
            c.execute("UPDATE files SET request_id=? WHERE id=?", (rid, f["id"]))
        if status in ("in_progress", "returned", "rejected"):
            act = {"in_progress": "approved", "returned": "returned", "rejected": "rejected"}[status]
            note = {"returned": "Təqdim ediləcəyi qurumun adını dəqiqləşdirin.", "rejected": "Eyni məzmunlu arayış artıq verilib."}.get(status, rt["steps"][0])
            c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)", (rid, nigar, act, note, iso(created + timedelta(hours=2))))
            if status == "returned":
                c.execute("INSERT INTO request_messages(request_id,author_id,text,created_at) VALUES(?,?,?,?)",
                          (rid, nigar, "Salam! Zəhmət olmasa, arayışın təqdim ediləcəyi qurumun tam adını yazın.", iso(created + timedelta(hours=2))))
        if status == "ready":
            issued = created + timedelta(hours=rng.uniform(2.5, 9))
            if rt.get("document"):
                stu = row(c, "SELECT * FROM users WHERE id=?", (st,))
                doc = issue_document(c, "request", st, rt["document"], {"type": code, **data, "student": stu["full_name"]}, nigar, rt["prefix"], rid, issued)
                c.execute("UPDATE requests SET document_id=? WHERE id=?", (doc["id"], rid))
            else:
                c.execute("UPDATE requests SET answer=? WHERE id=?", (rt.get("answer") or "Müraciətiniz təmin edildi.", rid))
            c.execute("UPDATE requests SET updated_at=?, step=? WHERE id=?", (iso(issued), len(rt["steps"]) - 1, rid))
            c.execute("INSERT INTO request_events(request_id,actor_id,action,note,created_at) VALUES(?,?,?,?,?)", (rid, nigar, "issued", "", iso(issued)))
        return rid

    aysel = uid["aysel"]
    r1 = make_request(aysel, "enrollment_certificate", "ready", 70, data={"purpose": "Bank", "purpose_other": "", "org": "Kapital Bank",
                                                                       "lang": "Azərbaycan dili", "copies": "1", "delivery": "Elektron (QR kodlu PDF)"})
    make_request(aysel, "transcript", "submitted", 3)
    pool = students[1:]
    for code, status, h, step, att_ in [("enrollment_certificate", "submitted", 30, 0, False), ("enrollment_certificate", "submitted", 6, 0, False),
                                        ("absence_excuse", "submitted", 20, 0, True), ("absence_excuse", "submitted", 4, 0, True),
                                        ("leave_permission", "submitted", 9, 0, False), ("academic_leave", "in_progress", 50, 1, True),
                                        ("grade_appeal", "submitted", 26, 0, False), ("dormitory", "submitted", 40, 0, False),
                                        ("student_card", "submitted", 2, 0, False), ("enrollment_certificate", "returned", 28, 0, False),
                                        ("transcript", "submitted", 12, 0, False), ("free_application", "submitted", 8, 0, False),
                                        ("transcript", "rejected", 90, 0, False)]:
        make_request(rng.choice(pool), code, status, h, step, attach=att_)
    for _ in range(18):
        make_request(rng.choice(pool), rng.choice(["enrollment_certificate"] * 4 + ["transcript", "free_application", "absence_excuse", "dormitory"]),
                     "ready", rng.randint(30, 600), attach=False)
    docs = rows(c, "SELECT id FROM documents ORDER BY id")
    if len(docs) > 4:
        c.execute("UPDATE documents SET status='revoked', revoked_reason=?, revoked_at=? WHERE id=?",
                  ("Məlumatlarda səhv aşkar edildi, yeni arayış verilib.", iso(t0 - timedelta(days=2)), docs[3]["id"]))

    # ---- academy
    ac = _load("academy.json")
    set_setting(c, "self_assessment", ac["self_assessment"])
    mod_by_track = {}
    for ti, tr in enumerate(ac["tracks"]):
        c.execute("INSERT INTO academy_tracks(key,seq,title,icon,color,level,audience,summary,outcomes) VALUES(?,?,?,?,?,?,?,?,?)",
                  (tr["key"], ti, tr["title"], tr["icon"], tr["color"], tr["level"], tr["audience"], tr["summary"], json.dumps(tr["outcomes"], ensure_ascii=False)))
        for mi, m in enumerate(tr["modules"], 1):
            mod_by_track.setdefault(tr["key"], []).append(c.execute(
                "INSERT INTO academy_modules(track_key,seq,title,minutes,paragraphs,key_points,phrases,task,link,quiz) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (tr["key"], mi, m["title"], m["minutes"], json.dumps(m["paragraphs"], ensure_ascii=False), json.dumps(m.get("key_points", []), ensure_ascii=False),
                 json.dumps(m.get("phrases", []), ensure_ascii=False), m["task"], m.get("link", ""), json.dumps(m["quiz"], ensure_ascii=False))).lastrowid)
    prog = []
    for i, mid in enumerate(mod_by_track["ai"][:5]):
        prog.append((uid["rauf"], mid, "completed", 100, iso(t0 - timedelta(days=30 - i * 5))))
    prog.append((uid["rauf"], mod_by_track["emi"][0], "completed", 100, iso(t0 - timedelta(days=3))))
    prog.append((uid["rauf"], mod_by_track["syllabus"][0], "completed", 50, iso(t0 - timedelta(days=2))))
    all_mods = [m for ms in mod_by_track.values() for m in ms]
    for t in [uid[k] for k in ("leyla", "elcin", "sebine", "tural", "gunel")] + teachers_synth:
        for mid in rng.sample(all_mods, rng.choice([0, 1, 2, 3, 4, 5, 6, 8, 10])):
            prog.append((t, mid, "completed", rng.choice([100, 100, 50]), iso(t0 - timedelta(days=rng.randint(2, 40)))))
    c.executemany("INSERT OR IGNORE INTO academy_progress(user_id,module_id,status,score,completed_at) VALUES(?,?,?,?,?)", prog)
    c.execute("UPDATE users SET prefs=? WHERE id=?", (json.dumps({"self_assessment": {"ai": 3, "emi": 2, "syllabus": 3, "communication": 4, "pedagogy": 3, "research": 2, "edtech": 2}}), uid["rauf"]))

    tl = _load("tools.json")
    set_setting(c, "tool_areas", tl["areas"])
    set_setting(c, "dept_areas", tl["dept_areas"])
    for i, t in enumerate(tl["tools"]):
        c.execute("INSERT INTO tools(key,seq,name,areas,type,pricing,platform,url,summary,use_cases,steps,lesson_idea) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  (t["key"], i, t["name"], json.dumps(t["areas"]), t["type"], t["pricing"], t["platform"], t["url"], t["summary"],
                   json.dumps(t["use_cases"], ensure_ascii=False), json.dumps(t["steps"], ensure_ascii=False), t["lesson_idea"]))
    for co in s["courses"]:
        for tk in co["tools"]:
            c.execute("INSERT INTO course_tools(course_id,tool_key,added_by,created_at) VALUES(?,?,?,?)",
                      (course_ids[co["code"]], tk, uid[co["teacher"]], iso(t0 - timedelta(days=10))))

    # ---- news
    nw = _load("news.json")
    set_setting(c, "news_kinds", nw["kinds"])
    news_ids = {}
    for n in nw["news"]:
        ev = n.get("event")
        start = end = None
        if ev:
            hh, mm = map(int, ev["time"].split(":"))
            start = datetime.combine(today + timedelta(days=ev["in_days"]), time(hh, mm))
            end = start + timedelta(hours=ev["duration_h"])
        pub = t0 - timedelta(days=n["days_ago"], hours=rng.randint(1, 6))
        nid = c.execute("INSERT INTO news(kind,title,summary,body,cover,author_id,audience,pinned,important,published_at,event_start,event_end,"
                        "location,capacity,registration,tags) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (n["kind"], n["title"], n["summary"], n["body"], json.dumps(n["cover"]), uid["rektorluq"], n["audience"],
                         1 if n["pinned"] else 0, 1 if n["important"] else 0, iso(pub), iso(start) if start else None, iso(end) if end else None,
                         ev["location"] if ev else None, ev["capacity"] if ev else None, 1 if ev and ev["registration"] else 0,
                         json.dumps(n["tags"], ensure_ascii=False))).lastrowid
        news_ids[n["title"]] = nid
        if ev and ev["registration"]:
            cap = ev["capacity"] or 50
            for st in rng.sample(pool, min(len(pool), int(cap * rng.uniform(0.25, 0.6)))):
                c.execute("INSERT OR IGNORE INTO news_rsvp(news_id,user_id,created_at) VALUES(?,?,?)", (nid, st, iso(pub + timedelta(hours=rng.randint(1, 40)))))
        for st in rng.sample(pool, rng.randint(20, 90)):
            c.execute("INSERT OR IGNORE INTO news_reads(news_id,user_id) VALUES(?,?)", (nid, st))
    for title in list(news_ids)[7:]:
        c.execute("INSERT OR IGNORE INTO news_reads(news_id,user_id) VALUES(?,?)", (news_ids[title], aysel))

    # ---- notifications
    hack = next(k for k in news_ids if "Hakaton" in k)
    sick_s = f"{min(sick):%d.%m}–{max(sick):%d.%m}"
    notify(c, aysel, "attendance", T3("{dates} tarixlərində 6 qayıbınız qeydə alınıb", dates=sick_s),
           T3("Üzrlü səbəbiniz varsa, təsdiqedici sənədi yükləyin — qayıblar üzrlü hesab ediləcək."), "/student/attendance", t0 - timedelta(hours=20))
    notify(c, aysel, "news", T3("Hakaton: “AzTU AI Challenge 2026” — qeydiyyat açıqdır"), T3("Komandanızla qoşulun, yerlərin sayı məhduddur."),
           f"/news/{news_ids[hack]}", t0 - timedelta(days=2, hours=20))
    notify(c, aysel, "quiz", T3("Yeni test: {title}", title="Məşq: Sinusoidal cərəyan"), T3("{course} · {n} sual", course=tr3("Elektrik dövrələrinin nəzəriyyəsi"), n=4),
           "/student/quizzes", t0 - timedelta(days=2))
    notify(c, aysel, "request", T3("Arayışınız hazırdır"), T3("Təhsil aldığını təsdiq edən arayış (bank üçün)"), f"/student/requests/{r1}", t0 - timedelta(hours=64), read=True)
    notify(c, uid["rauf"], "question", T3("{n} yeni tələbə sualı", n=3), T3("AI tutordan müəllimə yönləndirilmiş suallar"), "/teacher/questions", t0 - timedelta(hours=5))
    notify(c, uid["rauf"], "academy", T3("AI Akademiya: sertifikata 1 modul qalıb"), T3("“Təhsildə süni intellekt” istiqaməti"), "/teacher/academy", t0 - timedelta(days=1))
    notify(c, nigar, "request", T3("Yeni müraciətlər"), T3("Bu gün {n} yeni müraciət daxil olub", n=4), "/office", t0 - timedelta(hours=2))
    notify(c, nigar, "sla", T3("{n} müraciətin icra müddəti keçib", n=2), T3("Növbədə qırmızı rənglə işarələnib"), "/office", t0 - timedelta(hours=1))
    notify(c, uid["rektorluq"], "report", T3("Həftəlik pilot hesabatı hazırdır"), T3("Göstəricilərin {n}-si hədəfdədir", n=7), "/leader", t0 - timedelta(hours=8))
    from . import support
    support.seed(c, uid, t0)
    audit(c, None, "seed", "system", "Demo məlumatları yaradıldı")


SCHEMA_VERSION = 3


def init(reset: bool = False):
    DATA.mkdir(exist_ok=True)
    if not reset and DB_PATH.exists():
        try:
            probe = sqlite3.connect(DB_PATH)
            reset = probe.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION
            probe.close()
        except sqlite3.Error:
            reset = True
    if reset and DB_PATH.exists():
        for p in (DB_PATH, DB_PATH.with_suffix(".db-wal"), DB_PATH.with_suffix(".db-shm")):
            if p.exists():
                p.unlink()
    c = connect()
    c.executescript(SCHEMA)
    if not row(c, "SELECT 1 FROM users LIMIT 1"):
        seed(c)
        c.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        c.commit()
    build_indexes(c)
    c.close()


def reseed():
    c = connect()
    for t in [r["name"] for r in rows(c, "SELECT name FROM sqlite_master WHERE type='table'")]:
        c.execute(f'DELETE FROM "{t}"')
    seed(c)
    c.commit()
    build_indexes(c)
    c.close()
