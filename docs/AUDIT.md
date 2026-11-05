# Zəka (AzTU Rəqəmsal Kampus) — Technical Due-Diligence Audit

| | |
|---|---|
| **Repository** | `MrHerc/AzTU-Zeka`, branch `main` @ `a59ef1f` (2026-10-13) |
| **Audit date** | 2026-11-05 |
| **Prepared for** | Seed-stage investor, technical due diligence |
| **Prepared by** | CTO-level review (read of the entire repository, test run, live protocol probes) |
| **Companion document** | [`docs/ROADMAP.md`](ROADMAP.md) — prioritized 30/60/90-day plan to an investor-ready MVP |

> **Severity scale used throughout.** **Critical** — exploitable or blocks any real deployment today. **High** — must be fixed before a pilot with real users. **Medium** — fix during the MVP build. **Low** — backlog / hygiene.
> Every finding links to the exact file and line in this repository.

---

## 1. Executive summary

**What this is.** A single-developer, dependency-free (Python stdlib + vanilla ES-module JS) **demo** of an AI-assisted digital campus for Azerbaijan Technical University: a Socratic AI tutor grounded in lecture materials with citations, an e-services desk (13 request types, QR-verifiable documents), attendance/grades, news/events, a teacher "AI Academy", support desk with SLAs, and a leadership dashboard. It is trilingual (AZ/EN/RU) with 100 % catalog coverage and ships with a rich, deterministic synthetic dataset for a 12-minute scripted demo.

**Verdict in one line.** *High-quality demo, zero production infrastructure.* The code is unusually coherent and careful for a prototype, the domain modelling is deep, and localisation is genuinely differentiated. But there is **no authentication**, the public deployment exposes a **passwordless admin role that can wipe the database**, the HTTP layer has a **confirmed protocol bug**, the "AI" is by default a **rule-based heuristic** (an LLM is optional and untested in production), and the leadership dashboard **mixes hard-coded marketing numbers with computed ones**. None of this is hidden maliciously — the UI labels everything "DEMO" — but an investor must evaluate it as a prototype that proves product vision and execution speed, not as a product with users.

**Headline numbers**

| Metric | Value |
|---|---|
| Backend (Python, `app/`) | 5,561 LOC in 21 modules, 107 HTTP routes (6 unauthenticated), 40 SQLite tables |
| Front-end (JS/CSS) | 4,549 LOC JS (16 modules, no build step), 1,296 LOC CSS |
| Content | 16 lecture materials, 43 bank questions, 10 quizzes, 13 e-service workflows, 14 news, 18 sourced achievements, 25 tools, 7 academy tracks / 28 modules, 30 guides, 13 FAQ |
| i18n | 3,489 strings, EN + RU at **100 %** coverage (`tools/i18n.py stats`) |
| Tests | 1 script, **136 checks, all pass** (`python tests/selftest.py`, Python 3.13.18) — mostly happy-path, no CI |
| External dependencies | **0** (by design) |
| Git history | **9 commits, 1 GitHub account, 8 days** (2026-10-06 → 10-13); earlier versions (v0.1–v0.2) are not in history; `main` contains a 2 MB zip uploaded via the GitHub web UI |
| Deployment | Render.com free plan, stdlib HTTP server bound to `0.0.0.0`, ephemeral disk (DB re-seeded on every restart) |

**Top risks (fix order)**

1. **[S-01 Critical]** Passwordless login for every role, including `admin`, on a public URL; `admin` can wipe and re-seed the database with one POST.
2. **[M-01 Critical]** No identity layer at all (no passwords, SSO, MFA, provisioning). The product cannot onboard a single real user.
3. **[R-01 High]** HTTP keep-alive desync: 13 POST routes never read the request body, so the *next* request on the same connection fails with `501` (confirmed by probe).
4. **[R-03 High]** Graded quizzes are not trustworthy: no server-side time limit, attempt limits can be bypassed by opening attempts in parallel, and the full answer key is returned after the first submission.
5. **[P-01 High]** Leadership KPIs such as "WAU 64 %", "−41 % prep time", "+0.28 SD learning gain", "$0.42 AI cost/student" are hard-coded literals, not measurements.
6. **[R-02 High]** Destructive schema strategy: any schema change deletes the database; no migrations, no backups, SQLite on an ephemeral disk.
7. **[M-05 High]** Default AI engine is BM25 + templates; the LLM path is synchronous, unmonitored, has no evaluation set and no prompt-injection defence.

**What is genuinely strong (and worth paying for)**

- Domain depth: real workflow state machines (requests, SLAs, document issuance/revocation, support desk), not screens.
- Localisation: Azerbaijani-aware stemming/tokenisation, Russian plural rules, a custom lint/extract/build toolchain, 100 % coverage.
- Security *hygiene* in the code: parameterised SQL everywhere, consistent HTML escaping on both sides, magic-byte file validation with content-addressed storage, path-traversal protection, CSP with `script-src 'self'`, HttpOnly cookies, per-route role checks, one-time document links, audit trail of file views, PII masking before any LLM call.
- UX polish: skeletons, empty/error states, page tours, mobile layout, dark mode, keyboard focus management, reduced-motion support.
- Reproducibility: deterministic seed (`random.Random(42)`), self-test that exercises the whole API surface.

**Estimated distance to an investor-ready MVP** (see Roadmap): ~90 days with 2–3 engineers, *provided* the AzTU relationship (SSO, registry data, brand permission) is secured in the first 30 days. The riskiest items are organisational (university access, legal validity of e-documents, IP/brand rights), not technical.

---

## 2. Scope, method and assumptions

**Read in full:** every file in the repository (Python backend, JS front-end, CSS, content JSON/Markdown, i18n catalogs and tooling, deployment files, README), plus the contents of the committed `aztu-ai-campus.zip` (which includes internal dev notes `.dev/CONTRACT.md` and `.dev/plan-v03.md`, a SQLite snapshot and server logs).

**Executed (read-only against the repo, writes only to the git-ignored `data/` and `logs/`):**

- `python -m compileall` — OK on Python 3.13.18.
- `python tests/selftest.py` — **ALL PASSED** (136 checks).
- `python tools/i18n.py stats` / `lint` — 100 % coverage; 47 lint findings (Azerbaijani f-strings in generated-content templates; see T-03).
- A protocol/authorisation probe script (results in §9.2): keep-alive body handling, server-side quiz deadline, `GET /demo/login?role=admin`, consent enforcement, PII false positives, response headers.
- Git history inspection for secrets (none found; `config.json` is git-ignored and never committed).

**Not executed:** browser-based end-to-end tests, load tests, a full penetration test, a review of the live Render deployment (URL not in repo), and verification of the AzTU relationship/IP status.

**Assumptions** (also listed in the pull request): the target is a B2B SaaS/pilot with AzTU as the design partner; "investor-ready MVP" means *real users in one pilot cohort with real data and honest metrics*, not feature completeness; the company intends to keep Python for the backend; English is acceptable for investor-facing documents even though the codebase is Azerbaijani-first.

---

## 3. What the product does

### 3.1 Roles and modules

| Role (demo login) | What they get |
|---|---|
| **Student** (`aysel`) | Dashboard, weekly timetable, courses with lecture materials and "recommended sources", **AI tutor** (Socratic / Explain / Practice modes, citations to material chunks, forward-to-teacher), **campus assistant** (rules KB with actions), quizzes with timer and explanations, attendance with "excuse absence" flow, grades + synthetic transcript, **e-services** wizard (13 request types, attachments, status tracking, chat with dean's office), news/events (RSVP, `.ics`), support tickets, feedback, guides/tours, achievements, contact. |
| **Teacher** (`rauf`) | Dashboard with tutor insights (top topics, "no-source" gaps), material upload (DOCX/PPTX/TXT/MD → chunks + glossary + index), tutor mode/rules/lock settings, **Test Studio** (rule-based question generation → review → approve → publish quiz → results analytics), student questions inbox, course attendance view, **AI Academy** (7 tracks, 28 modules, quizzes, QR certificates, self-assessment → recommendations), tech-tools catalogue, **syllabus assistant** (generates a 15-week syllabus from materials; print view). |
| **Dean's office** (`nigar`) | Request queue with SLA countdowns, approve/return/reject/issue, document preview and issuance (registry number, verification code, QR, SHA-256), document registry with revocation, request messaging, support desk, news editor. |
| **Leadership** (`rektorluq`) | Pilot KPI dashboard, course table, insights, feedback/NPS analytics, audit log, registry read access. |
| **Admin** (`admin`) | LLM provider status/test, limits (daily questions, PII masking, retention), DB counts, **demo reset**, audit log. |
| **Public** | `/verify/{code}` document verification page, `/api/achievements`, `/api/contact`. |

### 3.2 Value proposition as implemented
1. *Grounded AI tutoring in Azerbaijani* — answers are composed only from teacher-uploaded materials and always cite a chunk; Socratic mode refuses to give final answers (regex guardrail). With `config.json`, an OpenAI-compatible / Azure / Anthropic model is used with the same sources in the system prompt; on any failure it falls back to the offline engine.
2. *Paperless student services* — a configurable form schema per request type (`content/seed.json`), validation, SLA, multi-step approval, document templates, QR verification, revocation.
3. *Teacher productivity and upskilling* — AI question drafts with teacher-in-the-loop approval, syllabus drafting, professional development with certificates.
4. *Trilingual, mobile, accessible UX* — the strongest polish layer in the codebase.

### 3.3 What is demo-only (and labelled as such in the UI)
Passwordless role switching; all users, courses, grades, attendance, requests, news, tickets and feedback are synthetic (`app/store.py` seed); documents carry a "DEMO — no legal validity" watermark; SSO and LMS integration are shown as "planned" in the system-status card; the AI engine badge reads "Demo AI mühərriki (oflayn)" unless an LLM is configured.

---

## 4. Architecture

### 4.1 Runtime topology

```
Browser (vanilla ES modules, hash router, fetch JSON, X-Lang/X-Session headers)
   │   static/index.html → static/js/main.js → 15 feature modules; CSS design tokens; locale JSON
   ▼
ThreadingHTTPServer (stdlib http.server, HTTP/1.1 keep-alive)            app/web.py
   ├─ Router (regex, {id:int} params, roles, auth flag)                   app/web.py:81-105
   ├─ before(): open SQLite conn, resolve session (cookie or X-Session)   app/common.py:37-47
   ├─ route modules r_core / r_learning / r_services / r_news /
   │               r_academy / r_admin / r_support                        app/routes.py
   ├─ after(): commit/rollback/close; localize() every JSON response      app/web.py:148-149, app/i18n.py
   ▼
SQLite (WAL) data/campus.db + content-addressed uploads data/uploads/<sha256>.bin
In-process BM25 indexes (chunks, campus KB, questions)                    app/engine.py:118-169
Optional outbound HTTPS → LLM provider (urllib, blocking)                 app/engine.py:323-349
```

- **No web framework, no ORM, no task queue, no cache, no message bus.** One Python process, threads per connection.
- **Content as code:** `content/*.json|md` is loaded at seed time into SQLite; `references.json` and `achievements.json` are read from disk at request time.
- **i18n:** the Azerbaijani source string is the key; the client fetches `static/locales/{en,ru}.json`; the server walks every JSON response and translates matching strings/i18n dicts (`app/i18n.py:117-141`); catalogs are generated by `tools/i18n.py build`.
- **Documents:** server-rendered HTML with inline SVG QR codes (`app/qr.py`), printed to PDF by the browser; integrity = SHA-256 of the payload stored in the `documents` row.
- **Deployment:** `render.yaml` (free plan, Frankfurt, `python run.py --host 0.0.0.0 --port $PORT`, no persistent disk).

### 4.2 Data model (40 tables, `app/store.py:22-96`)
Users/sessions/groups; courses/enrollments/timetable/lessons/attendance/grades; materials/chunks/campus_kb; messages (tutor + campus); questions/quizzes/attempts/teacher_questions; service_categories/request_types/requests/request_events/request_messages/files/documents; notifications; news (+rsvp/saved/reads); academy tracks/modules/progress; tools/course_tools; syllabi; support_tickets/support_messages/feedback; audit; settings (JSON blobs). JSON-in-TEXT is used liberally (`data`, `fields`, `options`, `details`, `prefs`). No `REFERENCES` constraints are declared, so `PRAGMA foreign_keys=ON` (`app/store.py:129`) has no effect.

### 4.3 Request lifecycle details that matter for the findings
- Body is read lazily only when a handler calls `req.json()` (`app/web.py:47-59`); the dispatcher never drains unread bodies → **R-01**.
- Sessions are rows `(sid, user_id, created_at)` with no expiry (`app/store.py:28`) → **S-02**.
- Role gate is a tuple on the route decorator; object-level checks are hand-written per handler (`course_access`, `_req_for`, `_ticket_for`, `file_access`) — reviewed, generally correct (see §6.2 for the exceptions).

---

## 5. Code quality assessment

### 5.1 Strengths
- **Clear module boundaries** (`r_*` by domain, `common.py` helpers, `store.py` persistence, `engine.py`/`tutor.py` AI) and informative docstrings that explain *why* (e.g. office-hours jitter in seed, Windows code-page fix in `run.py`).
- **Consistent defensive patterns:** parameterised SQL (f-strings only build `IN (?,?,…)` placeholders or whitelisted column names — e.g. `app/r_learning.py:664-672`, `app/r_news.py:134-157`), `html.escape` in every server-rendered template, an escaping `html` tagged template on the client with explicit `raw()` opt-out (`static/js/core.js:9-16`), input length caps on every text field.
- **Testable seams:** `make_server(port=0, …)` enables the in-process API test; deterministic seed.
- **Accessibility and UX discipline** rarely seen in prototypes (`static/js/core.js:152-195` modal focus trap; `static/js/tour.js`; reduced-motion checks).
- **Self-made tooling** (`tools/i18n.py` with a JS tokenizer and AST-based Python scan) shows engineering range.

### 5.2 Weaknesses
- **Density over readability:** very long lines (routinely 180–260 chars), one-liner lambdas, large functions (`seed()` ≈ 340 lines, `app/store.py:384-725`; `validate()` 90 lines, `app/r_services.py:52-141`; `compose_tutor()` 93 lines). New engineers will be slow to onboard.
- **Hand-rolled infrastructure** (HTTP server, router, PDF text extractor, QR encoder, Markdown renderer, BM25, i18n toolchain) — see **T-01**. Each is competent, each is a maintenance and security liability compared with battle-tested libraries.
- **No automated quality gates:** no linter/formatter config, no type checking, no CI, no dependency manifest, no Dockerfile, no front-end tests (**T-02**).
- **Testing is a single procedural script** that resets the database and depends on seed specifics (`len(qs) == 10`, `unexcused == 6`), making it brittle to content changes and unusable as a regression suite in CI without refactoring.
- **Business constants in code** (course prerequisites, grading components, registry prefixes, lesson times, KPI targets) — **T-04**.
- **Mixed languages in identifiers/comments** (English code, Azerbaijani strings and commit messages) is fine for the team but all investor/developer documentation is Azerbaijani-only (**M-08**).

### 5.3 Metrics snapshot

| Area | Files | LOC | Notes |
|---|---|---|---|
| `app/` backend | 21 | 5,561 | largest: `store.py` 761, `r_learning.py` 744, `engine.py` 682 |
| `run.py`, `tests/`, `tools/` | 3 | 950 | `tools/i18n.py` 518, `tests/selftest.py` 375 |
| `static/js/` | 16 | 4,549 | largest: `core.js` 650, `teacher.js` 490, `services.js` 460 |
| `static/css/` | 8 | 1,296 | design tokens, dark theme, 22 media queries |
| `content/` | 24 | 1,839 | seed, KB, materials, academy, tools, news, guide, references, achievements, contacts |
| `i18n/` + generated catalogs | 37 | 13,872 | source + EN/RU chunks; `app/locales/ru.json` 439 KB |
| `aztu-ai-campus.zip` | 1 | — | 2.0 MB stale snapshot incl. DB, logs, `.dev/` |

---

## 6. Findings

### 6.1 Security

| ID | Sev. | Finding | Evidence |
|---|---|---|---|
| S-01 | **Critical** | Passwordless login for all five roles, including `admin`, reachable on the public Render URL; `admin` can wipe/re-seed the DB, change limits, and trigger LLM calls (spending API credit if configured). The UI even claims the server "only runs on this computer". | [`app/r_core.py:41-53`](../app/r_core.py#L41-L53), [`app/r_admin.py:132-137`](../app/r_admin.py#L132-L137), [`app/r_admin.py:100-124`](../app/r_admin.py#L100-L124), [`render.yaml:14`](../render.yaml#L14), [`static/js/main.js:65`](../static/js/main.js#L65), [`README.md:14`](../README.md#L14) |
| S-02 | High | Sessions never expire and are never pruned; the session token is also returned in the login JSON, stored in `sessionStorage`, and accepted via `X-Session` — which negates the `HttpOnly` cookie protection against token theft by script. | [`app/store.py:28`](../app/store.py#L28), [`app/common.py:25-47`](../app/common.py#L25-L47), [`app/r_core.py:16-24`](../app/r_core.py#L16-L24), [`static/js/core.js:30-31`](../static/js/core.js#L30-L31), [`static/js/main.js:71`](../static/js/main.js#L71) |
| S-03 | High | Missing hardening headers: no HSTS, no `frame-ancestors`/`X-Frame-Options` (clickjacking of the SPA), no `object-src`/`base-uri`; `Server` header leaks the Python version (`ZekaDemo/0.3 Python/3.13.18`). CSP is otherwise good. | [`app/web.py:108-113`](../app/web.py#L108-L113), [`app/web.py:121`](../app/web.py#L121); probe §9.2 |
| S-04 | Medium | Untrusted uploads are parsed by hand-written code with no decompression limits: DOCX/PPTX via `zipfile` (zip-bomb), PDF FlateDecode via `zlib.decompress` (unbounded), XML via stdlib `xml.etree` (no `defusedxml`). The DOCX sniff accepts *any* ZIP (`PK\x03\x04`). Files up to 10 MB (30 MB request body) are accepted from any logged-in role. | [`app/engine.py:228-275`](../app/engine.py#L228-L275), [`app/pdftext.py:17-27`](../app/pdftext.py#L17-L27), [`app/pdftext.py:218-235`](../app/pdftext.py#L218-L235), [`app/store.py:183-215`](../app/store.py#L183-L215), [`app/r_core.py:266-289`](../app/r_core.py#L266-L289), [`app/web.py:17`](../app/web.py#L17) |
| S-05 | Medium | No rate limiting or abuse controls on login, uploads, search, tickets or feedback (only a daily chat quota for students; teachers are unlimited); `ThreadingHTTPServer` creates an unbounded thread per connection (slow-loris / thread exhaustion); `/api/consent` writes the raw request JSON (up to 30 MB) into the audit table. | [`app/web.py:193-195`](../app/web.py#L193-L195), [`app/common.py:115-126`](../app/common.py#L115-L126), [`app/r_core.py:65`](../app/r_core.py#L65) |
| S-06 | Medium | CSRF defence rests on `SameSite=Lax` plus a JSON `Content-Type` check; the state-changing `GET /demo/login` allows login-CSRF and is linkable from anywhere. | [`app/web.py:135-138`](../app/web.py#L135-L138), [`app/r_core.py:47-53`](../app/r_core.py#L47-L53), [`app/common.py:29-34`](../app/common.py#L29-L34) |
| S-07 | Low | Session IDs stored in plaintext (hash at rest); one-time document keys live in process memory (fine single-process, breaks under multiple workers). | [`app/store.py:28`](../app/store.py#L28), [`app/common.py:20-22`](../app/common.py#L20-L22), [`app/common.py:60-75`](../app/common.py#L60-L75) |
| S-08 | Low | Access logging is disabled; the only log is an unbounded `logs/errors.log` with full tracebacks; no log rotation, no forensics trail beyond the `audit` table. | [`app/web.py:123-124`](../app/web.py#L123-L124), [`run.py:39-43`](../run.py#L39-L43) |
| S-09 | Low | The `external` consent flag (send masked questions to an external AI service) is recorded in the audit log only and never checked before calling the LLM. | [`app/r_core.py:62-66`](../app/r_core.py#L62-L66), [`app/r_learning.py:324-328`](../app/r_learning.py#L324-L328) |
| S-10 | Low | CSV formula injection: the feedback export writes user comments verbatim, so a comment starting with `=`, `+`, `-` or `@` executes as a formula when leadership opens the file in Excel. | [`static/js/support.js:269-273`](../static/js/support.js#L269-L273) |

*Reviewed and found sound:* SQL parameterisation; HTML escaping (server `html.escape`, client `esc()`/`html` tag, Markdown renderer escapes before formatting, `highlight()` only wraps text nodes); static path traversal check (`app/web.py:161-164`); object-level authorisation on requests, files, documents, tickets, materials, quizzes, questions (`app/common.py:99-108`, `app/r_services.py:215-219`, `app/r_core.py:239-246`, `app/r_support.py:34-38`); `verify` page shows initials only; one-time links expire in 5 minutes and are single-use (selftest confirms).

### 6.2 Reliability and correctness

| ID | Sev. | Finding | Evidence |
|---|---|---|---|
| R-01 | **High** | **HTTP keep-alive desync (confirmed).** The body is read only when a handler calls `req.json()`. The SPA always sends a `{}` body on POST. For the 13 POST routes that never read it (`logout`, `tutor/clear`, `campus/clear`, `news/rsvp`, `news/save`, `requests/cancel`, `documents/link`, `files/link`, `syllabus/link`, `tickets/reopen`, `quizzes/start`, `admin/test-llm`, `admin/reset`) and for every error raised before the handler reads the body (401/403/404/405/415), the unread bytes are parsed as the start of the *next* request on the same connection → `501 Unsupported method ('{}GET')`. Users see intermittent "error" toasts depending on browser connection reuse; behind a connection-pooling reverse proxy the failed request can belong to a different user. The self-test cannot see it because `urllib` sends `Connection: close`. | [`app/web.py:47-59`](../app/web.py#L47-L59), [`app/web.py:126-159`](../app/web.py#L126-L159), [`static/js/core.js:32,47`](../static/js/core.js#L32), [`tests/selftest.py:100-113`](../tests/selftest.py#L100-L113); probe §9.2 |
| R-02 | **High** | Destructive persistence strategy: a `SCHEMA_VERSION` mismatch **deletes the database**; `reseed()` truncates every table; Render free tier has no disk, so the DB is recreated on each restart. There are no migrations and no backups. Pilot data would not survive a single schema change or deploy. | [`app/store.py:728-751`](../app/store.py#L728-L751), [`app/store.py:754-761`](../app/store.py#L754-L761), [`render.yaml:26-28`](../render.yaml#L26-L28) |
| R-03 | **High** | Graded assessment integrity: (a) the time limit is enforced only in the browser — the server accepted a submission for an attempt started in 2020 (confirmed); (b) the attempt limit counts only *finished* attempts, so a student can open several attempts, submit one, and (c) read the full answer key and explanations that every submission returns regardless of quiz kind, then submit the remaining open attempts with correct answers. "Graded" quizzes are therefore not trustworthy. | [`app/r_learning.py:446-469`](../app/r_learning.py#L446-L469), [`app/r_learning.py:423-436`](../app/r_learning.py#L423-L436), [`static/js/student.js:227-253`](../static/js/student.js#L227-L253) |
| R-04 | Medium | All timestamps are naive local time; the deploy target runs in UTC while business logic assumes Baku (office hours, "today's lessons", semester start, `.ics` `TZID=Asia/Baku`). | [`app/store.py:99-121`](../app/store.py#L99-L121), [`app/r_learning.py:234-238`](../app/r_learning.py#L234-L238), [`app/r_news.py:117-121`](../app/r_news.py#L117-L121) |
| R-05 | Medium | Search indexes (BM25) and one-time keys are process-local and rebuilt on start; search is an O(N) pure-Python scan per query. Blocks horizontal scaling and degrades with corpus size. | [`app/engine.py:118-169`](../app/engine.py#L118-L169), [`app/store.py:268-281`](../app/store.py#L268-L281) |
| R-06 | Medium | Dashboards load entire tables into Python per request and list endpoints have no pagination (`/api/requests`, `/api/news/manage`, `/api/support/tickets`, audit limited to 200). SQLite single-writer with a per-request connection. | [`app/r_services.py:421-437`](../app/r_services.py#L421-L437), [`app/r_admin.py:17-78`](../app/r_admin.py#L17-L78), [`app/r_support.py:247-270`](../app/r_support.py#L247-L270), [`app/r_services.py:227-249`](../app/r_services.py#L227-L249) |
| R-07 | Medium | Static assets are served `Cache-Control: no-cache` **without** `ETag`/`Last-Modified`, and JS/CSS are unminified and unbundled → ~425 KB JS + ~116 KB CSS (+118–168 KB locale JSON for EN/RU) re-downloaded on every page load. | [`app/web.py:161-169`](../app/web.py#L161-L169), [`static/index.html:12-19`](../static/index.html#L12-L19), [`static/js/i18n.js:29`](../static/js/i18n.js#L29) |
| R-08 | Medium | LLM calls are synchronous in the request thread (up to 40 s), no retry/backoff, no streaming, no token/cost accounting; LLM citations are parsed with a single-digit regex. | [`app/engine.py:323-349`](../app/engine.py#L323-L349), [`app/tutor.py:141-157`](../app/tutor.py#L141-L157) |
| R-09 | Low | Edge-case bugs: `/syllabus/{cid}` for admin/leader with an unknown id dereferences `None` (500); `revoke` and `news_delete` silently succeed on unknown ids; a saved syllabus larger than 200 kB is truncated mid-JSON and silently lost on the next read. | [`app/r_academy.py:256-261`](../app/r_academy.py#L256-L261), [`app/r_academy.py:244-245`](../app/r_academy.py#L244-L245), [`app/r_services.py:449-456`](../app/r_services.py#L449-L456), [`app/r_news.py:193-200`](../app/r_news.py#L193-L200) |
| R-10 | Low | "No-source gap" analytics depend on the exact JSON spacing of a `LIKE '%"no_source": true%'` match. | [`app/r_learning.py:498-500`](../app/r_learning.py#L498-L500) |
| R-11 | Low | PII masking false positives: the FİN regex masks course codes (`ELM2105` → `[FİN]`), degrading tutor questions (confirmed). | [`app/engine.py:279-293`](../app/engine.py#L279-L293) |
| R-12 | Low | Academy modules are not sequential server-side, and a failed module quiz returns the correct answers, so certificates can be earned by retrying. | [`app/r_academy.py:92-117`](../app/r_academy.py#L92-L117) |

### 6.3 Technical debt and architecture

| ID | Sev. | Finding | Evidence |
|---|---|---|---|
| T-01 | **High** | Everything is hand-rolled on the standard library: HTTP server/router, PDF text extraction, QR encoding, Markdown rendering, BM25, i18n toolchain with its own JS tokenizer. Excellent for a zero-install demo; for production it means owning the security and edge cases of six parsers and a web server. | [`app/web.py`](../app/web.py), [`app/pdftext.py`](../app/pdftext.py), [`app/qr.py`](../app/qr.py), [`app/engine.py:118-169`](../app/engine.py#L118-L169), [`static/js/core.js:347-379`](../static/js/core.js#L347-L379), [`tools/i18n.py`](../tools/i18n.py) |
| T-02 | **High** | No `requirements.txt`/`pyproject.toml`, no Dockerfile, no CI workflow, no lint/format/type config, no pre-commit; the only test is a manual script that resets the DB; zero front-end tests. The `.dev/tools` referenced by the README exist only inside the zip. | repo root; [`tests/selftest.py`](../tests/selftest.py); [`README.md:57`](../README.md#L57) |
| T-03 | Medium | i18n keyed by Azerbaijani source text with response-time translation of *every* JSON value: copy edits silently break translations; coincidental collisions required special-casing (`"Giriş"` = both "Introduction" and "Log in"); `SKIP_KEYS` heuristics decide what is "user content"; question-generation and document templates are Azerbaijani-only f-strings (47 lint findings). | [`app/i18n.py:117-141`](../app/i18n.py#L117-L141), [`app/i18n.py:168-172`](../app/i18n.py#L168-L172), [`app/engine.py:496-668`](../app/engine.py#L496-L668) |
| T-04 | Medium | Institution-specific business rules hard-coded in source: course prerequisites, document wording per destination, grading components, registry prefix `AzTU-`, lesson time slots, KPI targets. A second university requires code changes. | [`app/r_academy.py:17-18`](../app/r_academy.py#L17-L18), [`app/docs.py:14-20`](../app/docs.py#L14-L20), [`app/r_learning.py:185`](../app/r_learning.py#L185), [`app/store.py:287-291`](../app/store.py#L287-L291), [`static/js/student.js:312`](../static/js/student.js#L312) |
| T-05 | Medium | Schema without constraints (no `REFERENCES`, few `NOT NULL`), JSON blobs in TEXT columns validated only on read (`J()` swallows parse errors); settings are JSON in a key/value table. | [`app/store.py:22-96`](../app/store.py#L22-L96), [`app/store.py:142-148`](../app/store.py#L142-L148) |
| T-06 | Medium | Readability debt: 180–260-char lines, 300-line functions, nested one-liners; onboarding cost for hires. | [`app/store.py:384-725`](../app/store.py#L384-L725), [`app/r_services.py:52-141`](../app/r_services.py#L52-L141), [`static/js/services.js:52-220`](../static/js/services.js#L52-L220) |
| T-07 | Low | Dead/vestigial code: `app/api.py` shim, unused `panelHost`, debug exports (`_tours`, `_roleSteps`, `_debugActive`), one-line `print.js`. | [`app/api.py`](../app/api.py), [`static/js/chat.js:184-196`](../static/js/chat.js#L184-L196), [`static/js/main.js:272`](../static/js/main.js#L272), [`static/js/guide.js:78`](../static/js/guide.js#L78) |
| T-08 | Low | Front-end module-level caches (`SVC`, `META`, `A`) are never invalidated on role switch; `META` carries the role-dependent `desk` flag, so the support UI shows the previous role's controls until reload; global mutable state object `S`. | [`static/js/services.js:8-9`](../static/js/services.js#L8-L9), [`static/js/support.js:5-6`](../static/js/support.js#L5-L6), [`static/js/achievements.js:5-6`](../static/js/achievements.js#L5-L6), [`static/js/shell.js:215-221`](../static/js/shell.js#L215-L221) |

### 6.4 Missing components (gap to a product)

| ID | Sev. | Missing | Evidence of absence |
|---|---|---|---|
| M-01 | **Critical** | **Identity & access management**: no credentials, SSO, MFA, password reset, account lifecycle, user provisioning. Everything hinges on the demo-role login. | [`static/js/main.js:62`](../static/js/main.js#L62) (SSO button disabled), [`app/r_support.py:286-287`](../app/r_support.py#L286-L287) ("planned") |
| M-02 | **High** | Durable storage: production database (Postgres), object storage for uploads, backups/restore, migrations. | [`render.yaml:26-28`](../render.yaml#L26-L28), [`app/store.py:124-130`](../app/store.py#L124-L130) |
| M-03 | **High** | Observability: structured request logs, metrics, error tracking, uptime/alerting; complete audit (settings changes and reset are logged, logout/login failures/role switches are not). | [`app/web.py:123-124`](../app/web.py#L123-L124), [`app/store.py:151-153`](../app/store.py#L151-L153) |
| M-04 | **High** | Integrations that make the data real: student registry/LMS (courses, enrollments, attendance, grades are all seeded), e-mail/SMS notifications (in-app only), qualified e-signature (ASAN İmza/SİMA) for legally valid documents. | [`app/store.py:384-725`](../app/store.py#L384-L725), [`app/store.py:170-174`](../app/store.py#L170-L174), [`app/docs.py:48-54`](../app/docs.py#L48-L54) |
| M-05 | **High** | Production AI layer: evaluation set and regression harness for tutor quality, prompt-injection and jailbreak defences (only a regex), retrieval beyond BM25 over Markdown chunks, PDF ingestion of lecture materials, cost/latency controls, async execution. | [`app/tutor.py:14-16`](../app/tutor.py#L14-L16), [`app/tutor.py:141-157`](../app/tutor.py#L141-L157), [`app/engine.py:275`](../app/engine.py#L275) |
| M-06 | Medium | Data-protection controls promised in the UI but not implemented: consent not enforced on the API (confirmed), consent revocation is a stub, `retention_days` is stored but never applied, no export/erasure endpoints, no DPA/privacy notice artefacts. | [`static/js/main.js:87-107`](../static/js/main.js#L87-L107), [`static/js/main.js:201-203`](../static/js/main.js#L201-L203), [`app/r_admin.py:109-111`](../app/r_admin.py#L109-L111), [`app/r_learning.py:303-336`](../app/r_learning.py#L303-L336) |
| M-07 | Medium | Administration: no UI/API to manage users, courses, enrollments, request types, KB articles or guides — all live in JSON files loaded at seed time. | [`content/seed.json`](../content/seed.json), [`app/store.py:380-382`](../app/store.py#L380-L382) |
| M-08 | Medium | Documentation for stakeholders: no architecture/API docs (OpenAPI), no LICENSE, CONTRIBUTING, CHANGELOG, security policy or English README. | repo root |
| M-09 | Low | Automated accessibility/performance/E2E checks and a browser support matrix; the `.dev/tools` harness is not versioned in the repo. | zip contents only |

### 6.5 Product and claims integrity (important for an investor)

| ID | Sev. | Finding | Evidence |
|---|---|---|---|
| P-01 | **High** | The leadership dashboard presents **hard-coded** series and values alongside computed ones: weekly-active students/teachers (`[28…64]`, `[35…76]`), request turnaround history, "Test preparation time −41 %", "Student satisfaction 4.4/5", "Learning gain +0.28 SD vs control group", "AI cost per student $0.42", and a fixed "good" insight "100 % of paper applications moved online". The page carries a "Pilot scenario" banner and an info tip, but the numbers look like evidence. These must never appear in a data room or customer demo without an explicit "illustrative" stamp on each value. | [`app/r_admin.py:47-60`](../app/r_admin.py#L47-L60), [`app/r_admin.py:68`](../app/r_admin.py#L68), [`app/r_admin.py:74`](../app/r_admin.py#L74), [`static/js/staff.js:33-41`](../static/js/staff.js#L33-L41) |
| P-02 | Medium | "QR-verified official documents" is a UX prototype: transcript grades are generated deterministically from the user id; integrity is a SHA-256 stored in the same database; there is no registry integration or qualified signature. Labelled DEMO, but the gap to legal validity is the core risk of the e-services pillar. | [`app/store.py:306-317`](../app/store.py#L306-L317), [`app/store.py:287-303`](../app/store.py#L287-L303), [`app/docs.py:48-54`](../app/docs.py#L48-L54) |
| P-03 | Medium | "AI tutor" is, by default, retrieval + templated phrasing; the honest badge ("Demo AI mühərriki (oflayn)") must be preserved in any pitch, and the LLM path needs evidence (eval results) before it is marketed. | [`app/tutor.py:24-116`](../app/tutor.py#L24-L116), [`app/engine.py:316-320`](../app/engine.py#L316-L320) |

### 6.6 Repository hygiene and process

| ID | Sev. | Finding | Evidence |
|---|---|---|---|
| H-01 | Medium | A 2.0 MB `aztu-ai-campus.zip` was uploaded through the GitHub web UI into `main`. It contains a *stale* copy of the codebase (missing `refs.py`, `references.json`, `render.yaml`), a SQLite snapshot with three uploaded files, benign server logs, `__pycache__`, and internal dev notes (`.dev/CONTRACT.md`, `.dev/plan-v03.md`) including a developer's Windows home path. Remove it and purge it from history. | [`aztu-ai-campus.zip`](../aztu-ai-campus.zip); commit `46a4e87` "Add files via upload" |
| H-02 | Medium | Bus factor of one and code provenance: 9 commits from one GitHub account over 8 days; no PRs/reviews or branch protection. The dev notes inside the zip show v0.3 (trilingual UI, page guides, support desk, achievements, 3,473 translated strings) was planned and shipped on 2026-10-02 in about four hours by parallel AI coding agents ("subagents") under a written contract. Fast, but it means much of the code has had no human line-by-line review, and IP/licensing of AI-generated code should be covered in diligence. | `git log`; `aztu-ai-campus.zip` → `.dev/plan-v03.md`, `.dev/CONTRACT.md` |
| H-03 | Low | Generated catalogs (`app/locales/*.json`, `static/locales/*.json`) are committed next to their sources with no CI check that they are in sync; `i18n/source/*` is also committed. | [`tools/i18n.py:477-497`](../tools/i18n.py#L477-L497) |
| H-04 | Low | README references dev tools (`.dev/tools/*`) that are not in the repository; Windows-only launch scripts; no cross-platform `Makefile`/task runner. | [`README.md:57`](../README.md#L57), [`start_demo.bat`](../start_demo.bat), [`scripts/`](../scripts) |
| H-05 | Low | No open-source or proprietary LICENSE file; third-party brand (AzTU name, logo files) used without a visible permission artefact; Inter font (OFL) is fine. | [`static/img/brand/`](../static/img/brand), [`static/js/shell.js:64-65`](../static/js/shell.js#L64-L65) |

### 6.7 Severity summary

| Severity | Count | IDs |
|---|---|---|
| **Critical** | 2 | S-01, M-01 |
| **High** | 12 | S-02, S-03, R-01, R-02, R-03, T-01, T-02, M-02, M-03, M-04, M-05, P-01 |
| **Medium** | 19 | S-04, S-05, S-06, R-04, R-05, R-06, R-07, R-08, T-03, T-04, T-05, T-06, M-06, M-07, M-08, P-02, P-03, H-01, H-02 |
| **Low** | 14 | S-07, S-08, S-09, S-10, R-09, R-10, R-11, R-12, T-07, T-08, M-09, H-03, H-04, H-05 |
| **Total** | **47** | |

---

## 7. Investment-relevant assessment

**What is real today**
- A working, coherent, trilingual product prototype that a dean, teacher and student can click through end-to-end in 12 minutes, running on a $0 deployment.
- Deep understanding of the Azerbaijani higher-education workflow (request types, SLAs, document wording per destination, grading components, academic calendar) — this is domain IP that is hard to copy quickly.
- Real, sourced content (18 verified achievements, official contacts, 93 checked external references) and a translation pipeline that works.

**What is not real yet**
- Users, data, identity, persistence, legal validity of documents, measured outcomes, an AI layer that has been evaluated, and any operational practice (CI, monitoring, backups, incident response).

**Team and execution**
- Velocity is exceptional: the internal plan in the zip shows the v0.3 release was orchestrated in one afternoon with parallel AI coding agents, and the result is coherent. That is a real skill (product judgement + agent orchestration), but it is not the same as production engineering. Risks: single contributor, no review culture, no tests beyond one script, largely AI-written code. The hiring plan should prioritise a second senior engineer with production/security experience before the pilot.

**Diligence items outside the code (must be answered before term sheet)**
1. Status of the AzTU relationship: demo shown? LOI/MoU? Who sponsors SSO/registry access? Written permission to use the AzTU name and logo?
2. Ownership of code and content (sole author; any employer IP claims; AI-generated content/code licensing posture).
3. Regulatory path for e-documents (ASAN İmza / SİMA integration, Ministry of Science and Education requirements, personal-data law compliance in Azerbaijan).
4. LLM provider strategy and data residency (student questions leaving the country vs. a local/EU-hosted model).
5. Unit economics: real LLM cost per active student (the `$0.42` in the dashboard is a placeholder).

**Effort to investor-ready MVP (engineering only):** ~26–32 engineer-weeks over 90 days with 2–3 engineers (details, sequencing and exit criteria in [`docs/ROADMAP.md`](ROADMAP.md)).

---

## 8. Recommendations in priority order (summary)

1. **Week 1 hot-fixes:** gate demo login behind an environment flag and a shared passcode (S-01); drain request bodies / read eagerly in the dispatcher (R-01); enforce quiz deadlines, attempt limits and answer-key visibility server-side (R-03); add session expiry and drop the `X-Session` path or scope it (S-02); add HSTS, `frame-ancestors 'self'`, remove `Server` version (S-03); remove the zip and purge history (H-01); stamp every hard-coded KPI as illustrative or remove (P-01).
2. **Weeks 2–4 foundations:** `pyproject.toml`, Dockerfile, GitHub Actions (lint + selftest), pytest conversion of the selftest, Postgres + Alembic migrations, structured logging; wire a real LLM with a 50-question Azerbaijani evaluation set.
3. **Days 30–60 pilot readiness:** SSO (or interim e-mail+password+MFA for staff), registry/LMS import (CSV first), PDF ingestion, email notifications, consent/retention enforcement, object storage, load test, light pen test.
4. **Days 60–90 pilot & evidence:** launch one cohort, replace all dashboard literals with event-derived metrics, produce security/architecture documentation and the data room.

---

## 9. Appendix

### 9.1 Self-test run (2026-11-05, Python 3.13.18)
`python tests/selftest.py` → `RESULT: ALL PASSED` (136 checks: QR Reed-Solomon vectors, stemming, PII masking, transliteration, search, tutor modes and guardrails, quiz generation and grading for all 6 courses, full API smoke across the five roles, i18n behaviour, support desk, feedback, achievements, contacts, file preview, document issuance and one-time links).

### 9.2 Live probe results (in-process server on a random port)

| Probe | Result | Finding |
|---|---|---|
| `POST /api/tutor/1/clear` with body `{}` then `GET /api/badges` on the same connection | second request → **501** `Unsupported method` | R-01 |
| `POST /api/consent` with wrong content type (415) then `GET` on the same connection | second request → **501** | R-01 |
| Start quiz, back-date `started_at` to 2020, submit | **200**, graded (0 %) | R-03 |
| `GET /demo/login?role=admin` (no credentials) | **302** + `Set-Cookie: zeka_sid=…` | S-01 |
| Student with `consent_at = NULL` calls `POST /api/campus/ask` | **200** | M-06 |
| `mask_pii("ELM2105 haqqında")` | `('[FİN] haqqında', ['FİN'])` | R-11 |
| Response headers on `/` | `Server: ZekaDemo/0.3 Python/3.13.18`; CSP present; no HSTS, no frame-ancestors, no ETag; `Cache-Control: no-cache` | S-03, R-07 |

### 9.3 i18n tooling
`python tools/i18n.py stats` → EN and RU: ui 1584/1584, server 417/417, content 1488/1488. `lint` → 47 findings: `app/engine.py` question templates (31), `app/docs.py` document templates (9), `app/r_academy.py` syllabus text (4), `static/js/student.js` tutor query strings (3). Generated course content is intentionally Azerbaijani-only, but EN/RU users get Azerbaijani questions and syllabi.

### 9.4 Route inventory
107 routes (counted from `@R(...)` decorators): 57 GET, 40 POST, 7 PUT, 3 DELETE across `app/r_core.py`, `app/r_learning.py`, `app/r_services.py`, `app/r_news.py`, `app/r_academy.py`, `app/r_admin.py`, `app/r_support.py`. Unauthenticated: `/api/bootstrap`, `/api/auth/demo`, `/demo/login`, `/verify/{code}`, `/api/achievements`, `/api/contact`.

### 9.5 Git history
```
a59ef1f 2026-10-13 Render pulsuz plan: sabit disk silindi (baza restartda avtomatik seed olunur)
418d8ce 2026-10-13 develop budağı main-ə birləşdirildi: Zəka AzTU rəqəmsal kampus portalı + Render yerləşdirmə
406e2a6 2026-10-13 Render.com üçün yerləşdirmə: render.yaml, konfiqurasiya olunan host və PORT/HOST/PUBLIC_URL
412a2c6 2026-10-12 Çıxış fayla yönləndiriləndə serverin açılışda çökməsi düzəldildi
46a4e87 2026-10-12 Add files via upload            ← aztu-ai-campus.zip (2 MB)
a6cb0e2 2026-10-12 Yoxlanılmış mənbələr, peşəkar AZ mətnlər və UI düzəlişləri
6ac1ae9 2026-10-09 Dil dəyişəndə portalın donması düzəldildi
929ba9d 2026-10-09 Serverə yerləşdirmə: --public-url və HTTPS-də Secure kuki
bb3a94a 2026-10-06 Zəka — AzTU rəqəmsal kampus demosu v0.3
```
