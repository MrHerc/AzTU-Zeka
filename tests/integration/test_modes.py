"""Run modes (tasks/todo.md, Task 5): demo routes do not exist in prod, prod never seeds people nor deletes data."""
import subprocess
import sys
from pathlib import Path

import pytest

import manage
from zeka.core import config, migrate
from zeka.legacy import store

ROOT = Path(__file__).resolve().parents[2]
DEMO_ONLY = [("POST", "/api/auth/demo"), ("GET", "/demo/login"), ("GET", "/api/demo/storyline"), ("POST", "/api/admin/reset")]


@pytest.fixture
def prod(monkeypatch):
    monkeypatch.setattr(config, "MODE", "prod")


@pytest.mark.parametrize("method, path", DEMO_ONLY)
def test_demo_routes_do_not_exist_in_prod(anon, prod, method, path):
    r = anon.request(method, path, {} if method == "POST" else None)
    assert r.status == 404, (path, r.status)


@pytest.mark.parametrize("method, path", DEMO_ONLY)
def test_demo_routes_exist_in_demo(anon, method, path):
    assert anon.request(method, path, {} if method == "POST" else None).status != 404


def test_bootstrap_reports_the_mode(anon, prod):
    assert anon.get("/api/bootstrap").json["app"]["mode"] == "prod"


def test_empty_prod_database_has_the_catalogue_and_no_people(prod):
    store.DB_PATH.unlink(missing_ok=True)
    for p in (store.DB_PATH.with_suffix(".db-wal"), store.DB_PATH.with_suffix(".db-shm")):
        p.unlink(missing_ok=True)
    store.init()
    c = store.connect()
    try:
        assert store.row(c, "SELECT COUNT(*) n FROM users")["n"] == 0
        assert store.setting(c, "university")["short"] == "AzTU"
        assert store.row(c, "SELECT COUNT(*) n FROM request_types")["n"] == 13
        assert store.row(c, "SELECT COUNT(*) n FROM courses")["n"] == 0
    finally:
        c.close()
    assert manage.main(["create-admin", "--username", "it.admin", "--name", "İT Mərkəzi Admin"]) == 0
    assert manage.main(["create-admin", "--username", "it.admin", "--name", "Again"]) == 2
    c = store.connect()
    try:
        assert [(u["username"], u["role"], u["synthetic"]) for u in store.rows(c, "SELECT * FROM users")] == [("it.admin", "admin", 0)]
    finally:
        c.close()
    store.init(reset=False)                    # a restart keeps the account and seeds nothing


def test_prod_never_deletes_the_database(prod):
    with pytest.raises(migrate.MigrationError, match="never deletes"):
        store.init(reset=True)


def test_create_admin_is_refused_in_demo(capsys):
    assert manage.main(["create-admin", "--username", "x.admin", "--name", "Someone"]) == 2
    assert "ZEKA_MODE=prod" in capsys.readouterr().err


def _run(env, *args):
    base = {"PATH": "/usr/bin:/bin", "PYTHONIOENCODING": "utf-8", "SYSTEMROOT": ""}
    p = subprocess.run([sys.executable, str(ROOT / "backend" / "run.py"), *args], env={**base, **env}, capture_output=True, timeout=120)
    return p.returncode, p.stderr.decode("utf-8", "replace")


@pytest.mark.slow
@pytest.mark.parametrize("env, args, needle", [
    ({}, ("--host", "0.0.0.0"), "demo rejimi şəbəkəyə açılmır"),
    ({"ZEKA_MODE": "prod", "PUBLIC_URL": "https://zeka.example.az"}, (), "ZEKA_PROXY_HOPS=0"),
    ({"ZEKA_MODE": "prod"}, ("--reset",), "--reset qadağandır"),
    ({"ZEKA_MODE": "staging"}, (), "yalnız demo və ya prod"),
])
def test_unsafe_start_up_is_refused(env, args, needle):
    code, err = _run(env, *args)
    assert code == 2 and needle in err, err[-400:]
