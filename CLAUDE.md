# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Zəka — "AzTU Rəqəmsal Kampus": a digital campus portal demo (v0.3) for Azerbaijan Technical University. AI tutor grounded in
lecture materials, campus assistant, Test studio, 13 e-services with QR-verified documents, attendance/grades, news, teacher
AI Academy, support desk, leadership dashboard. Five roles: `student`, `teacher`, `office`, `leader`, `admin`.

Zero runtime dependencies by design: Python 3.10+ standard library only, vanilla ES-module JS, no build step.
Zəka Radar (`backend/zeka/legacy/radar.py`, `backend/zeka/legacy/r_radar.py`) adds explainable early warning with teacher support plans.
It is being turned from a demo into a product sold to universities — see "Product direction" below before adding features.

## Commands

```bash
python backend/run.py --port 5070                 # start (http://127.0.0.1:5070); seeds data/campus.db on first run
python backend/run.py --reset                     # wipe and re-seed the demo database
python backend/run.py --workers 4                 # N processes on one port (Linux/macOS, SO_REUSEPORT); /healthz names the worker
ZEKA_MODE=prod ZEKA_PROXY_HOPS=1 python backend/run.py --host 0.0.0.0 --public-url https://host   # real deployment
python backend/manage.py status | migrate | create-admin --username U --name "Full Name"   # schema and first admin
python backend/manage.py import --kind users --source old-sis --file F.csv [--dry-run] [--prefer source]   # Task 16
python backend/manage.py import --kind attendance|attendance-opening|grades --as-of D ... | --kind results | --kind status-events --by USER   # Task 38
python tools/etl/run.py --mapping content/mappings/SRC.json --dir EXPORT --wave 0 --as-of D --by USER [--dry-run]   # a wave's ETL (Task 38)
python backend/manage.py reconcile --wave 0 --source SRC --dir data/migration/SRC-wave0 [--out report.json]   # Task 38
python backend/manage.py activation-codes --faculty CODE --out codes.csv   # one-time student codes for a dean's office
python backend/manage.py export --kind grades|attendance|oneroster|registry|status-changes [--since ISO] [--out F]   # Task 37
python backend/manage.py jobs status | run          # periodic jobs (Task 36): each job's last run; run what is due now
python backend/manage.py exam-verify ID [--root HEX]  # an exam's hash chain, frozen answers and scores (Task 30)
python backend/manage.py import-routes --building EK --nodes N.csv --edges E.csv   # a building's route graph (Task 31)
python backend/manage.py forma3-check FILE.xlsx [--json]   # a department's Forma №3 before upload: controls, counts, conflicts by cell (Task 47)
python tests/fixtures/make_fixtures.py            # rewrites the synthetic Forma №3 and 10k-user fixtures

python -m pip install -r requirements-dev.txt     # dev tools only: pytest, ruff, mypy (the app has no runtime deps)
python -m pytest -q                               # 2016 tests, about 12 min; uses a temp database, never touches data/
python -m pytest tests/unit/test_engine_quiz.py::test_name -q     # a single test
ruff check . && mypy                              # lint and type check (config in pyproject.toml)
for f in frontend/js/*.js; do node --check "$f"; done
python tools/loadtest.py --scenario read --users 300 --seconds 30 --dataset faculty [--workers 4]   # docs/perf/baseline.md
python tools/loadtest.py --scenario exam --users 300 --seconds 300 --dataset faculty [--burst]      # Task 27: lost answers must be 0
python tools/queryplan.py --dataset university    # full scans of tables > 1 000 rows on the read routes and the timetable builder's (must be none)
python tools/eval_assistant.py tests/eval/assistant_az.jsonl   # campus assistant: 50 questions, at least 45 right (Task 32)
python tools/ttbench.py --units 1250 [--groups 300 --teachers 90 --rooms 60 --iters 50000]   # timetable solver timings (Task 48, docs/perf/timetable.md)
python backend/manage.py jobs run                  # also one chunk of the oldest queued timetable builder run (job timetable.work, every 30 s; pages /admin/timetable/build, /dept/timetable, /office/timetable, /teacher/availability)

python tools/i18n.py lint                 # user-visible strings not wrapped for translation (72 known: official documents are Azerbaijani)
python tools/i18n.py extract              # refresh i18n/source/*, write untranslated keys to i18n/todo/*.json
python tools/i18n.py build                # i18n/{en,ru}/*.json -> frontend/locales/*.json + backend/zeka/core/locales/*.json
python tools/i18n.py stats                # coverage per language (must stay 100%)
python tools/i18n.py rename MAP.json [--apply]   # rewrite Azerbaijani keys {old: new} in code, content, tests and en/ru (dry run by default)

docker compose -f infra/compose.demo.yml up --build            # demo container (loopback only, resets data on every start)
docker compose -f infra/compose.yml up -d --build              # prod: Caddy (TLS) + app, infra/.env, docs/runbooks/deploy.md
infra/backup.sh && infra/restore.sh backups/latest.enc /tmp/restore-test   # encrypted backup, docs/runbooks/backup.md
```

Tests: `tests/unit/` (pure logic), `tests/integration/` (real HTTP server on a temp database; `test_security_review.py`
and `test_radar.py` hold the checks ported from the old self-test), `tests/migration/`, `tests/load/` (query plans on the
university dataset). The suite sets `ZEKA_TX_GUARD=1`: a request that holds the write lock for more than 200 ms of its handler thread's CPU
time, or 1 s of wall time, fails its test (`TX_GUARD_EXEMPT` in `legacy/common.py` lists the few exempt routes). CI: `.github/workflows/ci.yml` (lint, types, JS syntax,
i18n catalogue, pytest on Python 3.10–3.13 and Windows) and `security.yml` (gitleaks, pip-audit, bandit).

Settings come from the environment: `ZEKA_MODE` (`demo` default, `prod`; `backend/zeka/core/config.py`), `ZEKA_TZ`
(default `Asia/Baku`; `backend/zeka/core/clock.py`), `ZEKA_DATA` (database and uploads, default `data/`), `ZEKA_WORKERS`,
`ZEKA_HANDLERS`/`ZEKA_SLOW`/`ZEKA_QUEUE_WAIT` (the handler gate in `backend/zeka/core/web.py`), `ZEKA_JOBS` (`0` turns the
periodic job runner off) and `ZEKA_JOBS_DELAY` (seconds before its first cycle, default 15) and, in
`backend/zeka/core/security.py`, `ZEKA_ACCESS_CODE`, `ZEKA_ALLOW_OPEN_DEMO`,
`ZEKA_PROXY_HOPS`, `ZEKA_ACCESS_LOG`; `ZEKA_SECURITY_CONTACT` and `ZEKA_SECURITY_EXPIRES` (the `/.well-known/security.txt` contact and its review date, Task 41); in `backend/zeka/core/mail.py`, `ZEKA_SMTP_HOST/PORT/TLS/USER/PASSWORD/FROM`
(Task 36: without a host nothing is e-mailed). `config.json` (git-ignored, copy from `config.example.json`) or the
`AZTU_LLM_PROVIDER/BASE_URL/API_KEY/MODEL` env vars switch the AI from the offline engine to a real LLM.

## Architecture

**Request path.** `backend/run.py` → `backend/zeka/core/web.py` (hand-written HTTP server on `http.server`, regex `Router`, `Request`/`Response`,
security headers) → `before()` in `backend/zeka/legacy/common.py` (opens a SQLite connection per request, resolves the session from the
`zeka_sid` cookie only (the database keeps its SHA-256; idle/absolute limits per role), enforces `roles=`/`auth=` from the route decorator) → handler → `after()`
(commit on success, rollback on exception). Handlers return a `dict`/`list`; the dispatcher runs `i18n.localize()` over it
and serialises JSON. Raise `HTTPError(status, "Azerbaijani message")` for errors. At most `ZEKA_HANDLERS` (2) handlers run at
once per process (`slow=True` routes, which wait on the network, have their own 4 slots); a request that waits longer than
`ZEKA_QUEUE_WAIT` gets 503 + `Retry-After`. With `--workers N` the supervisor runs `store.init()` (migrations, seed, one
search-index build), freezes the heap (`gc.freeze()`) and forks; workers share the index pages and restarted ones only
apply the change log. The supervisor also forks the periodic job runner (`backend/zeka/core/jobs.py`; the jobs
register in `backend/zeka/legacy/periodic.py`) and restarts it like a worker; a single process runs it in a thread. One
runner works at a time (a lease row), each run is a `job_runs` row.

**Routes** live in `backend/zeka/legacy/r_*.py`, one module per domain, registered by import order in `backend/zeka/legacy/routes.py`
(`r_core` auth/profile/files, `r_learning` courses/tutor/campus/quizzes/teacher, `r_services` requests/documents,
`r_news`, `r_academy` academy/tools/syllabus, `r_admin`, `r_support`). Declare with
`@R("POST", "/api/x/{id:int}", roles=("teacher",))`. Role checks are on the decorator; object-level checks are explicit
helpers per handler (`course_access`, `_req_for`, `_ticket_for`, `file_access`) — every new handler that takes an id needs one.

**Storage.** The schema is `backend/migrations/*.sql` (42 tables in `0001_baseline.sql`, no foreign keys, JSON in TEXT columns
read with `J()`), applied by `backend/zeka/core/migrate.py` with a backup first. `backend/zeka/legacy/store.py` has the helpers
`row/rows/setting/audit/notify`, `seed_catalog()` (product content, also in prod) and `seed()` (all demo data from
`content/*.json|md`, deterministic, `random.Random(42)`). Uploads are content-addressed under `data/uploads/<sha256>.bin`.

**AI.** `backend/zeka/legacy/engine.py` = Azerbaijani-aware tokeniser/stemmer, in-process BM25 indexes (`INDEX["chunks"|"campus"|"questions"]`,
rebuilt at start), PII masking, rule-based question generation and grading, and the optional LLM client (`llm_chat`,
OpenAI-compatible / Azure / Anthropic over `urllib`). Code that changes a chunk, KB entry or question calls `store.log_index()`;
every request runs `store.sync_indexes()` (one indexed `MAX(seq)` when nothing changed), so all workers see the change. `backend/zeka/legacy/tutor.py` composes answers: every answer must cite a retrieved
chunk; Socratic mode must not give final answers; the LLM path falls back to the offline engine on any failure.

**Documents.** `backend/zeka/legacy/docs.py` renders official documents as server-side HTML with an inline SVG QR (`backend/zeka/legacy/qr.py`, own encoder);
`/verify/{code}` is the public verification page. One-time view keys for `/doc`, `/syllabus`, `/api/files` are rows in
`doc_keys`, taken with `DELETE … RETURNING` so exactly one request in any worker can use a key.

**Frontend.** `frontend/index.html` loads `frontend/js/main.js`, which imports every feature module; each module registers hash
routes with `route("/path/:id", handler)` from `core.js`. `core.js` has the escaping `html` tagged template (use `raw()` only
for trusted markup), `api.get/post/put/del`, modal/toast helpers and the Markdown renderer. `shell.js` owns per-role
navigation (`NAV`, `BOTTOM`, `QUICK`) — a new page needs a `route()` plus a `NAV` entry. CSS: `app.css` design tokens +
one `m-*.css` per module, linked in `index.html`.

**i18n is structural, not cosmetic.** The Azerbaijani source string is the key everywhere; new source text follows
`i18n/STYLE.md` and the glossary in `i18n/BRIEF.md`. JS: `t("… {x} …", { x })`.
Python: `S(text, lang)` for one language, `T3(text, **p)` / `E(...)` for an all-languages dict that `localize()` resolves in
the response, `S_()` as an extraction marker. Any new user-visible string must be wrapped, then `extract` → translate into
`i18n/en|ru/*.json` (rules in `i18n/BRIEF.md`) → `build`. Generated catalogs (`frontend/locales`, `backend/zeka/core/locales`) are committed.
Editing an existing Azerbaijani string changes its key and silently drops its translations: use `tools/i18n.py rename`,
which moves them, and give a seeded text already in databases a migration (`0463`, `0464`: a column changes only while it
holds the old seeded text). A parameter taken from a file or typed by a person is `i18n.Lit(...)` (shown as written, never
translated); a date in a message is `i18n.date3(d)` (each language's format). One key means one sense: split a key
rather than share it between, say, a load type and a tip label.

## Things that will bite you

- **Line endings.** `.gitattributes` keeps every text file LF; `.bat`/`.cmd`/`.ps1` are CRLF. Do not commit CRLF elsewhere.
- **Layers.** `backend/zeka/core/` must not import `legacy/` or `modules/`; `modules/*/domain.py` has no I/O
  (`tests/unit/test_layers.py`). Web URLs stay `/static/...` although the files live in `frontend/`.
- **Handlers read input through `req.body` typed accessors** (`body.str`, `body.int`, `body.obj`); a body that a handler
  does not read closes the connection. Malformed input must end as a translated 400, never a 500.
- **Two ways in.** Demo mode keeps the password-less role login (a reachable host needs `ZEKA_ALLOW_OPEN_DEMO=1`;
  anyone with `ZEKA_ACCESS_CODE` can take any role). `ZEKA_MODE=prod` has no demo routes (`@R(..., demo=True)`), never
  seeds people or deletes the database, and signs in with passwords: `backend/zeka/modules/identity/` (scrypt, NIST
  policy, throttling per account and client in `login_blocks`, temporary passwords with `must_change`). A refused
  sign-in is *returned* as a 401/429 response, not raised, so the failure count commits. `manage.py create-admin` prints
  a temporary password. Sessions (Task 11): cookie only, SHA-256 in `sessions.id_hash`, `rotate_session()` after a privilege
  change, `_own_commit()` for bookkeeping writes in `before()` so a request stays a reader.
- **Schema changes go through `backend/migrations/NNNN_name.sql`** (number = task × 10, a second file of the same task takes
  the next number, e.g. `0071`); never edit an applied file: the server refuses to start on a changed checksum.
- **Process memory is per worker.** State that must hold across `--workers` lives in the database: one-time keys (`doc_keys`),
  named rate limiters (`security.LIMITS` → `rate_hits`, own short transaction), search-index changes (`index_changes`).
- **Every route is in `tests/security/matrix.json`** (who may call it, demo, slow, `perm`, `audit_read`). A new or changed
  route fails `tests/security/test_authz_matrix.py` until you run `python tests/security/test_authz_matrix.py` and review
  the diff. Roles and permissions: `backend/zeka/core/perms.py`; `@R(..., perm="roles.grant")` instead of `roles=`.
  A person has a primary role (`users.role`) plus `role_grants` with a scope; a session acts in one (`sessions.role`).
- **Exam sessions (Task 27).** A session with `sessions.scope='exam:{id}'` reaches only `@R(..., scope="exam")` routes of
  that exam, and those routes refuse every other session (`_exam_scope()` in `legacy/common.py`). A new exam-page route
  needs `scope="exam"`; a refusal that must leave an exam event is returned as a 403 response, not raised.
  Task 29 adds the exam's network list to every such request (`exam.service.check_request`, committed before the 403)
  and the proctor board (`/proctor`, `frontend/js/proctor.js`, polled every 5 s).
- **Exam log (Task 30, Checkpoint D).** `exam_events` is a hash chain and append-only (triggers in `0301`): a test that
  tampers with it drops and re-creates the triggers (`tamper()` in `tests/integration/test_exam_verify.py`). Every exam
  state change calls `repo.lock(c)` (`BEGIN IMMEDIATE`) before it reads the state it checks.
- **Modules call each other's `service.py`, never their `repo.py`** (`tests/unit/test_layers.py`, Checkpoint E); from
  `legacy/` too. A provider without the function gets a one-line pass-through in its service.
- **E-service steps (Task 46).** Each step of a request type has one role (`request_types.step_roles`); only that role,
  within its scope (`legacy/common.covers`), acts on it; admin never; `issue` only on the last step. The last step runs
  the type's `effect` (`r_services.EFFECTS`); `effect = none` answers with the factual template. A type is offered only
  when `enabled` (prod: 0 until the administrator opens it). Request types in prod come from `0461`, not the seed.
- **Forum privacy (Checkpoint E).** A question forwarded from the tutor is a private topic (`teacher_questions.private`):
  its author and the course's teachers only, and an anonymous one hides the name from the teacher too.
- **Outbound HTTP (webhooks).** `integration/webhooks.py` follows no redirects, refuses non-public addresses in prod at
  send time, and catches every exception per delivery; a new outbound call copies that, never `urllib.request.urlopen`.
- **Migration (Task 38).** The old system's journal records, final grades and status orders are import kinds
  (`attendance`, `results`, `status-events`) written by `modules/migration/loaders.py` through the owning module's
  service. A writing import refuses while an exam is open (`--force`, audited) and a file over 199 999 rows
  (`tools/etl/run.py` splits). `manage.py reconcile` re-reads the wave's logged files (`migration_files`) as a dry run.
- **Forma №3 (Task 47).** `integration/forma3.py` is pure: `read(sheets) -> Form` (posts, units, load lines, links, notes,
  conflicts, controls T1–T6); the rules and their ids are `docs/forms/forma-3.md`. A re-import lists the earlier units
  this file no longer applies (`stale`) and, on apply, sets those of a blocked or vanished post inactive (Checkpoint F). A semester is the columns between the
  `Cəmi` columns, a unit is a valued top-left contact cell and its groups are the rows its merge covers; nothing is read
  from a sheet's name or a row's position. The import applies only posts that pass T1–T3 with no blocking conflict;
  every non-empty cell must end somewhere (`Form.unclassified == 0`). The departments' real files hold staff names and
  never enter the repository: tests use `tests/fixtures/make_fixtures.py`, places are named by cell ref only.
- **No full scans on hot paths.** A new read route or query on a growing table needs an index; `tests/load/test_query_plans.py`
  fails on a scan of a table with more than 1 000 rows in the read scenario.
- **Measured indicators (Task 39).** The leadership tiles and the accreditation evidence page (`/leader/evidence`) are
  queries in `modules/insight/` over real rows; a number that cannot be measured is not a tile. `after()` writes one
  `events` row for a signed-in request that changed rows, `start_session` one per sign-in, and a session's first request
  of a day one `visit` (kept 365 days). Targets are pilot constants in `insight/service.py`.
- **Personal data (Task 40).** Every column that holds a person is in `identity/repo.INVENTORY` (export condition and
  erase action: delete, keep or anonymise) and in `docs/privacy/data-inventory.md`; `tests/integration/test_privacy.py`
  fails on a new one until both list it. An external LLM is called only with a consent to the current text version
  (`identity/privacy.allowed`); retention periods are university settings purged by `retention.purge`.
- **Timetable solver (Task 48).** `modules/timetable/solver.py` is pure like a `domain.py` (no clock, no I/O, no
  repo; `test_layers.py`): ints only and `rng.random()` only, so one seed gives the same bytes on every Python (the
  golden signature in `tests/unit/test_tt_props.py` changes with any solver change: recompute it on purpose). Its state
  never holds a hard violation; `domain.check` is the independent checker and `domain.scorecard` must equal the
  solver's running cost. Week sets are bit masks (`domain.week_mask`/`week_text`: `all | odd | even | N[-M],...`).
- **Timetable builder (Task 48, slice 2).** `modules/timetable/builder.py` is the builder's service (no SQL: its SQL is
  in `repo.py`, `test_layers.py`), routes under `/api/timetable/build/{term}` and `/api/timetable/versions/{id}`.
  `scope_of()` gives what a role covers; every id outside it is 404. Settings and a term's plan need a university-wide
  scope (403 otherwise); a run or a base version must cover the version's stored scope (`_covers_scope`); a draft
  limited to named departments is visible only to a caller covering each, and a scorecard lists only the caller's
  units' problems. S10 counts the weeks a placement really holds (`domain.lost_weeks`: holidays, term edges). No request computes a term: runs (`precheck`,
  `solve`, `check`, `publish`) are `tt_runs` rows worked by the job `timetable.work` (30 s), one per term at a time.
  A move is checked live against its neighbourhood, then `bump_rev` (optimistic lock) inside one short write. A
  publication runs check → rows → drop → lessons → notify → done, each batch with its cursor in one transaction;
  while it runs, hand-written rows answer 409. A row a version published carries the version's effective date:
  `make_lessons` never makes its lessons earlier. Units with hand-written rows stay out of runs (no adoption yet) and
  their builder rows stay through a publication. A publication past its check never fails: an error retries from the
  stored step and cursor with the term locked. A run's error is stored as JSON in every language (`_err`), a titled
  and named problem list goes to `progress.problems`. The weekly schedule (`/api/schedule`) reads the week's lessons
  (`timetable.service.week_of`), never a row's current time alone.
- **Time.** Use `store.now()` (naive Baku wall clock, `ZEKA_TZ`) or `clock.now()` (aware UTC); `datetime.now()` and
  `date.today()` fail lint outside `backend/zeka/core/clock.py`. `tests/conftest.py` anchors the suite's today at
  2026-11-19 10:00 Baku (the demo term is seeded around today); a test of another date patches `clock.now`, and a test
  never reads the real date.

## Branch state (2026-11-22)

The working branch `claude/tender-meitner-avsvvh` contains `main` plus all five open PRs (#1 audit, #2 docs, #3 security,
#4 Zəka Radar, #5 tests and CI), merged in the order #3, #5, #4, #2, #1 with their conflicts resolved, plus the spec, plan
and research, then Faza 1 (Tasks 1–9, Checkpoint A), Faza 2 (Tasks 10–17, Checkpoint B: `docs/review/checkpoint-b-2026-11-18.md`) and Faza 3 (Tasks 18–22 and 45, Checkpoint C: `docs/review/checkpoint-c-2026-11-19.md`) and Faza 4 (Tasks 23 and 25–30, with Task 36's job runner and e-mail outbox; Checkpoint D: `docs/review/checkpoint-d-2026-11-19.md`; Task 24 is blocked: the NICE file's host is refused by this environment's proxy) and Faza 5 (Tasks 31–35, 37 and 46; Checkpoint E: `docs/review/checkpoint-e-2026-11-19.md`) and Faza 6 so far (Tasks
38–43, the owner's decisions of 2026-11-21, Task 47's Forma №3 reader, Task 48's timetable builder and the language
change; Checkpoint F: `docs/review/checkpoint-f-2026-11-22.md`, every confirmed finding fixed). Task 44 (release) waits
for the owner's inputs (`docs/runbooks/release-v1.md`): Checkpoint F's gate is not passed. `main` is unchanged and the five PRs are still open against it; they are
superseded by this branch.

## Product direction

AzTU is **replacing all of its existing systems** with this product (not an overlay). Read these before adding features:

- `SPEC.md` — objective, replacement matrix, capability map (stable module ids), target layout, code style, boundaries, success criteria.
- `tasks/plan.md` and `tasks/todo.md` — 6 phases, 48 tasks with acceptance criteria and verification commands, migration waves,
  record owner per entity. `docs/review/plan-review-2026-11-16.md` — the 24 review findings and the fixes applied.
- `docs/CODEMAP.md` — what the current code really does, with file:line evidence and a capability inventory.
- `docs/research/` — market, law, SEB and NIST research, verbatim; `docs/report/zeka-vahid-hesabat.html` — the unified report.

Facts that shape the plan:

- The academic core has no write path today: attendance, grades, timetable, users, courses and enrolments are only created by
  `seed()`. A teacher cannot mark attendance or enter a grade.
- Throughput: one process gives about 270 req/s on the read scenario at 300 clients with 0 errors, on the demo, faculty and
  university datasets alike; 4 processes about 830 (Tasks 6–7, `docs/perf/baseline.md`). Before the gate it fell to 47 at 20
  clients.
- New code goes into `backend/zeka/modules/<id>/{domain,service,repo,routes}.py`; `domain.py` has no I/O, SQL lives
  only in `repo.py`, routes register on the legacy router (`legacy/routes.py` imports them). `identity` is the first. The existing frontend is kept and extended.
- Third-party plugins (ponytail, agent-skills, ecc, claude-mem) may be missing at the start of a cloud session; they load after a resume.

## Working rules set by the owner

- Reply in Azerbaijani, in short sentences. End every reply with what was not verified and the remaining risk.
- Commit and push to the session's own working branch at every checkpoint without asking (standing permission from the
  owner, 2026-11-16, for the V1 sprint). `main`, other branches, tags, merging PRs and force-pushes still need asking first.
- Work in the order spec → plan → build → test → review → ship. For code review, try to refute each finding with a
  separate agent and fix only what is confirmed.
