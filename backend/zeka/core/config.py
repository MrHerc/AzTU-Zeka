"""Run mode, read from the environment once at import (tasks/todo.md, Task 5).

ZEKA_MODE=demo (default): password-less demo login, synthetic data, reset; loopback only unless ZEKA_ALLOW_OPEN_DEMO=1.
ZEKA_MODE=prod: the demo routes do not exist, people are never seeded and the database is never deleted or reset.
"""
import os

MODES = ("demo", "prod")
MODE = (os.environ.get("ZEKA_MODE") or "demo").strip().lower()


def prod() -> bool:
    return MODE == "prod"
