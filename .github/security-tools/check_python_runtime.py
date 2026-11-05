"""Check that the CPython release pinned in render.yaml is supported and current (data: endoflife.date)."""
import datetime
import json
import re
import sys
import urllib.request

API = "https://endoflife.date/api/python.json"


def main(path: str) -> int:
    text = open(path, encoding="utf-8").read()
    m = re.search(r"key:\s*PYTHON_VERSION\s*\n\s*value:\s*\"?([0-9]+\.[0-9]+(?:\.[0-9]+)?)\"?", text)
    if not m:
        print(f"::error file={path}::PYTHON_VERSION not found")
        return 1
    pinned = m.group(1)
    cycle = ".".join(pinned.split(".")[:2])
    try:
        # bandit B310: fixed https URL
        with urllib.request.urlopen(API, timeout=30) as r:  # nosec B310
            cycles = json.load(r)
    except (OSError, ValueError) as ex:      # the data source being down must not block unrelated pull requests
        print(f"::warning::Could not read {API}: {ex}; runtime support not checked")
        return 0
    info = next((c for c in cycles if str(c.get("cycle")) == cycle), None)
    if not info:
        print(f"::error file={path}::Python {cycle} is not a known release line")
        return 1
    today = datetime.date.today()
    eol = datetime.date.fromisoformat(str(info["eol"])) if isinstance(info.get("eol"), str) else None
    latest = str(info.get("latest", ""))
    status = 0
    if eol and eol <= today:
        print(f"::error file={path}::Python {cycle} reached end-of-life on {eol}; move to a supported release line")
        status = 1
    elif eol and (eol - today).days < 183:
        print(f"::warning file={path}::Python {cycle} reaches end-of-life on {eol}; plan the upgrade")
    if pinned.count(".") == 2 and latest and pinned != latest:
        print(f"::error file={path}::PYTHON_VERSION {pinned} is behind the latest {cycle} release {latest}")
        status = 1
    print(f"PYTHON_VERSION={pinned} · line {cycle} · latest {latest or '?'} · end-of-life {eol or '?'}")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "render.yaml"))
