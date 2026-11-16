# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Zəka — "AzTU Rəqəmsal Kampus": a digital campus portal demo (v0.3) for Azerbaijan Technical University. AI tutor grounded in
lecture materials, campus assistant, Test studio, 13 e-services with QR-verified documents, attendance/grades, news, teacher
AI Academy, support desk, leadership dashboard. Five roles: `student`, `teacher`, `office`, `leader`, `admin`.

Zero runtime dependencies by design: Python 3.10+ standard library only, vanilla ES-module JS, no build step.
It is being turned from a demo into a product sold to universities — see "Product direction" below before adding features.

## Commands

```bash
python run.py --port 5070                 # start (http://127.0.0.1:5070); seeds data/campus.db on first run
python run.py --reset                     # wipe and re-seed the demo database
python run.py --host 0.0.0.0 --public-url https://host   # server mode: QR links use this URL, cookie becomes Secure

python tests/selftest.py                  # the only test suite on main: one script, ~136 checks, RESETS the database
python tools/i18n.py lint                 # find user-visible strings not wrapped for translation
python tools/i18n.py extract              # refresh i18n/source/*, write untranslated keys to i18n/todo/*.json
python tools/i18n.py build                # i18n/{en,ru}/*.json -> static/locales/*.json + app/locales/*.json
python tools/i18n.py stats                # coverage per language (must stay 100%)
```

There is no single-test runner on `main`: `selftest.py` is one procedural script that starts an in-process server on a random
port. It depends on seed specifics, so changing `content/seed.json` can break checks. PR #5 replaces it with pytest
(`pytest tests/unit/test_x.py::test_name`), ruff and mypy — use those once it is merged.

No lint/format/type config exists on `main`. `config.json` (git-ignored, copy from `config.example.json`) or the
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

- **Mixed line endings.** 21 tracked files are CRLF (`app/store.py`, `app/engine.py`, `app/r_learning.py`, `static/js/main.js`, …),
  the rest LF. Keep each file's existing endings; do not let an editor normalise them. Merge the open PR branches with
  `-Xignore-cr-at-eol`, otherwise whole files conflict.
- **Unread request bodies desync keep-alive connections** on `main` (handlers that never call `req.json()`); fixed in PRs #3/#5.
- **Demo login is passwordless for every role including admin** (`/api/auth/demo`, `/demo/login`). Never expose `main` publicly.
- Leadership-dashboard KPIs in `app/r_admin.py` are partly hard-coded literals — not measurements.
- `aztu-ai-campus.zip` in the repo root is a stale snapshot with a database; do not read code from it (removed in PR #3).
- Timestamps are naive local time; business logic assumes Asia/Baku.

## Open work on other branches (as of 2026-11-16, none merged)

| PR | Branch | Content |
|---|---|---|
| #1 | `claude/fervent-newton-azzabh` | `docs/AUDIT.md` (47 findings), `docs/ROADMAP.md` (30/60/90 days) |
| #2 | `claude/wizardly-fermat-9hij0x` | new README, `docs/ARCHITECTURE.md`, `docs/API.md` |
| #3 | `claude/focused-hypatia-bdi95m` | security fixes, `app/security.py`, access code, `docs/SECURITY_REVIEW.md`, security CI |
| #4 | `claude/vibrant-mayer-nkiwis` | Zəka Radar (explainable early warning), Dockerfile, demo mode |
| #5 | `claude/festive-cerf-8tk3vl` | pytest suite, ruff/mypy, GitHub Actions CI, bug fixes |

#1 and #3 merge cleanly into `main`. #5 and #4 then conflict with #3 (about 20 and 11 real hunks; `app/web.py`,
`app/r_core.py`, `app/r_academy.py`, catalogs, `tests/selftest.py`). #3 and #5 fix the same HTTP-layer bugs differently — keep one.

## Product direction

The target is a unified university portal sold to Azerbaijani universities: real identity (SSO), syllabus management with
framework mapping, a safe-exam-browser mode, campus assistant with room finding, ask-the-teacher Q&A, club communities,
integrations, and security controls mapped to NIST. The owner wants the existing frontend kept and built upon, and code
separated by language and layer (backend / frontend / infra) with an explicit architecture.

## Working rules set by the owner

- Reply in Azerbaijani, in short sentences. End every reply with what was not verified and the remaining risk.
- Commit only when told to. Never push without asking first.
- Work in the order spec → plan → build → test → review → ship. For code review, try to refute each finding with a
  separate agent and fix only what is confirmed.
