"""A migration wave's load (tasks/todo.md, Task 38):

    python tools/etl/run.py --mapping content/mappings/<source>.json --dir EXPORT_DIR --wave 0 --as-of 2026-11-01 \\
        [--exported-at 2026-11-01T18:00:00+04:00] [--out data/migration/<source>-wave0] [--dry-run] [--force]

For each file of the mapping, in its order: read the old system's export, map it onto its import kind (columns,
transforms, constants; a lesson export without its classes or starts is summed into opening balances), split it into
files the import takes in one transaction, write them to ``--out`` and import each through Task 16's import (dry run,
all or nothing, links), logged with the wave for ``manage.py reconcile --wave N --source <source> --dir <out>``.

Exit 0: every file mapped with no column unexplained and every row imported (or checked); 1: refused rows or columns
not explained (nothing of that file is written); 2: a file, the mapping or the database cannot be used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import adapters  # noqa: E402
from zeka.core import migrate  # noqa: E402
from zeka.legacy import store  # noqa: E402
from zeka.modules.integration import domain as imports, importer, tables  # noqa: E402
from zeka.modules.migration import domain, service  # noqa: E402


def _az(v) -> str:
    return v.get("az", "") if isinstance(v, dict) else str(v)


def run(mapping: Path, folder: Path, wave: int, as_of: str, exported_at: str | None, out: Path, dry_run: bool, force: bool,
        user_id: int | None = None) -> int:
    spec = json.loads(mapping.read_text(encoding="utf-8"))
    source = spec["source"]
    problems = [f"{f.get('file')}: {p}" for f in spec["files"] for p in domain.check_spec(f)]
    if problems:
        print("error: the mapping is not valid:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    c = store.connect()
    code = 0
    try:
        for f in spec["files"]:
            path = folder / f["file"]
            try:
                header, rows = adapters.read(path)
            except (OSError, adapters.AdapterError, tables.TableError) as ex:
                print(f"error: {f['file']}: {ex}", file=sys.stderr)
                return 2
            kind, head, canon, rep = domain.apply(f, header, rows)
            print(f"{f['file']} -> {kind}: {rep['rows']} rows · mapped {', '.join(rep['mapped'])}"
                  + (f" · left out {', '.join(f'{k} ({v})' for k, v in rep['ignored'].items())}" if rep["ignored"] else "")
                  + (" · summed into opening balances" if rep.get("aggregated") else ""))
            if not domain.explained(rep):
                print(f"  NOT EXPLAINED: columns not in the mapping {rep['unexplained']}, mapped columns not in the file {rep['missing']}")
                code = 1
                continue
            for r in rep["refused"]:
                print(f"  refused, row {r['row']}: {_az(r['reason'])}")
            if rep["refused"]:
                code = 1
                continue
            source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            parts = domain.chunks(canon, importer.MAX_FILE_ROWS)
            for i, part in enumerate(parts, 1):
                name = f"{Path(f['file']).stem}.{kind}.{i:03d}.csv"
                data = adapters.to_csv(head, part)
                (out / name).write_bytes(data)
                rows_of = {j + 2: x["_row"] for j, x in enumerate(part)}     # canonical line -> the export's line
                try:
                    r = service.load(c, wave, source, kind, name, data, as_of=as_of if kind in imports.JOURNAL_KINDS else None,
                                     exported_at=exported_at, source_file=f["file"], source_sha256=source_sha, user_id=user_id,
                                     dry_run=dry_run, force=force)
                except tables.TableError as ex:
                    print(f"error: {name}: {ex}", file=sys.stderr)
                    return 2
                print(f"  {name}: new {r['inserted']} · changed {r['updated']} · unchanged {r['unchanged']} · conflicts "
                      f"{len(r['conflicts'])} · refused {r['error_count']}" + (" · dry run" if dry_run else ""))
                for e in r["errors"]:
                    print(f"    refused, export row {rows_of.get(e['row'], e['row'])}: {_az(e['reason'])}")
                if r["error_count"]:
                    code = 1
    finally:
        c.close()
    return code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mapping", required=True, type=Path)
    ap.add_argument("--dir", required=True, type=Path, help="the folder of the old system's export files")
    ap.add_argument("--wave", required=True, type=int)
    ap.add_argument("--as-of", required=True, help="the export's cut-over date (YYYY-MM-DD) for the journal kinds")
    ap.add_argument("--exported-at", help="when the old system exported the files (ISO date-time), for the report")
    ap.add_argument("--out", type=Path, help="where the mapped files go (default: data/migration/<source>-wave<N>)")
    ap.add_argument("--dry-run", action="store_true", help="check and compare only: nothing is written to the database")
    ap.add_argument("--force", action="store_true", help="load while an exam is going on (audited)")
    ap.add_argument("--by", help="the account the load is entered by (username): status orders name it")
    a = ap.parse_args(argv)
    if imports.a_date(a.as_of) != a.as_of:
        print("error: --as-of must be YYYY-MM-DD", file=sys.stderr)
        return 2
    try:
        source = json.loads(a.mapping.read_text(encoding="utf-8"))["source"]
    except (OSError, ValueError, KeyError) as ex:
        print(f"error: the mapping cannot be read: {ex}", file=sys.stderr)
        return 2
    out = a.out or store.DATA / "migration" / f"{source}-wave{a.wave}"
    try:
        store.init()
        user_id = None
        if a.by:
            import manage                                   # backend/manage.py: one rule for who may enter an import
            c = store.connect()
            try:
                user_id = manage.staff_id(c, a.by)
            finally:
                c.close()
            if user_id is None:
                print(f"error: --by {a.by}: no active staff account with this username", file=sys.stderr)
                return 2
        return run(a.mapping, a.dir, a.wave, a.as_of, a.exported_at, out, a.dry_run, a.force, user_id)
    except migrate.MigrationError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
