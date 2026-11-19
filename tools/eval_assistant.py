"""Score the campus assistant against a question set (tasks/todo.md, Task 32).

    python tools/eval_assistant.py tests/eval/assistant_az.jsonl [--min 45]

Each line: {"q", "lang", "expect"} where expect is {"kb": heading} (the first source is that article), {"room": code}
(a room answer about that room), {"intent": "next_lesson"} or {"handoff": true} (no source: the answer hands over to a
person). Every answer must also carry a source or a handoff. The demo database is built in a temporary ZEKA_DATA, so
data/ is never touched; the questions are asked as the demo student, through the same function as POST /api/campus/ask.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BARE = "neither a source nor a handoff"


def judge(out: dict, expect: dict, heading_of) -> str | None:
    """None when the answer is right, else why not."""
    source = out["meta"].get("source")
    handoff = any(a["type"] == "handoff" for a in out["actions"])
    if not (out["cites"] or source or handoff or out["meta"].get("greeting")):
        return BARE
    if "kb" in expect:
        got = heading_of(out["cites"][0]) if out["cites"] else None
        return None if got == expect["kb"] else f"first source {got!r}"
    if "room" in expect:
        return None if source == "rooms" and f"**{expect['room']}**" in out["text"] else f"source {source!r}: {out['text'][:60]!r}"
    if "intent" in expect:
        return None if out["meta"].get("intent") == expect["intent"] else f"intent {out['meta'].get('intent')!r}"
    if expect.get("handoff"):
        got = source or (heading_of(out["cites"][0]) if out["cites"] else None)
        return None if handoff and not got else f"answered from {got!r}"
    return "unknown expectation"


def run(cases: list[dict]) -> tuple[int, list[str], int]:
    """(right answers, one line per miss, answers with neither a source nor a handoff) on a fresh demo database."""
    with tempfile.TemporaryDirectory(prefix="zeka-eval-") as tmp:
        os.environ["ZEKA_DATA"] = tmp                   # read when store is imported
        sys.path.insert(0, str(ROOT / "backend"))
        from zeka.legacy import engine, store
        from zeka.modules.assistant import service
        store.init()
        c = store.connect()
        try:
            user = store.row(c, "SELECT * FROM users WHERE username=?", ((store.setting(c, "demo_logins") or {})["student"],))

            def heading_of(kid):
                doc = engine.INDEX["campus"].docs.get(kid)
                return doc[2]["heading"] if doc else None
            right, misses, bare = 0, [], 0
            for i, case in enumerate(cases, 1):
                masked, _ = engine.mask_pii(case["q"])
                why = judge(service.campus_answer(c, user, masked, case.get("lang", "az")), case["expect"], heading_of)
                bare += why == BARE
                if why is None:
                    right += 1
                else:
                    misses.append(f"{i:>2}. MISS {case['q']!r} -> {why}")
            return right, misses, bare
        finally:
            c.close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cases", type=Path)
    ap.add_argument("--min", type=int, default=45, help="the least number of right answers to pass")
    args = ap.parse_args(argv)
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    right, misses, bare = run(cases)
    print("\n".join(misses))
    print(f"without a source or a handoff: {bare}")
    print(f"right: {right}/{len(cases)} (needed {args.min})")
    return 0 if right >= args.min and not bare else 1


if __name__ == "__main__":
    raise SystemExit(main())
