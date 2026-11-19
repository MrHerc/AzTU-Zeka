"""Schema migration engine (backend/zeka/core/migrate.py) and its use by store.init() (tasks/todo.md, Task 4)."""
import sqlite3

import pytest

from zeka.core import migrate
from zeka.legacy import store


@pytest.fixture
def mdir(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    return d


@pytest.fixture
def conn(tmp_path):
    c = sqlite3.connect(tmp_path / "t.db")
    yield c
    c.close()


def put(d, name, sql):
    (d / name).write_text(sql, encoding="utf-8")


ALL = [v for v, _, _ in migrate.discover()]      # every file in backend/migrations


def versions(c):
    return [r[0] for r in c.execute("SELECT version FROM schema_migrations ORDER BY version")]


def test_applies_in_number_order_once(conn, mdir):
    put(mdir, "0001_a.sql", "CREATE TABLE a(x);")
    put(mdir, "0030_c.sql", "ALTER TABLE a ADD COLUMN y;")
    assert migrate.apply(conn, mdir) == [1, 30]
    assert migrate.apply(conn, mdir) == []
    assert versions(conn) == [1, 30]


def test_a_lower_number_added_later_is_applied(conn, mdir):
    put(mdir, "0001_a.sql", "CREATE TABLE a(x);")
    put(mdir, "0030_c.sql", "CREATE TABLE c(x);")
    migrate.apply(conn, mdir)
    put(mdir, "0020_b.sql", "CREATE TABLE b(x);")
    assert migrate.apply(conn, mdir) == [20]
    assert versions(conn) == [1, 20, 30]


def test_an_edited_applied_file_refuses(conn, mdir):
    put(mdir, "0001_a.sql", "CREATE TABLE a(x);")
    migrate.apply(conn, mdir)
    put(mdir, "0001_a.sql", "CREATE TABLE a(x, y);")
    with pytest.raises(migrate.MigrationError, match="edited"):
        migrate.apply(conn, mdir)


def test_a_database_newer_than_the_code_refuses(conn, mdir):
    put(mdir, "0001_a.sql", "CREATE TABLE a(x);")
    put(mdir, "0002_b.sql", "CREATE TABLE b(x);")
    migrate.apply(conn, mdir)
    (mdir / "0002_b.sql").unlink()
    with pytest.raises(migrate.MigrationError, match="newer than the code"):
        migrate.status(conn, mdir)


@pytest.mark.parametrize("names", [("0001_a.sql", "0001_b.sql"), ("1_a.sql",), ("0001_A.sql",)])
def test_duplicate_numbers_and_bad_names_refuse(conn, mdir, names):
    for n in names:
        put(mdir, n, "SELECT 1;")
    with pytest.raises(migrate.MigrationError):
        migrate.apply(conn, mdir)


def test_a_failing_migration_leaves_no_trace(conn, mdir):
    put(mdir, "0001_a.sql", "CREATE TABLE a(x);")
    put(mdir, "0002_b.sql", "CREATE TABLE b(x);\nINSERT INTO missing VALUES(1);")
    with pytest.raises(migrate.MigrationError, match="rolled back"):
        migrate.apply(conn, mdir)
    assert versions(conn) == [1]
    assert conn.execute("SELECT 1 FROM sqlite_master WHERE name='b'").fetchone() is None


def test_a_copy_is_saved_before_pending_files_and_only_five_are_kept(conn, mdir, tmp_path):
    backups = tmp_path / "backups"
    put(mdir, "0001_a.sql", "CREATE TABLE a(x);")
    migrate.apply(conn, mdir, backup_dir=backups)
    assert not backups.exists()                     # an empty database has nothing to save
    conn.execute("INSERT INTO a VALUES(42)")
    conn.commit()
    for n in range(2, 9):
        put(mdir, f"{n:04d}_m{n}.sql", f"CREATE TABLE t{n}(x);")
        migrate.apply(conn, mdir, backup_dir=backups)
    kept = sorted(backups.glob("pre-*.db"))
    assert len(kept) == migrate.KEEP_BACKUPS
    assert [k.name[:8] for k in kept] == ["pre-0004", "pre-0005", "pre-0006", "pre-0007", "pre-0008"]   # the newest five
    copy = sqlite3.connect(kept[-1])
    try:
        assert copy.execute("SELECT x FROM a").fetchall() == [(42,)]
        assert copy.execute("SELECT 1 FROM sqlite_master WHERE name='t8'").fetchone() is None   # saved before 0008
    finally:
        copy.close()


def _counts(c):
    names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name<>'schema_migrations'")]
    return {t: c.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in names}  # nosec B608


def _to_baseline(c):
    """Turn a current database into one from before the migration engine: the 0001 schema with its rows, no log."""
    base = sqlite3.connect(":memory:")
    base.executescript((migrate.DIR / "0001_baseline.sql").read_text(encoding="utf-8"))
    keep = set(base.execute("SELECT type, name FROM sqlite_master"))
    columns = {t: {r[1] for r in base.execute(f'PRAGMA table_info("{t}")')} for kind, t in keep if kind == "table"}
    create = dict(base.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"))
    base.close()
    for t, allowed in columns.items():                    # a table a later migration rebuilt: back to its old, empty form
        now_cols = {r[1] for r in c.execute(f'PRAGMA table_info("{t}")')}
        if not allowed <= now_cols:
            c.execute(f'DROP TABLE "{t}"')
            c.execute(create[t])
    have = c.execute("SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    for kind in ("index", "table"):                       # later indexes first: one of them uses a later column
        for k, name in have:
            if k == kind and (k, name) not in keep:
                c.execute(f'DROP {kind.upper()} "{name}"')
    for t, allowed in columns.items():
        for col in [r[1] for r in c.execute(f'PRAGMA table_info("{t}")') if r[1] not in allowed]:
            c.execute(f'ALTER TABLE "{t}" DROP COLUMN "{col}"')
    c.execute(f"PRAGMA user_version={store.LEGACY_SCHEMA_VERSION}")
    c.commit()


def test_a_demo_database_from_before_the_engine_keeps_every_row(db):
    _to_baseline(db)
    before = _counts(db)
    db.close()
    store.init()
    c = store.connect()
    try:
        assert {t: n for t, n in _counts(c).items() if t in before} == before and sum(before.values()) > 1000
        assert versions(c) == ALL
    finally:
        c.close()


def test_a_demo_reset_keeps_the_migration_log(db):
    store.reseed()
    assert versions(db) == ALL


def test_init_refuses_a_database_newer_than_the_code(db):
    db.execute("INSERT INTO schema_migrations VALUES(9990, 'future', 'x', '2030-01-01T00:00:00')")
    db.commit()
    with pytest.raises(migrate.MigrationError, match="newer than the code"):
        store.init()


def test_0450_starts_each_registry_sequence_after_the_largest_issued_number(tmp_path, mdir):
    """Checkpoint C, D4: the back-fill of doc_sequences from the registry numbers issued before Task 45."""
    for v, _, path in migrate.discover():
        if v < 450:
            put(mdir, path.name, path.read_text(encoding="utf-8"))
    c = sqlite3.connect(tmp_path / "seq.db")
    try:
        migrate.apply(c, mdir)
        for reg in ("AzTU-ARY-2026-000007", "AzTU-ARY-2026-000003", "AzTU-ARY-2025-000003", "AzTU-TRN-2026-000012", "zibil", "AzTU-ARY-2026-12"):
            c.execute("INSERT INTO documents(kind,title,reg_no,verify_code,data,hash,issued_at,status) VALUES('request','x',?,?,'{}','',"
                      "'2026-01-01','valid')", (reg, reg))
        c.commit()
        src = next(p for v, _, p in migrate.discover() if v == 450)
        put(mdir, src.name, src.read_text(encoding="utf-8"))
        migrate.apply(c, mdir)
        got = {(p, y): n for p, y, n in c.execute("SELECT prefix, year, last_no FROM doc_sequences")}
        assert got == {("AzTU-ARY", 2026): 7, ("AzTU-ARY", 2025): 3, ("AzTU-TRN", 2026): 12}, got   # the key issue_document uses
    finally:
        c.close()
