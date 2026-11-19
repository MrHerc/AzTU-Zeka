"""Every write endpoint answers malformed input with a 4xx — never a 500.

Before the fix 28 of the POST/PUT routes crashed when a field had the wrong JSON type: ``int("abc")`` on a capacity,
``[].strip()`` on a message, a list used as an SQL parameter, ``x in some_set`` with an unhashable value…
The field names are collected from the route modules' source, so new fields are covered automatically.
"""
import inspect
import json
import re
import sys

import pytest

from zeka.legacy import api

WEIRD = ["abc", "", 1.5, -1, 10 ** 30, True, None, [], ["x"], {}, {"a": 1}]
SKIP = {"logout", "admin_reset", "temporary_password", "mfa_reset"}   # end the shared sessions, reseed, force a change
_FIELD = re.compile(r'(?:\bb|body|raw|req\.json\(\))\.(?:get|text|integer|number|array|ids|obj)\("(\w+)"|\bb\["(\w+)"\]')


def _routes():
    out = []
    for method, rx, fn, roles, _auth in api.R.routes:
        if method not in ("POST", "PUT") or fn.__name__ in SKIP:
            continue
        path = re.sub(r"\(\?P<\w+>\[0-9\]\+\)", "1", rx.pattern.strip("^$"))
        path = re.sub(r"\(\?P<\w+>\[\^/\]\+\)", "x", path)
        src = inspect.getsource(sys.modules[fn.__module__])
        fields = sorted({a or b for a, b in _FIELD.findall(src)} | {"x"})
        out.append(pytest.param(method, path, (roles or ("student", "office"))[0], fields, id=f"{method} {path}"))
    return out


@pytest.fixture(scope="module")
def clients(app_db):
    out = {r: app_db.client(r) for r in ("student", "teacher", "office", "leader", "admin")}
    out["admin"].post(f"/api/admin/users/{out['office'].user['id']}/roles", {"role": "academic_office"})
    registrar = app_db.client("office")            # a granted role (Task 13): the academic office's routes are fuzzed too
    assert registrar.post("/api/me/role", {"role": "academic_office"}).status == 200
    out["admin"].post(f"/api/admin/users/{out['teacher'].user['id']}/roles", {"role": "dept_head"})
    head = app_db.client("teacher")                # and a department head's (Task 20)
    assert head.post("/api/me/role", {"role": "dept_head"}).status == 200
    out["admin"].post(f"/api/admin/users/{out['leader'].user['id']}/roles", {"role": "proctor"})
    proctor = app_db.client("leader")              # and an exam proctor's (Task 29)
    assert proctor.post("/api/me/role", {"role": "proctor"}).status == 200
    return {**out, "academic_office": registrar, "dept_head": head, "proctor": proctor}


@pytest.mark.parametrize("method, path, role, fields", _routes())
def test_wrongly_typed_fields_never_crash(clients, method, path, role, fields):
    crashes = []
    for field in fields:
        for value in WEIRD:
            r = clients[role].request(method, path, {field: value})
            if r.status >= 500:
                crashes.append(f"{field}={json.dumps(value)} -> {r.status}")
    assert not crashes, crashes


@pytest.mark.parametrize("body", [[1, 2], "text", 5, None])
def test_non_object_json_bodies_are_400(clients, body):
    r = clients["student"].request("POST", "/api/feedback", raw=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    assert r.status == 400


def test_typed_errors_name_the_field_and_are_translated(clients):
    r = clients["teacher"].post("/api/studio/generate", {"course_id": 1, "count": "many"}, lang="en")
    assert r.status == 400 and r.json["error"] == "Invalid value: count"
    r = clients["teacher"].post("/api/studio/generate", {"course_id": 1, "count": "many"}, lang="ru")
    assert r.json["error"] == "Недопустимое значение: count"


def test_numeric_strings_are_still_accepted(clients):
    # the frontend sends some numbers as strings (form inputs); those keep working
    r = clients["teacher"].post("/api/syllabus/1/generate", {"weeks": "12"})
    assert r.status == 200 and len(r.json["plan"]) == 12
    r = clients["teacher"].post("/api/studio/generate", {"course_id": "1", "count": "2", "types": ["mcq"]})
    assert r.status == 200 and len(r.json["questions"]) == 2


def test_query_string_integers(clients):
    assert clients["teacher"].get("/api/questions?course_id=abc").status == 400
    assert clients["teacher"].get("/api/questions?course_id=1").status == 200


@pytest.mark.parametrize("value", ["2026-13-45", "yesterday", 5, ["2026-01-01"], {"from": "x"}, "2026-01-01"])
def test_e_service_form_fields_with_wrong_types(clients, value):
    """Nested form data: every field of every request type gets a wrongly typed value."""
    svc = clients["student"].get("/api/services").json
    crashes = []
    for t in svc["types"]:
        for f in t["fields"]:
            r = clients["student"].post("/api/requests", {"type_code": t["code"], "data": {f["name"]: value}})
            if r.status >= 500:
                crashes.append(f"{t['code']}.{f['name']}")
    assert not crashes, crashes
