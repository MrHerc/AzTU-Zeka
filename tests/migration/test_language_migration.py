"""0464 (Checkpoint F, M1): a database seeded before the language review gets the renamed seeded texts, so en and ru
readers no longer see the old Azerbaijani; a text someone wrote is left alone, and a fresh seed needs no rewrite.
0465 (M1's leftovers): the rows that carry their own texts, the same way."""
import json
from pathlib import Path

from zeka.core import i18n
from zeka.legacy import store

SQL = Path(__file__).resolve().parents[2] / "backend" / "migrations" / "0464_language_review.sql"
OLD = {("support_tickets", "subject", "Profildə köhnə qrupum göstərilir"): "Profildə qrupum köhnə göstərilir",
       ("support_tickets", "subject", "Kampus köməkçisi təqaüd sualıma cavab vermədi"): "Kampus köməkçisi təqaüd barədə",
       ("support_tickets", "body", "Elektrik dövrələri fənnində tutorun cavabındakı [2] mənbəyinə klik etdikdə pəncərə açılmır."):
           "Elektrik dövrələri fənnində tutorun cavabındakı [2] mənbəsinə klik edəndə pəncərə açılmır.",
       ("support_tickets", "body", "«Dəyişən cərəyan» mühazirəsini PPTX formatında yüklədim, amma bəzi slaydların mətni tutorda görünmür."):
           "“Dəyişən cərəyan” mühazirəsini PPTX formatında yüklədim, amma bəzi slaydların mətni tutorda görünmür.",
       ("support_messages", "text", "Sorğunuz qəbul olundu, araşdırırıq."): "Müraciətiniz qəbul olundu, araşdırırıq.",
       ("academy_tracks", "level", "Başlanğıc səviyyə"): "Başlanğıc",
       ("academy_tracks", "level", "Orta səviyyə"): "Orta"}


def test_0464_brings_the_seeded_texts_of_an_older_database_to_the_catalogue(db):
    for (table, col, new), old in OLD.items():          # the database as the seed before the review wrote it
        assert db.execute(f"UPDATE {table} SET {col}=? WHERE {col}=?", (old, new)).rowcount, (table, new)  # nosec B608
    mine = db.execute("INSERT INTO support_messages(ticket_id, author_id, text, created_at) VALUES(1, 1, 'Müraciətiniz qəbul olundu, "
                      "araşdırırıq. Sabah zəng edəcəyik.', '2026-11-19')").lastrowid
    db.executescript(SQL.read_text(encoding="utf-8"))
    for (table, col, new), old in OLD.items():
        assert not db.execute(f"SELECT 1 FROM {table} WHERE {col}=?", (old,)).fetchone(), (table, old)  # nosec B608
        assert db.execute(f"SELECT 1 FROM {table} WHERE {col}=?", (new,)).fetchone(), (table, new)  # nosec B608
    assert db.execute("SELECT text FROM support_messages WHERE id=?", (mine,)).fetchone()[0].endswith("Sabah zəng edəcəyik.")


def test_every_seeded_support_text_is_a_catalogue_key(db):
    """What made M1 visible: a seeded subject, body or reply that is no catalogue key shows in Azerbaijani in en and ru."""
    for table, cols in (("support_tickets", ("subject", "body")), ("support_messages", ("text",))):
        for r in store.rows(db, f"SELECT {', '.join(cols)} FROM {table}"):  # nosec B608
            for col in cols:
                if r[col]:
                    assert i18n.localize({col: r[col]}, "en")[col] != r[col], (table, col, r[col][:60])


# 0465: (table, column, the fresh seed's text, what a database seeded before the language change holds there). A JSON
# column is matched on a part of its text; the notifications and plans keep az, en and ru together.
SQL65 = SQL.with_name("0465_language_rows.sql")
ROWS65 = [
    ("notifications", "title", '"az": "Hakaton: «AzTU AI Challenge 2026» — qeydiyyat açıqdır"',
     '"az": "Hakaton: “AzTU AI Challenge 2026” — qeydiyyat açıqdır"'),
    ("notifications", "body", '"az": "«Təhsildə süni intellekt» istiqaməti"', '"az": "“Təhsildə süni intellekt” istiqaməti"'),
    ("notifications", "body", '{"az": "7 göstərici hədəfə çatıb", "en": "7 indicators are on target", "ru": "7 показателей достигли целевого значения"}',
     '{"az": "Göstəricilərin 7-si hədəfdədir", "en": "7 of the indicators are on target", "ru": "7 из показателей достигли цели"}'),
    ("interventions", "plan", "sənədi E-xidmətlər bölməsində yükləyin — qayıb üzrlü hesab ediləcək.",
     "sənədi E-xidmətlərdən yükləyin — qayıb üzrlü sayılacaq."),
    ("interventions", "plan", "Если у вас была уважительная причина, загрузите подтверждающий документ в разделе «Электронные услуги» — "
     "пропуск будет признан уважительным.",
     "Если причина была уважительной, загрузите подтверждающий документ в электронных услугах — пропуск будет засчитан как уважительный."),
    ("requests", "answer", "Zəka platformasında başqa heç bir qeyd dəyişdirilməyib.", "Zəka-da başqa heç bir qeyd dəyişməyib."),
    ("courses", "suggestions", '"«used to» və «used for» fərqi nədir?"', '"“used to” və “used for” fərqi nədir?"'),
    ("courses", "suggestions", '"«consists of» necə işlədilir?"', '"“consists of” necə işlədilir?"'),
    ("messages", "content", "«used to» və «used for» fərqi nədir?", "“used to” və “used for” fərqi nədir?"),
    ("messages", "content", "«consists of» necə işlədilir?", "“consists of” necə işlədilir?"),
    ("questions", "explanation", "«is used to» quruluşundan", "“is used to” quruluşundan"),
    ("questions", "text", "«The circuit ___ a battery, a switch and two resistors.»", "“The circuit ___ a battery, a switch and two resistors.”"),
    ("questions", "explanation", "«consists of» quruluşu düzgündür:", "Düzgün quruluş “consists of”-dur:"),
    ("questions", "text", "«25 ± 0.05 mm» necə", "“25 ± 0.05 mm” necə"),
    ("questions", "explanation", "± işarəsi «plus or minus», 0.05 isə «zero point zero five» kimi oxunur.",
     "± işarəsi “plus or minus”, 0.05 isə “zero point zero five” oxunur."),
    ("questions", "explanation", "variantlar: «The shaft is 40 mm long» və ya «The shaft has a length of 40 mm».",
     "variantlar: “The shaft is 40 mm long” və ya “The shaft has a length of 40 mm”."),
]
TABLES65 = {"notifications": ("title", "body"), "interventions": ("plan",), "requests": ("answer",), "courses": ("suggestions",),
            "messages": ("content",), "questions": ("text", "explanation")}


def _snapshot(db):
    return {t: db.execute(f"SELECT id, {', '.join(cols)} FROM {t} ORDER BY id").fetchall() for t, cols in TABLES65.items()}  # nosec B608


def test_0465_brings_an_older_databases_rows_to_the_fresh_seed_and_leaves_what_people_wrote(db):
    fresh = _snapshot(db)
    for table, col, new, old in ROWS65:                  # the rows as a seed before the language change wrote them
        assert db.execute(f"UPDATE {table} SET {col}=replace({col}, ?, ?) WHERE instr({col}, ?)", (new, old, new)).rowcount, (table, new)  # nosec B608
    assert db.execute("UPDATE questions SET text='Doğrudurmu: “' || substr(text, 14, length(text) - 15) || '.”' "  # «X». was “X.”
                      "WHERE text LIKE 'Doğrudurmu: «%».'").rowcount >= 9
    assert db.execute("UPDATE messages SET content=replace(replace(content, '«', '“'), '»', '”') WHERE synthetic=1 AND role='assistant' "
                      "AND instr(content, 'Materialda deyilir: «')").rowcount
    # a question a teacher edited and a message a student typed hold the old wording too: they stay as written
    mine = {"questions": db.execute("INSERT INTO questions(course_id, qtype, text, explanation, status, origin) VALUES(1, 'tf', "
                                    "'Doğrudurmu: “Tezlik artdıqca induktiv müqavimət azalır.” (redaktə)', '', 'draft', 'manual')").lastrowid,
            "messages": db.execute("INSERT INTO messages(user_id, course_id, channel, role, content, synthetic) VALUES(1, 1, 'tutor', 'user', "
                                   "'“consists of” necə işlədilir?', 0)").lastrowid}
    # MUT-l03: the tutor's real answer to a person, from a version that wrote “ ”, is that person's history and stays
    real = db.execute("INSERT INTO messages(user_id, course_id, channel, role, content, synthetic) VALUES(1, 1, 'tutor', 'assistant', "
                      "'Materialda deyilir: “Om qanunu”. [1]', 0)").lastrowid
    written = {t: db.execute(f"SELECT * FROM {t} WHERE id=?", (i,)).fetchone() for t, i in mine.items()}  # nosec B608
    assert _snapshot(db) != fresh
    db.executescript(SQL65.read_text(encoding="utf-8"))
    after = _snapshot(db)
    for t in TABLES65:
        assert [r for r in after[t] if r[0] != mine.get(t) and (t, r[0]) != ("messages", real)] == fresh[t], t
    for t, i in mine.items():
        assert db.execute(f"SELECT * FROM {t} WHERE id=?", (i,)).fetchone() == written[t], t  # nosec B608
    assert db.execute("SELECT content FROM messages WHERE id=?", (real,)).fetchone()[0] == "Materialda deyilir: “Om qanunu”. [1]"


def _az(v):
    """The Azerbaijani strings of a column: a plain text, or every "az" value (and every string of a list) inside JSON."""
    try:
        v = json.loads(v)
    except ValueError:
        return [v]
    if isinstance(v, dict):
        return ([v["az"]] if isinstance(v.get("az"), str) else []) + [s for x in v.values() if isinstance(x, (dict, list)) for s in _az(json.dumps(x))]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)] + [s for x in v if isinstance(x, (dict, list)) for s in _az(json.dumps(x))]
    return [v] if isinstance(v, str) else []


def test_seeded_azerbaijani_texts_use_the_style_guides_quotes(db):
    """i18n/STYLE.md: «» in Azerbaijani text, “ ” only in English (the en values beside it may hold them)."""
    for t, cols in TABLES65.items():
        for r in db.execute(f"SELECT {', '.join(cols)} FROM {t}"):  # nosec B608
            for v in r:
                for s in _az(v) if v else []:
                    assert "“" not in s and "”" not in s, (t, s[:80])
