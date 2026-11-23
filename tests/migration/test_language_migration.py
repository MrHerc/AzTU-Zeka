"""0464 (Checkpoint F, M1): a database seeded before the language review gets the renamed seeded texts, so en and ru
readers no longer see the old Azerbaijani; a text someone wrote is left alone, and a fresh seed needs no rewrite."""
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
