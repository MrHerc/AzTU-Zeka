# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Zəka — "AzTU Rəqəmsal Kampus": a digital campus portal demo (v0.3) for Azerbaijan Technical University. AI tutor grounded in
lecture materials, campus assistant, Test studio, 13 e-services with QR-verified documents, attendance/grades, news, teacher
AI Academy, support desk, leadership dashboard. Five roles: `student`, `teacher`, `office`, `leader`, `admin`.

Zero runtime dependencies by design: Python 3.10+ standard library only, vanilla ES-module JS, no build step.
Zəka Radar (`app/radar.py`, `app/r_radar.py`) adds explainable early warning with teacher support plans.
It is being turned from a demo into a product sold to universities — see "Product direction" below before adding features.

## Commands

```bash
python run.py --port 5070                 # start (http://127.0.0.1:5070); seeds data/campus.db on first run
python run.py --reset                     # wipe and re-seed the demo database
ZEKA_ACCESS_CODE=... python run.py --host 0.0.0.0 --public-url https://host   # reachable host: access code is mandatory

python -m pip install -r requirements-dev.txt     # dev tools only: pytest, ruff, mypy (the app has no runtime deps)
python -m pytest -q                               # 698 tests, about 65 s; uses a temp database, never touches data/
python -m pytest tests/unit/test_engine_quiz.py::test_name -q     # a single test
ruff check . && mypy                              # lint and type check (config in pyproject.toml)
for f in static/js/*.js; do node --check "$f"; done

python tools/i18n.py lint                 # user-visible strings not wrapped for translation (51 known findings)
python tools/i18n.py extract              # refresh i18n/source/*, write untranslated keys to i18n/todo/*.json
python tools/i18n.py build                # i18n/{en,ru}/*.json -> static/locales/*.json + app/locales/*.json
python tools/i18n.py stats                # coverage per language (must stay 100%)

docker compose up --build                 # demo container (loopback only, resets data on every start)
```

Tests: `tests/unit/` (pure logic), `tests/integration/` (real HTTP server on a temp database; `test_security_review.py`
and `test_radar.py` hold the checks ported from the old self-test). CI: `.github/workflows/ci.yml` (lint, types, JS syntax,
i18n catalogue, pytest on Python 3.10–3.13 and Windows) and `security.yml` (gitleaks, pip-audit, bandit).

Settings come from the environment (`app/security.py`): `ZEKA_ACCESS_CODE`, `ZEKA_ALLOW_OPEN_DEMO`, `ZEKA_SESSION_HOURS`,
`ZEKA_PROXY_HOPS`, `ZEKA_ACCESS_LOG`. `config.json` (git-ignored, copy from `config.example.json`) or the
`AZTU_LLM_PROVIDER/BASE_URL/API_KEY/MODEL` env vars switch the AI from the offline engine to a real LLM.

## Architecture

**Request path.** `run.py` → `app/web.py` (hand-written HTTP server on `http.server`, regex `Router`, `Request`/`Response`,
security headers) → `before()` in `app/common.py` (opens a SQLite connection per request, resolves the session from the
`zeka_sid` cookie or `X-Session` header, enforces `roles=`/`auth=` from the route decorator) → handler → `after()`
(commit on success, rollback on exception). Handlers return a `dict`/`list`; the dispatcher runs `i18n.localize()` over it
and serialises JSON. Raise `HTTPError(status, "Azerbaijani message")` for errors.

**Routes** live in `app/r_*.py`, one module per domain, registered by import order in `app/routes.py`
(`r_core` auth/profile/files, `r_learning` courses/tutor/campus/quizzes/teacher, `r_services` requests/documents,
`r_news`, `r_academy` academy/tools/syllabus, `r_admin`, `r_support`). Declare with
`@R("POST", "/api/x/{id:int}", roles=("teacher",))`. Role checks are on the decorator; object-level checks are explicit
helpers per handler (`course_access`, `_req_for`, `_ticket_for`, `file_access`) — every new handler that takes an id needs one.

**Storage.** `app/store.py` holds the whole schema (one `SCHEMA` string, ~40 tables, no foreign keys, JSON in TEXT columns
read with `J()`), the helpers `row/rows/setting/audit/notify`, and `seed()` which builds all demo data from `content/*.json|md`
deterministically (`random.Random(42)`). **`store.init()` deletes the database when `SCHEMA_VERSION` changes** — there are
no migrations. Bump `SCHEMA_VERSION` when you change `SCHEMA`; never do this once real data exists (migrations must come first).
Uploads are content-addressed under `data/uploads/<sha256>.bin`.

**AI.** `app/engine.py` = Azerbaijani-aware tokeniser/stemmer, in-process BM25 indexes (`INDEX["chunks"|"campus"|"questions"]`,
rebuilt at start), PII masking, rule-based question generation and grading, and the optional LLM client (`llm_chat`,
OpenAI-compatible / Azure / Anthropic over `urllib`). `app/tutor.py` composes answers: every answer must cite a retrieved
chunk; Socratic mode must not give final answers; the LLM path falls back to the offline engine on any failure.

**Documents.** `app/docs.py` renders official documents as server-side HTML with an inline SVG QR (`app/qr.py`, own encoder);
`/verify/{code}` is the public verification page. One-time view keys for `/doc`, `/syllabus`, `/api/files` are kept in
process memory (`common._DOC_KEYS`) — this breaks with more than one worker.

**Frontend.** `static/index.html` loads `static/js/main.js`, which imports every feature module; each module registers hash
routes with `route("/path/:id", handler)` from `core.js`. `core.js` has the escaping `html` tagged template (use `raw()` only
for trusted markup), `api.get/post/put/del`, modal/toast helpers and the Markdown renderer. `shell.js` owns per-role
navigation (`NAV`, `BOTTOM`, `QUICK`) — a new page needs a `route()` plus a `NAV` entry. CSS: `app.css` design tokens +
one `m-*.css` per module, linked in `index.html`.

**i18n is structural, not cosmetic.** The Azerbaijani source string is the key everywhere. JS: `t("… {x} …", { x })`.
Python: `S(text, lang)` for one language, `T3(text, **p)` / `E(...)` for an all-languages dict that `localize()` resolves in
the response, `S_()` as an extraction marker. Any new user-visible string must be wrapped, then `extract` → translate into
`i18n/en|ru/*.json` (rules in `i18n/BRIEF.md`) → `build`. Generated catalogs (`static/locales`, `app/locales`) are committed.
Editing an existing Azerbaijani string changes its key and silently drops its translations.

## Things that will bite you

- **Mixed line endings.** Some files are CRLF, others LF, and the merge moved several from CRLF to LF. Keep each file's
  existing endings until Task 2 (`.gitattributes`) normalises the repository in one commit.
- **Handlers read input through `req.body` typed accessors** (`body.str`, `body.int`, `body.obj`); a body that a handler
  does not read closes the connection. Malformed input must end as a translated 400, never a 500.
- **The demo login is still password-less for every role.** A reachable host requires `ZEKA_ACCESS_CODE`; anyone with the
  code can take any role, including admin. Real accounts are Task 10.
- **Rate limiters and one-time document keys live in process memory** (`app/security.py`, `common._DOC_KEYS`): they break
  with more than one worker (Task 7).
- Leadership-dashboard KPIs in `app/r_admin.py` are partly hard-coded literals — not measurements (Task 39).
- `docs/ARCHITECTURE.md` and `docs/API.md` were written against the pre-merge `main`: they still say sessions never expire,
  mention `tests/selftest.py`, and lack the access code and the Radar endpoints.
- `/api/demo/storyline` answers without the access code (ids only); it must not exist in prod mode (Task 5).
- Timestamps are naive local time; business logic assumes Asia/Baku.

## Branch state (2026-11-16)

The working branch `claude/tender-meitner-avsvvh` contains `main` plus all five open PRs (#1 audit, #2 docs, #3 security,
#4 Zəka Radar, #5 tests and CI), merged in the order #3, #5, #4, #2, #1 with their conflicts resolved, plus the spec, plan
and research. `main` is unchanged and the five PRs are still open against it; they are superseded by this branch.

## Product direction

AzTU is **replacing all of its existing systems** with this product (not an overlay). Read these before adding features:

- `SPEC.md` — objective, replacement matrix, capability map (stable module ids), target layout, code style, boundaries, success criteria.
- `tasks/plan.md` and `tasks/todo.md` — 6 phases, 44 tasks with acceptance criteria and verification commands, migration waves.
- `docs/CODEMAP.md` — what the current code really does, with file:line evidence and a capability inventory.
- `docs/research/` — market, law, SEB and NIST research, verbatim; `docs/report/zeka-vahid-hesabat.html` — the unified report.

Facts that shape the plan:

- The academic core has no write path today: attendance, grades, timetable, users, courses and enrolments are only created by
  `seed()`. A teacher cannot mark attendance or enter a grade.
- Throughput collapses under concurrency (256 req/s with 1 client, 47 with 20, errors at 300). Bounding concurrent handlers to
  2 per process restores it (226 req/s at 20 clients, 0 errors at 300) — measured, not yet implemented (Task 6).
- New code goes into `backend/zeka/modules/<id>/{domain,service,repo,routes}.py` once the restructure (Task 3) lands;
  `domain.py` has no I/O, SQL lives only in `repo.py`. The existing frontend is kept and extended.
- Third-party plugins (ponytail, agent-skills, ecc, claude-mem) do not load in cloud sessions; they work in local sessions.

## Working rules set by the owner

- Reply in Azerbaijani, in short sentences. End every reply with what was not verified and the remaining risk.
- Commit and push to the session's own working branch at every checkpoint without asking (standing permission from the
  owner, 2026-11-16, for the V1 sprint). `main`, other branches, tags, merging PRs and force-pushes still need asking first.
- Work in the order spec → plan → build → test → review → ship. For code review, try to refute each finding with a
  separate agent and fix only what is confirmed.
