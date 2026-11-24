"""Every action a workflow uses is pinned to a commit, with its version beside it (SEC-27F-2): a moved tag cannot change
what CI runs or what lands in its pip and npm caches. Dependabot (.github/dependabot.yml) bumps the SHA and the comment."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USES = re.compile(r"^\s*(?:-\s*)?uses:\s*(\S+)(.*)$")


def test_every_action_is_pinned_to_a_commit_sha():
    found, loose = 0, []
    for f in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            m = USES.match(line)
            if not m or m.group(1).startswith("./"):
                continue
            found += 1
            if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", m.group(1)) or not re.fullmatch(r"\s+# v\d+(\.\d+)*", m.group(2)):
                loose.append(f"{f.name}:{n}: {line.strip()}")
    assert found and loose == [], loose
