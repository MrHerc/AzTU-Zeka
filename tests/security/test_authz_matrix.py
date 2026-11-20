"""Role x route matrix (tasks/todo.md, Task 13).

tests/security/matrix.json holds, for every route, who may call it (``public``, ``any`` signed-in user, or the roles),
whether it exists only in demo mode, runs in the slow slots, the permission it needs and the kind of personal data
whose reading is audited. A route that is new, gone or changed fails this test until matrix.json is updated on purpose:

    python tests/security/test_authz_matrix.py        # rewrite matrix.json from the route table, then review the diff
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from zeka.core import perms  # noqa: E402
from zeka.legacy import api  # noqa: E402

MATRIX = Path(__file__).with_name("matrix.json")


def current() -> dict:
    out = {}
    for method, rx, fn, roles, auth in api.R.routes:
        path = re.sub(r"\(\?P<(\w+)>\[0-9\]\+\)", r"{\1:int}", rx.pattern[1:-1])
        path = re.sub(r"\(\?P<(\w+)>\[\^/\]\+\)", r"{\1}", path)
        path = re.sub(r"\\(.)", r"\1", path)              # the literal parts are escaped in the route's regex
        out[f"{method} {path}"] = {"access": sorted(roles) if roles else "any" if auth else "public",
                                   "demo": bool(getattr(fn, "demo_only", False)), "slow": bool(getattr(fn, "slow", False)),
                                   "perm": getattr(fn, "perm", None), "audit_read": getattr(fn, "audit_read", None),
                                   **({"scope": fn.scope} if getattr(fn, "scope", None) else {})}
    return out


def test_every_route_is_in_the_matrix_with_the_access_it_declares():
    expected, now = json.loads(MATRIX.read_text(encoding="utf-8")), current()
    new, gone = sorted(set(now) - set(expected)), sorted(set(expected) - set(now))
    changed = {k: {"matrix": expected[k], "code": now[k]} for k in sorted(set(now) & set(expected)) if expected[k] != now[k]}
    assert not (new or gone or changed), json.dumps({"new": new, "gone": gone, "changed": changed}, ensure_ascii=False, indent=1)


def test_the_matrix_names_only_known_roles_and_permissions():
    for key, entry in current().items():
        if isinstance(entry["access"], list):
            assert set(entry["access"]) <= set(perms.ROLES), key
        assert entry["perm"] is None or entry["perm"] in perms.PERMS, key


if __name__ == "__main__":
    MATRIX.write_text(json.dumps(current(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{MATRIX}: {len(current())} routes")
