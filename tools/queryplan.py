"""Query plans of the load-test read routes on a large dataset (tasks/todo.md, Task 7).

    python tools/queryplan.py [--dataset university] [--min-rows 1000]

Builds the dataset in a throw-away ZEKA_DATA directory, serves the API in this process, sends every route of the read
scenario (tools/loadtest.py READ) as a student, records each SQL statement the handlers run and prints, as JSON, every
statement whose EXPLAIN QUERY PLAN scans a table that has more than --min-rows rows. Exit 1 when there is one.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

import loadtest

ROOT = Path(__file__).resolve().parents[1]
WRITES = re.compile(r"\s*(SELECT|WITH|UPDATE|DELETE)\b", re.I)
ALIAS = re.compile(r"\b(?:FROM|JOIN)\s+(\w+)(?:\s+(?:AS\s+)?(?!ON\b|WHERE\b|JOIN\b|LEFT\b|ORDER\b|GROUP\b|LIMIT\b)(\w+))?", re.I)


def scans(db: sqlite3.Connection, sql: str, sizes: dict[str, int], min_rows: int) -> list[str]:
    """The plan lines of ``sql`` that walk a whole table (or a whole index of it) with more than ``min_rows`` rows."""
    alias = {(a or t).lower(): t.lower() for t, a in ALIAS.findall(sql)}
    out = []
    for *_, detail in db.execute("EXPLAIN QUERY PLAN " + sql):
        m = re.match(r"SCAN (\w+)", detail)
        if m and sizes.get(alias.get(m.group(1).lower(), m.group(1).lower()), 0) > min_rows:
            out.append(detail)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--dataset", choices=sorted(loadtest.SIZES), default="university")
    ap.add_argument("--min-rows", type=int, default=1000)
    args = ap.parse_args(argv)
    os.environ.pop("ZEKA_TX_GUARD", None)              # it installs its own trace callback on every connection
    with tempfile.TemporaryDirectory(prefix="zeka-plan-") as tmp:
        data = Path(tmp)
        loadtest.build_dataset(data, args.dataset)       # sets ZEKA_DATA before store is imported
        from zeka.core import web
        from zeka.legacy import api, store
        seen: list[str] = []
        connect = store.connect

        def traced():
            c = connect()
            c.set_trace_callback(seen.append)            # parameters arrive already bound into the text
            return c

        store.connect = traced                          # the read routes never search: no BM25 build needed
        srv = web.make_server(0, api.R, ROOT / "frontend", api.before, api.after, lambda _msg: None)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        try:
            token = loadtest.sessions(port, data)[0][0]
            import http.client
            for _, method, path in loadtest.READ:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
                try:
                    status = loadtest.call(conn, method, path, None, {"Cookie": token, "Origin": f"http://127.0.0.1:{port}"})
                finally:
                    conn.close()
                if status != 200:
                    raise SystemExit(f"{method} {path}: HTTP {status}")
        finally:
            srv.shutdown()
            srv.server_close()
        db = sqlite3.connect(data / "campus.db")
        try:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            sizes = {t.lower(): db.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}  # nosec B608 - names from sqlite_master
            bad = {sql: plan for sql in dict.fromkeys(seen) if WRITES.match(sql)
                   for plan in [scans(db, sql, sizes, args.min_rows)] if plan}
        finally:
            db.close()
    print(json.dumps({"dataset": args.dataset, "statements": len(set(seen)), "scans": bad}, ensure_ascii=False, indent=1))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
