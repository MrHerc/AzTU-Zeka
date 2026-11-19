"""Every channel route answers 403 to someone who is not a member of the channel's club (tasks/todo.md, Task 35),
taken from the route table, so a new channel route is covered the day it is added."""
import json
import re
from pathlib import Path

import pytest

from tests.integration.test_community import build_club

MATRIX = json.loads((Path(__file__).parent / "matrix.json").read_text(encoding="utf-8"))
CHANNEL = re.compile(r"^(GET|POST|PUT|DELETE) /api/(channels/|club-messages/|clubs/\{id:int\}/(members|conduct))")
ROUTES = sorted(k for k in MATRIX if CHANNEL.match(k))


def call(client, key: str, w: dict):
    method, path = key.split(" ", 1)
    ids = {"channels": w["chat"], "club-messages": w["message"], "clubs": w["club"]}
    path = re.sub(r"^/api/([a-z-]+)/\{id:int\}", lambda m: f"/api/{m.group(1)}/{ids[m.group(1)]}", path)
    path = path.replace("{uid:int}", str(w["member"].user["id"])).replace("{action}", "mute")
    body = {"text": "salam", "reason": "səbəb yazılıb", "minutes": 30}
    return getattr(client, method.lower())(path, *([body] if method in ("POST", "PUT") else []))


@pytest.fixture(scope="module")
def world(app_db):
    return build_club(app_db, "acc")


def test_the_route_table_has_the_channel_routes():
    assert len(ROUTES) >= 7 and "GET /api/channels/{id:int}/messages" in ROUTES and "POST /api/channels/{id:int}/messages" in ROUTES


def test_a_non_member_gets_403_on_every_channel_route(world, app_db):
    outsiders = {"student": world["out"], "teacher": app_db.client("teacher")}
    for who, client in outsiders.items():
        leaks = {k: s for k in ROUTES if (s := call(client, k, world).status) != 403}
        assert leaks == {}, (who, leaks)


def test_a_member_reaches_the_read_routes(world):
    assert call(world["member"], "GET /api/channels/{id:int}/messages", world).status == 200
    shown = call(world["member"], "GET /api/clubs/{id:int}/members", world).json
    assert shown and all(set(m) == {"user_id", "full_name", "role"} for m in shown), "T-E5/M32: no requests, removals or mutes"


def test_a_person_who_only_asked_to_join_gets_403(app_db):
    """T-E5: a pending request is not a membership."""
    w = build_club(app_db, "req")
    assert w["out"].post(f"/api/clubs/{w['club']}/join").status == 200
    leaks = {k: s for k in ROUTES if (s := call(w["out"], k, w).status) != 403}
    assert leaks == {}, leaks
