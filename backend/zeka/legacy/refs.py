"""Verified external references (content/references.json): open textbooks, open courses, official documentation and
guidance shown on course pages, in the lecture viewer and in AI Akademiya modules.

Titles and section names stay in the language of the source; the localiser never translates them (see SKIP_KEYS in i18n.py).
Only https links are served, so a typo in the content file cannot inject a javascript: or plain-http link into the page.
"""
from __future__ import annotations

import json

from .store import CONTENT

KINDS = ("book", "course", "docs", "guide", "policy", "article", "standard", "database", "org")
_cache: dict = {"mtime": None, "data": {}}


def _data() -> dict:
    path = CONTENT / "references.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if _cache["mtime"] != mtime:            # re-read after an edit, no restart needed
        try:
            _cache["data"] = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            _cache["data"] = {}
        _cache["mtime"] = mtime
    return _cache["data"]


def _clean(items) -> list[dict]:
    out = []
    for r in items or []:
        url = str(r.get("url") or "")
        if not url.startswith("https://") or not r.get("work"):
            continue
        out.append({"work": r["work"], "part": r.get("part") or "", "authors": r.get("authors") or "", "publisher": r.get("publisher") or "",
                    "kind": r.get("kind") if r.get("kind") in KINDS else "docs", "lang": r.get("lang") or "en", "url": url})
    return out


def checked() -> str:
    """ISO date on which every link was last opened and checked."""
    return _data().get("checked") or ""


def for_course(code: str) -> list[dict]:
    return _clean(_data().get("courses", {}).get(code))


def for_material(filename: str) -> list[dict]:
    return _clean(_data().get("materials", {}).get(filename))


def for_module(track_key: str, seq: int) -> list[dict]:
    return _clean(_data().get("academy", {}).get(f"{track_key}/{seq}"))
