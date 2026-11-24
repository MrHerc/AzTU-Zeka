"""Administration commands:  python backend/manage.py status | migrate | create-admin | backup | restore | import |
reconcile | activation-codes | export | jobs | exam-verify | import-routes | forma3-check | import-framework |
timetable-replay  (--help for each)"""
import argparse
import os
import re
import sqlite3
import subprocess  # nosec B404 - only to catch the timeout of the ssh transfer
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from zeka.core import backup, config, migrate  # noqa: E402
from zeka.legacy import store  # noqa: E402
from zeka.modules.identity import domain as identity  # noqa: E402
from zeka.modules.integration import domain as integration_rules, export, importer, tables  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Zəka: administration commands")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="applied and pending schema migrations")
    sub.add_parser("migrate", help="apply pending schema migrations (a copy of the database is saved first)")
    ca = sub.add_parser("create-admin", help="prod: create an administrator account (sign-in arrives with Task 10)")
    ca.add_argument("--username", required=True)
    ca.add_argument("--name", required=True, help="full name")
    bk = sub.add_parser("backup", help="encrypted backup of the database and uploads, sent to BACKUP_REMOTE (infra/backup.sh)")
    bk.add_argument("--dest", default=os.environ.get("BACKUP_DIR") or str(store.ROOT / "backups"), help="local backup directory")
    bk.add_argument("--key-file", default=os.environ.get("BACKUP_KEY_FILE", ""), help="file with one random line (BACKUP_KEY_FILE)")
    bk.add_argument("--remote", default=os.environ.get("BACKUP_REMOTE", ""), help="second host: user@host:/path or a mounted path")
    rs = sub.add_parser("restore", help="check a backup set and restore it into a new directory (infra/restore.sh)")
    rs.add_argument("set", help="zeka-YYYYMMDD-HHMMSS.enc or latest.enc")
    rs.add_argument("--to", required=True, help="new or empty directory: campus.db and uploads/ are written there")
    rs.add_argument("--key-file", default=os.environ.get("BACKUP_KEY_FILE", ""))
    im = sub.add_parser("import", help="bulk import of one CSV/XLSX file, all or nothing (Task 16)")
    im.add_argument("--kind", required=True, choices=integration_rules.KINDS)
    im.add_argument("--source", required=True, help="name of the source system, e.g. old-sis")
    im.add_argument("--file", required=True)
    im.add_argument("--dry-run", action="store_true", help="check and compare only: nothing is written")
    im.add_argument("--prefer", choices=("zeka", "source"), default="zeka",
                    help="source: overwrite rows changed in Zəka since the last import (audited)")
    im.add_argument("--as-of", help="attendance, attendance-opening, grades (required): the export's cut-over date YYYY-MM-DD")
    im.add_argument("--force", action="store_true", help="import while an exam is going on (audited)")
    im.add_argument("--wave", type=int, help="log the file as part of this migration wave, for manage.py reconcile (Task 38)")
    im.add_argument("--exported-at", help="with --wave: when the old system exported the file (ISO date-time)")
    im.add_argument("--by", help="the account the import is entered by (username); required for status-events")
    rc = sub.add_parser("reconcile", help="compare a migration wave's files with what Zəka holds (Task 38)")
    rc.add_argument("--wave", type=int, required=True)
    rc.add_argument("--source", required=True)
    rc.add_argument("--dir", required=True, help="the folder holding the wave's loaded files")
    rc.add_argument("--sample", type=int, default=50, help="random records listed for a person to check")
    rc.add_argument("--out", help="also write the full report as JSON to this file")
    rc.add_argument("--by", help="the account (username) that checked the wave: with it, a reconciled history makes the "
                                 "transcript issuable; without it, nothing is marked")
    ac = sub.add_parser("activation-codes", help="one-time activation codes for a faculty's students, as CSV (Task 16)")
    ac.add_argument("--faculty", required=True, help="faculty code")
    ac.add_argument("--out", required=True, help="CSV file to write (handed to the dean's office)")
    xp = sub.add_parser("export", help="grades, attendance, OneRoster files, a register, the status change list (Task 37) "
                                       "or the timetable (Task 48)")
    xp.add_argument("--kind", required=True, choices=export.KINDS)
    xp.add_argument("--since", help="grades, attendance, status-changes: only what was written or changed after this ISO "
                                    "date-time, e.g. 2026-12-01T00:00:00+04:00 (without an offset: the university's clock)")
    xp.add_argument("--registry", choices=tuple(export.REGISTRY), default="students", help="registry: which register")
    xp.add_argument("--columns", default="", help="registry: comma-separated columns (default: all)")
    xp.add_argument("--out", help="file to write; without it a CSV goes to standard output (oneroster needs it: a zip)")
    xp.add_argument("--term", type=int, help="timetable: the term's id (default: the current term); its rows in force")
    xp.add_argument("--version", type=int, help="timetable: a builder version's id (draft or published); its placements")
    jb = sub.add_parser("jobs", help="periodic jobs (Task 36)")
    jb.add_argument("action", choices=("status", "run", "check"),
                    help="status: each job's last run; run: run what is due now, once; check: the warning signs (exit 1 on a problem)")
    ev = sub.add_parser("exam-verify", help="check an exam's hash chain, its frozen answers and scores (Task 30)")
    ev.add_argument("exam_id", type=int)
    ev.add_argument("--root", help="the 64-character root from the closing protocol or e-mail")
    rt = sub.add_parser("import-routes", help="replace a building's route graph from two CSV files, all or nothing (Task 31)")
    rt.add_argument("--building", required=True, help="building code")
    rt.add_argument("--nodes", required=True, help="CSV: code,kind,floor,room,label (kind: entrance, corridor, stairs, lift, door)")
    rt.add_argument("--edges", required=True, help="CSV: from,to,length_m,step_free")
    f3 = sub.add_parser("forma3-check", help="check a department's Forma №3 file before uploading it: controls, counts and "
                                             "conflicts by cell; reads only the file, no database (Task 47)")
    f3.add_argument("file", help="the department's XLSX file")
    f3.add_argument("--json", action="store_true", help="the whole report as JSON (it holds the names written in the file)")
    fw = sub.add_parser("import-framework", help="import a framework file as NIST published it, unchanged (NICE Framework "
                                                 "Components JSON); a second run changes nothing (Task 24)")
    fw.add_argument("--file", required=True, help="e.g. content/frameworks/nice-components-2.2.0.json")
    tr = sub.add_parser("timetable-replay", help="solve a timetable version again from its run's stored input and seed and "
                                                 "confirm the same placements (audit; Task 48)")
    tr.add_argument("--version", type=int, required=True, help="the builder version's id")
    args = ap.parse_args(argv)
    if args.cmd == "timetable-replay":
        return timetable_replay(args.version)
    if args.cmd == "import-framework":
        return import_framework(Path(args.file))
    if args.cmd == "forma3-check":
        return forma3_check(Path(args.file), args.json)
    if args.cmd == "import-routes":
        return import_routes(args.building, Path(args.nodes), Path(args.edges))
    if args.cmd == "exam-verify":
        return exam_verify(args.exam_id, args.root)
    if args.cmd == "jobs":
        return run_jobs(args.action)
    if args.cmd == "export":
        return run_export(args.kind, args.since, args.registry, args.columns, args.out, args.term, args.version)
    if args.cmd == "import":
        return run_import(args.kind, args.source, Path(args.file), args.dry_run, args.prefer == "source", args.as_of, args.force,
                          args.wave, args.exported_at, args.by)
    if args.cmd == "reconcile":
        return run_reconcile(args.wave, args.source, Path(args.dir), args.sample, args.out, args.by)
    if args.cmd == "activation-codes":
        return run_activation_codes(args.faculty, Path(args.out))
    if args.cmd == "create-admin":
        return create_admin(args.username, args.name)
    if args.cmd == "backup":
        return run_backup(Path(args.dest), args.key_file, args.remote)
    if args.cmd == "restore":
        return run_restore(Path(args.set), Path(args.to), args.key_file)
    c = store.connect()
    try:
        if args.cmd == "status":
            s = migrate.status(c)
            print(f"database: {store.DB_PATH}")
            print("applied: " + (", ".join(f"{v:04d}" for v in s["applied"]) or "-"))
            print("pending: " + (", ".join(f"{v:04d}" for v in s["pending"]) or "-"))
        else:
            done = migrate.apply(c, backup_dir=store.DATA / "backups")
            print("applied: " + (", ".join(f"{v:04d}" for v in done) or "nothing to do"))
    except migrate.MigrationError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    finally:
        c.close()
    return 0


def forma3_check(path: Path, as_json: bool) -> int:
    """0: every visible post can be applied; 1: at least one post is blocked (or a control fails); 2: the file cannot be
    read. The default output names cells only (``#<sheet index>!<cell>``): no person's name and no cell text."""
    import json
    from zeka.modules.integration import forma3
    try:
        form = forma3.read(tables.xlsx_sheets(path.read_bytes()))
    except OSError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    except (tables.TableError, forma3.FormError) as ex:
        print(f"error: {ex.args[0]}", file=sys.stderr)
        return 2
    r = forma3.report(form)
    if not form.posts:
        print("error: Faylda Forma №3 tədris yükü tapılmadı", file=sys.stderr)
        return 2
    bad = [p for p in r["posts"] if p["status"] == "blocked"]
    if as_json:
        print(json.dumps({k: (_az_deep(v)) for k, v in r.items()}, ensure_ascii=False, indent=1))
        return 1 if bad else 0
    u = r["units"]
    print(f"quruluş {r['layout']} · tədris ili {r['year']} · vərəq {len(r['sheets'])} · ştat/bölmə {len(r['posts'])}")
    for sh in r["sheets"]:
        if not sh["imported"]:
            print(f"  vərəq #{sh['index']}: {sh['class']}, {sh['state']} — idxal olunmur ({sh['units']} dərs, {sh['hours']:g} saat)")
    print(f"dərslər: {u['count']} ({u['hours']:g} auditoriya saatı); tətbiq oluna bilən: {u['ready']} ({u['ready_hours']:g} saat); "
          f"gizli vərəqdə: {u['hidden']}; saat hesabı: {u['hourly']}; vakansiya: {u['vacancy']}; birləşmiş: {u['joint']}")
    print(f"digər yük: {sum(x['lines'] for x in r['load'].values())} sətir, {r['load_hours']:g} saat")
    x = r["excluded"]
    if x["posts"]:
        print(f"kafedranın cəminə daxil olmayan: {len(x['posts'])} ştat/bölmə ({', '.join(x['posts'][:12])}) — {x['units']} dərs "
              f"({x['hours']:g} saat), digər yük {x['load_lines']} sətir ({x['load_hours']:g} saat)")
    passed = sum(all(p["controls"].get(t) for t in ("T1", "T2", "T3")) for p in r["posts"])
    print(f"yoxlamalar T1–T3: {passed}/{len(r['posts'])} ştat/bölmə keçdi; bloklanıb: {len(bad)}; heç bir qaydaya düşməyən xana: {r['unclassified']}")
    for p in bad:
        failed = ", ".join(t for t in ("T1", "T2", "T3") if not p["controls"].get(t)) or "-"
        print(f"  BLOK {p['ref']}: {p['units']} dərs, {p['hours']:g} saat tətbiq olunmur; keçməyən yoxlama: {failed}")
    for check in ("T4", "T5", "T6"):
        mine = [c for c in form.controls if c.check == check]
        if mine:
            print(f"yoxlama {check}: {sum(c.ok for c in mine)}/{len(mine)} keçdi")
    for c in r["controls"]:
        if not c["ok"]:
            print(f"  YOXLAMA {c['check']} {c['ref']}: gözlənilən {c['expected']}, tapılan {c['found']}")
    print(f"konfliktlər: {r['conflict_count']} (bloklayan: {r['blocking_count']})")
    for c in r["conflicts"]:
        print(f"  {'BLOK' if c['blocking'] else 'qeyd'} {c['cell']}  {c['code']}: {_bare(forma3.MSG[c['code']])}")
    codes: dict = {}
    for n in form.notes:
        codes.setdefault(n.code, []).append(n.cell)
    print(f"qeydlər: {r['note_count']}")
    for code, cells in sorted(codes.items(), key=lambda x: -len(x[1])):
        print(f"  {len(cells):4d}  {code}: {_bare(forma3.MSG[code])}")
        print(f"        {', '.join(cells[:12])}{' …' if len(cells) > 12 else ''}")
    return 1 if bad or any(not c["ok"] for c in r["controls"]) else 0


def _bare(template: str) -> str:
    """A message with its values left out: the default output of forma3-check shows no cell text."""
    return re.sub(r"\{\w+\}", "…", template)


def _az_deep(v):
    if isinstance(v, dict):
        return v["az"] if set(v) >= {"az", "en", "ru"} and isinstance(v["az"], str) else {k: _az_deep(x) for k, x in v.items()}
    return [_az_deep(x) for x in v] if isinstance(v, list) else v


def exam_verify(eid: int, root: str | None) -> int:
    """0 when the chain, the answers, the scores and (given) the root all hold; 1 with the first broken link and every
    changed attempt; 2 when there is no such exam. Reads only."""
    from zeka.modules.exam import service as exam
    c = store.connect()
    try:
        r = exam.verify(c, eid, root)
    finally:
        c.close()
    if r is None:
        print(f"exam {eid}: not found", file=sys.stderr)
        return 2
    print(f"exam {eid}: {r['events']} events, head {r['head']}")
    for p in r["problems"]:
        if p["what"] == "chain":
            print(f"  BROKEN chain at seq {p['seq']}: {p['problem']}")
        elif p["what"] == "attempt":
            print(f"  CHANGED attempt {p['attempt_id']} (student {p['student_id']}): {p['problem']}")
        elif p["what"] == "event":
            print(f"  FOREIGN event at seq {p['seq']}: {p['problem']}")
        elif p["what"] == "anchor":
            print(f"  ANCHOR {p['document']} (seq {p['seq']}): {p['problem']}")
        else:
            print(f"  ROOT not in the chain (the head is {p['head']})")
    print("FAILED" if r["problems"] else "OK" + (" (root matches)" if root else ""))
    return 1 if r["problems"] else 0


def timetable_replay(vid: int) -> int:
    """0 when the run's stored input and seed give the version's placements again; 1 with each meeting that differs; 2
    when there is no such version. Names meetings by key only (unit:part), never a person."""
    from zeka.modules.timetable import builder
    c = store.connect()
    try:
        r = builder.replay(c, vid)
    finally:
        c.close()
    if r is None:
        print(f"version {vid}: not found", file=sys.stderr)
        return 2
    print(f"version {vid} (run {r['run_id']}): {r['placements']} placements, {r['manual']} moved by hand (not compared)")
    for p in r["problems"]:
        print(f"  {p}")
    for k in r["differ"]:
        print(f"  DIFFERS {k}")
    print("OK" if r["same"] else "FAILED")
    return 0 if r["same"] else 1


def import_framework(path: Path) -> int:
    """0: imported, or already imported (nothing changed), and every kind's rows equal the file's elements; 1: refused or
    the counts differ; 2: the file cannot be read."""
    from zeka.modules.syllabus import frameworks
    try:
        if path.stat().st_size > frameworks.MAX_FILE:     # refused before it is read into memory (SEC-FW-4)
            print(f"error: the file is larger than {frameworks.MAX_FILE // 2 ** 20} MB", file=sys.stderr)
            return 1
        raw = path.read_bytes()
    except OSError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    store.init()
    c = store.connect()
    try:
        try:
            r = frameworks.import_file(c, raw)
        except frameworks.FrameworkError as ex:
            print(f"error: {ex.args[0]['en']}", file=sys.stderr)
            return 1
        c.commit()
    finally:
        c.close()
    f = r["framework"]
    print(f"{f['key']} {f['version']}: {'imported' if r['status'] == 'imported' else 'already imported, nothing changed'} "
          f"(sha256 {f['sha256']})")
    if (f["key"], f["version"]) not in frameworks.KNOWN:
        print("  not verified: no SHA-256 of a file NIST published is known for this version; it has no source and is "
              "never the default framework")
    for kind in sorted(r["file"].keys() | r["stored"].keys()):
        print(f"  {kind:<16} file {r['file'].get(kind, 0):>6}   database {r['stored'].get(kind, 0):>6}")
    print(f"  {'links':<16} file {r['links']['file']:>6}   database {r['links']['stored']:>6}")
    same = r["file"] == r["stored"] and r["links"]["file"] == r["links"]["stored"]
    if not same:
        print("error: the database does not hold what the file holds", file=sys.stderr)
    return 0 if same else 1


def import_routes(building: str, nodes: Path, edges: Path) -> int:
    import csv
    import io
    from zeka.modules.facilities import service as facilities
    store.init()
    try:                                # newline="": a quoted line break stays in its cell (Checkpoint E, PY-E11)
        node_rows = list(csv.DictReader(io.StringIO(nodes.read_text(encoding="utf-8-sig"), newline="")))
        edge_rows = list(csv.DictReader(io.StringIO(edges.read_text(encoding="utf-8-sig"), newline="")))
    except (OSError, UnicodeDecodeError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    c = store.connect()
    try:
        r = facilities.import_graph(c, building, node_rows, edge_rows)
        if not r["ok"]:
            for p in r["problems"]:
                print(f"  {p}", file=sys.stderr)
            print("nothing imported", file=sys.stderr)
            return 1
        c.commit()
    finally:
        c.close()
    cov = r["coverage"]
    print(f"{r['building']}: {r['nodes']} nodes, {r['edges']} edges")
    for key, what in (("rooms_without_node", "rooms without a door node"), ("unreachable", "doors no entrance reaches"),
                      ("no_step_free_route", "accessible rooms without a step-free route")):
        print(f"  {what}: {', '.join(cov[key]) or 'none'}")
    return 0


def run_jobs(action: str) -> int:
    from zeka.core import jobs
    from zeka.legacy import periodic  # noqa: F401  registers the jobs
    store.init()
    c = store.connect()
    try:
        if action == "check":                    # host cron: still reports when the runner (and so the outbox) is down
            from zeka.core import ops
            bad = ops.problems(c, store.DATA)
            for x in ops.checks(c, store.DATA):
                print(f"{x['key']:<7} {'-' if x['ok'] is None else 'ok' if x['ok'] else 'PROBLEM'}  "
                      + " ".join(f"{k}={v}" for k, v in x.items() if k not in ("key", "ok")))
            print(periodic.ops_check(c))
            c.commit()
            return 1 if bad else 0
        if action == "run":
            for name, result in jobs.run_due(c, f"manage:{os.getpid()}"):
                print(f"{name}: {result}")
        for j in jobs.status(c):
            last = j["last"]
            shown = f"{last['status']} at {last['started_at']} ({last['ms']} ms) {last['detail'] or ''}".strip() if last else "never ran"
            print(f"{j['name']:<18} every {j['interval_s'] // 60:>5} min · last ok {j['last_ok'] or '-'} · last: {shown}")
            if last and last["status"] == "error":
                print(f"  reason: {last['detail']}")
    finally:
        c.close()
    return 0


def run_backup(dest: Path, key_file: str, remote: str) -> int:
    try:
        m = backup.create(store.DB_PATH, store.UPLOADS, dest, key_file)
    except (backup.BackupError, sqlite3.Error, OSError) as ex:
        print(f"error: backup failed: {ex}", file=sys.stderr)
        return 2
    print(f"backup: {dest / m['db']}: {len(m['tables'])} tables, {sum(m['tables'].values())} rows, {len(m['uploads'])} uploads")
    if not remote:
        if config.prod():
            print("error: BACKUP_REMOTE is empty: in prod every backup must also be on a second host", file=sys.stderr)
            return 4
        print("BACKUP_REMOTE is not set: the backup stays on this host only")
        return _damaged(m)
    try:
        r = backup.send(dest, remote)
    except (backup.BackupError, OSError, subprocess.TimeoutExpired) as ex:
        print(f"error: sending to the second host failed: {ex}", file=sys.stderr)
        return 3
    print(f"second host: {r['sent']} file(s) sent and their SHA-256 checked there, {r['removed']} old file(s) removed")
    return _damaged(m)


def _damaged(m: dict) -> int:
    if not m.get("damaged"):
        return 0
    print(f"warning: {len(m['damaged'])} upload(s) in the data directory do not match their SHA-256 and were not backed up: "
          + ", ".join(m["damaged"][:5]), file=sys.stderr)
    return 5


def run_restore(enc: Path, target: Path, key_file: str) -> int:
    try:
        r = backup.restore(enc, target, key_file)
    except (backup.BackupError, sqlite3.Error, OSError) as ex:
        print(f"error: restore failed: {ex}", file=sys.stderr)
        return 2
    print(f"restored into {target}: {r['tables']} tables, {r['rows']} rows, {r['uploads']} uploads; integrity_check ok, "
          "row counts match the manifest")
    return 0


def create_admin(username: str, name: str) -> int:
    if not config.prod():
        print("error: create-admin is for ZEKA_MODE=prod; the demo already has its accounts", file=sys.stderr)
        return 2
    username, name = username.strip().lower(), " ".join(name.split())
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,39}", username) or not 3 <= len(name) <= 120:
        print("error: username: 3-40 of a-z 0-9 . _ - ; name: 3-120 characters", file=sys.stderr)
        return 2
    try:
        store.init()                           # migrations and the product catalogue; never people in prod
    except migrate.MigrationError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    c = store.connect()
    try:
        if store.row(c, "SELECT 1 FROM users WHERE username=?", (username,)):
            print(f"error: user {username} already exists", file=sys.stderr)
            return 2
        password = identity.temporary_password()
        uid = c.execute("INSERT INTO users(username,full_name,role,title,color,synthetic,password_hash,must_change) "
                        "VALUES(?,?,'admin','Administrator','#1a2355',0,?,1)",
                        (username, name, identity.hash_password(password))).lastrowid
        store.audit(c, None, "create_admin", "user", username)
        c.commit()
    finally:
        c.close()
    print(f"created administrator {username} (id {uid})")
    print(f"temporary password (shown once, must be changed at the first sign-in): {password}")
    return 0



def _az(v) -> str:
    return v.get("az", "") if isinstance(v, dict) else str(v)          # reasons are i18n dicts


def run_import(kind: str, source: str, path: Path, dry_run: bool, prefer_source: bool, as_of: str | None = None,
               force: bool = False, wave: int | None = None, exported_at: str | None = None, by: str | None = None) -> int:
    """Exit 0: imported (or checked); 1: refused rows, nothing written; 2: the file or the database cannot be used."""
    from zeka.modules.migration import service as migration
    if kind in integration_rules.JOURNAL_KINDS and not as_of:
        print(f"error: --as-of is required for {kind}: the cut-over date of the export (Task 38)", file=sys.stderr)
        return 2
    try:                                               # Checkpoint F (PY-F8)
        integration_rules.moment(exported_at)
    except ValueError:
        print("error: --exported-at must be an ISO date-time, e.g. 2026-11-01T18:00:00+04:00", file=sys.stderr)
        return 2
    try:
        store.init()
    except migrate.MigrationError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    c = store.connect()
    try:
        user_id = staff_id(c, by) if by else None
        if by and user_id is None:
            print(f"error: --by {by}: no active staff account with this username", file=sys.stderr)
            return 2
        if wave is not None:
            report = migration.load(c, wave, source, kind, path.name, path.read_bytes(), as_of=as_of, exported_at=exported_at,
                                    dry_run=dry_run, force=force, prefer_source=prefer_source, user_id=user_id)
        else:
            report = importer.run(c, kind, source, path.name, path.read_bytes(), dry_run=dry_run, prefer_source=prefer_source,
                                  as_of=as_of, force=force, user_id=user_id)
    except (OSError, tables.TableError, sqlite3.Error) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    finally:
        c.close()
    tail = " · dry run, nothing written" if dry_run else f" · write lock {report['lock_ms']} ms" if report["written"] else ""
    print(f"{kind} from {source}: {report['rows']} rows · new {report['inserted']} · changed {report['updated']} · "
          f"unchanged {report['unchanged']} · conflicts {len(report['conflicts'])} · refused {report['error_count']} · "
          f"{report['seconds']} s{tail}")
    for e in report["errors"]:
        print(f"  row {e['row']}: {_az(e['reason'])}")
    for w in report.get("warnings", []):
        print(f"  warning, row {w['row']}: {_az(w['reason'])}")
    for x in report["conflicts"][:200]:
        print(f"  conflict, row {x['row']}: {_az(x['reason'])}" + (f" ({', '.join(x['fields'])})" if x.get("fields") else ""))
    return 1 if report["error_count"] else 0


def staff_id(c, username: str) -> int | None:
    """The id of an active account that is not a student: who an import from the command line is entered by."""
    u = store.row(c, "SELECT id FROM users WHERE username=? AND status='active' AND role<>'student'", (username,))
    return u["id"] if u else None


def run_reconcile(wave: int, source: str, folder: Path, sample: int, out: str | None, by: str | None = None) -> int:
    """Exit 0: the wave reconciles; 1: differences (listed); 2: no database, no file of the wave or an unknown --by."""
    import json
    from zeka.modules.migration import service as migration
    if not store.DB_PATH.exists():
        print(f"error: no database at {store.DB_PATH}", file=sys.stderr)
        return 2
    c = store.connect()
    try:
        user_id = staff_id(c, by) if by else None
        if by and user_id is None:
            print(f"error: no staff account {by!r}", file=sys.stderr)
            return 2
        r = migration.reconcile(c, wave, source, folder, sample, user_id)
    finally:
        c.close()
    if not r["files"]:
        print(f"error: wave {wave} has no file from {source}", file=sys.stderr)
        return 2
    print(f"wave {wave} · {source} · exported at {', '.join(r['exported_at']) or '-'}")
    for f in r["files"]:
        same = f.get("checksums") and f["checksums"]["source"] == f["checksums"]["zeka"]
        print(f"  {f['filename']} ({f['kind']}, {f['rows']} rows) sha256 {f['sha256']} · from {f['source_file']} sha256 "
              f"{f['source_sha256']} · checksum {'equal' if same else 'DIFFERENT'}")
    for kind, v in r["entities"].items():
        print(f"  {kind}: source {v['source']} · linked {v['linked']}" + ("" if v["source"] == v["linked"] else "  <- DIFFERENT"))
    print(f"  absence hours: {r['hour_pairs']} student × course pairs, {len(r['hours'])} different")
    for h in r["hours"][:200]:
        print(f"    student #{h['student_id']} course #{h['course_id']}: source {h['source']} · zeka {h['zeka']}")
    print(f"  differences: {len(r['differences'])}")
    for d in r["differences"][:500]:
        print(f"    {d.get('file')} row {d.get('row', '-')}: {_az(d.get('reason')) or d.get('action')} {', '.join(d.get('fields') or [])}")
    print(f"  history reconciled: {r['history_reconciled']} students · sample for a person to check: {len(r['sample'])} records")
    if out:
        Path(out).write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("RECONCILED" if r["ok"] else "NOT RECONCILED")
    return 0 if r["ok"] else 1


def run_export(kind: str, since: str | None, registry: str, columns: str, out: str | None, term: int | None = None,
               version: int | None = None) -> int:
    """The same export service as the screen. Exit 0: written; 2: a wrong argument or a database that cannot be read."""
    try:
        moment = integration_rules.moment(since)
    except ValueError:
        print("error: --since must be an ISO date-time, e.g. 2026-12-01T00:00:00+04:00", file=sys.stderr)
        return 2
    if kind == "oneroster" and not out:
        print("error: the OneRoster export is a zip: give --out FILE", file=sys.stderr)
        return 2
    if not store.DB_PATH.exists():
        print(f"error: no database at {store.DB_PATH}", file=sys.stderr)
        return 2
    fd = None
    if out:                                            # opened first: a bad path writes no audit row; private (0600), like codes
        try:
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.chmod(out, 0o600)                       # an existing file keeps its mode on open
        except OSError as ex:
            print(f"error: {out}: {ex.strerror}", file=sys.stderr)
            return 2
    c = store.connect()
    try:
        name, _, body = export.run(c, kind, since=moment, registry=registry,
                                   columns=[x.strip() for x in columns.split(",") if x.strip()] or None, term_id=term, version_id=version)
        c.commit()                                     # the audit row of the export
    except (ValueError, sqlite3.Error) as ex:
        print(f"error: {_az(ex.args[0]) if isinstance(ex, ValueError) else ex}", file=sys.stderr)
        if fd is not None:
            os.close(fd)
        return 2
    finally:
        c.close()
    if fd is not None:
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
        print(f"{name}: {len(body)} bytes written to {out}", file=sys.stderr)
    else:
        sys.stdout.flush()
        sys.stdout.buffer.write(body)                  # UTF-8 whatever the console's encoding
        sys.stdout.buffer.flush()
    return 0


def run_activation_codes(faculty_code: str, out: Path) -> int:
    import csv
    try:
        store.init()
    except migrate.MigrationError as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 2
    c = store.connect()
    try:
        f = store.row(c, "SELECT id FROM faculties WHERE code=?", (faculty_code,))
        if not f:
            print(f"error: no faculty {faculty_code}", file=sys.stderr)
            return 2
        try:
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)      # private from the start; never overwrites
        except FileExistsError:
            print(f"error: {out} exists; codes are written once, to a new file", file=sys.stderr)
            return 2
        items = importer.issue_codes(c, None, f["id"])
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["student_no", "full_name", "group", "username", "code", "expires_at"])
            w.writerows([[integration_rules.csv_cell(x[k]) for k in ("student_no", "full_name", "group", "username", "code", "expires_at")]
                         for x in items])
        c.commit()                                     # the codes count only once the file holding them is written
    finally:
        c.close()
    print(f"{len(items)} codes written to {out}; the earlier unused codes of these students no longer work")
    return 0


if __name__ == "__main__":
    sys.exit(main())
