# Zəka — 30/60/90-Day Roadmap to an Investor-Ready MVP

| | |
|---|---|
| **Baseline** | `main` @ `a59ef1f`, assessed in [`docs/AUDIT.md`](AUDIT.md) (47 findings: 2 Critical, 12 High, 19 Medium, 14 Low) |
| **Start date** | Day 1 = the Monday after funding/approval of this plan |
| **Team assumed** | 2.5 engineers (founder-engineer, 1 senior backend/security hire, 0.5 AI engineer) + part-time designer/QA + founder/CEO on the university relationship |
| **Engineering effort** | ~36 engineer-weeks planned against ~32 available (2.5 engineers × 13 weeks); the gap is managed by cutting from the bottom of each phase (§7) |

Finding IDs in brackets (e.g. **[S-01]**) refer to [`docs/AUDIT.md`](AUDIT.md).

---

## 1. What "investor-ready MVP" means on Day 90

An investor (or a second university) can verify each of the following without taking our word for it:

1. **Real users, real data.** One pilot cohort at AzTU uses Zəka with university accounts: one faculty, the 6 courses already modelled, about 120 students, about 10 teachers, one dean's office. Courses, enrollments and timetable come from the university, not from `seed.json`.
2. **Every number is measured.** The leadership dashboard and the pitch deck show only values derived from logged events, with a visible methodology note. No literal in code produces a KPI **[P-01]**.
3. **Security baseline is evidenced.** University SSO, no passwordless roles in production, OWASP ASVS Level 1 self-assessment, an external light penetration test with all Critical/High findings closed **[S-01…S-06, M-01]**.
4. **Data survives.** Managed Postgres with migrations, daily backups and a tested restore; uploads in object storage **[R-02, M-02]**.
5. **The AI is evaluated.** A versioned Azerbaijani evaluation set with published scores for groundedness, citation accuracy and Socratic compliance; the production tutor runs on the model that wins it; cost per active student is measured **[M-05, P-03]**.
6. **The team can ship safely.** CI on every PR, automated tests, observability, runbooks, and at least two engineers who can deploy **[T-02, M-03, H-02]**.
7. **A data room exists.** Architecture overview, security overview, privacy/DPIA, audit-remediation status, pilot report, 12-month roadmap, unit economics.

**Explicitly out of scope for the 90 days:** a front-end rewrite (the vanilla SPA is good enough), native mobile apps, more than one paying university, training our own model, all 13 e-services in production (the pilot runs 3, see §4.3).

---

## 2. Key decisions to take in week 1

| # | Decision | Recommendation | Why |
|---|---|---|---|
| D1 | Web framework | Move the HTTP layer to **Starlette/FastAPI on uvicorn** behind a managed TLS proxy. Keep the existing handler signature through a thin adapter (`req.db`, `req.user`, `req.json()`, `req.params`, `req.query`, `req.lang`) so the 107 handlers move with minimal edits. | Removes the hand-rolled server and its protocol bug **[R-01, T-01, S-05]**; gives OpenAPI for free **[M-08]**; no big-bang rewrite. |
| D2 | Database | **Postgres** (managed) + **Alembic** migrations; uploads to **S3-compatible object storage**. | **[R-02, M-02, T-05]**. Porting effort is moderate: SQLite-specific SQL (`SUM(x='y')`, `INSERT OR REPLACE/IGNORE`, `PRAGMA`, `?` placeholders) must be rewritten. |
| D3 | Hosting and data residency | EU region (Frankfurt) for the pilot unless AzTU's legal review requires in-country hosting. Decide together with D4 in the first 2 weeks. | Student data protection; must be agreed with the university before real data flows. |
| D4 | LLM provider | Run a bake-off on the Azerbaijani eval set (frontier API models vs. an open-weight model hosted in-region); pick on quality, cost and residency. Keep the offline engine as fallback and for zero-cost demos. | **[M-05, P-03, R-08]**. Today the "AI" is BM25 + templates by default. |
| D5 | Keep a zero-install demo | Keep `run.py` + SQLite as a **demo mode** (sales demos, offline use) behind a build flag; production uses D1–D2. | Preserves the current strength without exposing it in production **[S-01]**. |
| D6 | Pilot scope of e-services | Pilot only **enrolment certificate, absence excuse with medical note, and free-form application**; others stay "coming soon". | Focuses legal/process work; these three are the most used in the seed data and the demo script. |

---

## 3. Day 0–7: stop the bleeding (before anyone else sees the public URL)

These are small, high-leverage fixes. All change source code, so they are scheduled here and not done in the audit session.

| Priority | Item | Findings | Effort |
|---|---|---|---|
| P0 | Disable `/api/auth/demo` and `/demo/login` unless `ZEKA_DEMO=1`; protect the demo with a shared passcode; disable `/api/admin/reset` outside demo mode. Take the Render deployment private until done. | S-01, S-06 | 0.5 d |
| P0 | In the dispatcher, always read and discard `Content-Length` bytes before responding (or set `close_connection` on any error). Add a keep-alive regression test using `http.client`. | R-01 | 0.5 d |
| P0 | Enforce quiz deadline (`started_at + time_limit + grace`) and attempt limits counting *started* attempts; return the answer key only for practice quizzes or after the quiz closes. | R-03 | 1 d |
| P0 | Mark every hard-coded KPI in `/api/analytics` as `illustrative: true` and render an "Illustrative" badge on each; remove the "100 % paper applications" insight. | P-01 | 0.5 d |
| P1 | Session expiry (idle 8 h, absolute 7 days) and pruning; stop returning the token in JSON; keep the cookie as the only credential. | S-02, S-07 | 1 d |
| P1 | Add `Strict-Transport-Security`, `frame-ancestors 'self'`, `object-src 'none'`, `base-uri 'self'`; drop the version from `Server`. | S-03 | 0.25 d |
| P1 | Remove `aztu-ai-campus.zip` from the repo and purge it from history; enable branch protection on `main`. | H-01, H-02 | 0.25 d |
| P2 | Neutralise CSV formula injection in the feedback export; tighten the FİN regex so course codes are not masked. | S-10, R-11 | 0.25 d |

**Exit (Day 7):** public URL no longer allows passwordless admin; keep-alive and quiz-integrity tests pass; dashboard numbers labelled; zip gone.

---

## 4. Days 1–30 — Foundations and trust

**Goal:** a production-shaped platform that can safely hold real data, plus a signed agreement to get that data.

### 4.1 Engineering platform
- `pyproject.toml` with pinned dependencies; `ruff` + `black` + `mypy` (gradual); pre-commit hooks **[T-02]**.
- Dockerfile and `docker-compose` (app + Postgres + MinIO) for one-command local setup on any OS **[H-04]**.
- GitHub Actions: lint, type check, unit + API tests, i18n catalog sync check, container build on every PR **[T-02, H-03]**.
- Convert `tests/selftest.py` into a pytest suite with fixtures and a factory-based test dataset, so tests stop depending on seed counts. Target 70 % line coverage on `app/` by Day 30.
- Move the `.dev/tools` DOM/screenshot harness into the repo as Playwright smoke tests for the 5 roles × 3 languages × desktop/mobile **[M-09]**.
- i18n: CI check that generated catalogs match sources; move generated-content templates (practice questions, syllabus, document text) into the catalog so EN/RU users stop receiving Azerbaijani; plan stable message IDs for UI strings **[T-03]**.

### 4.2 Data and persistence
- Framework migration per D1 behind the adapter; one route module at a time, each with its tests green.
- Postgres schema with foreign keys, `NOT NULL`, check constraints and `timestamptz`; JSON columns become `jsonb` with schema validation on write **[T-05, R-04]**.
- Alembic migrations replace "delete the DB on version mismatch"; the seed becomes a `demo` fixture, never run in production **[R-02]**.
- Object storage for uploads with server-side encryption; daily Postgres backups with a restore drill documented and performed once **[M-02]**.

### 4.3 Security and privacy
- Interim authentication for staff (e-mail + password + TOTP) so the dean's office and teachers can start onboarding before SSO lands; students wait for SSO **[M-01]**.
- Rate limiting per IP and per user on login, uploads, search, AI and ticket endpoints; request size caps per route **[S-05]**.
- Upload hardening: decompression-size limits for DOCX/PPTX/PDF, `defusedxml`, stricter DOCX sniffing (check `[Content_Types].xml`), parse in a worker with a timeout **[S-04]**.
- Enforce consent on the API (no tutor/campus calls without it); honour the "external AI" opt-in; implement retention deletion as a scheduled job; data export and erasure endpoints **[M-06, S-09]**.
- Structured JSON access logs, error tracking, uptime checks, log rotation; audit login, logout, failures and role/permission changes **[S-08, M-03]**.

### 4.4 AI quality
- Build the **Azerbaijani evaluation set**: 150 tutor questions across the 6 courses with gold citations (answerable, unanswerable, problem-solving, "give me the answer" attempts, prompt-injection attempts, EN/RU phrasing) and 50 campus-rules questions. Version it in the repo.
- Eval harness that scores groundedness, citation correctness, Socratic compliance and refusal-when-unsupported; run it in CI on prompt or model changes.
- Make LLM calls async with timeouts, retries and streaming; log tokens and cost per call; per-tenant monthly budget cap **[R-08]**.
- Prompt-injection defences: material and history passed as delimited data, output citation validation, guardrail classifier instead of one regex **[M-05]**.
- Run the D4 bake-off and choose the production model.

### 4.5 Product, honesty and business
- Replace dashboard literals with an `events` table and computed metrics: WAU, questions per active student, cited-answer rate, helpfulness rate, request turnaround, SLA compliance **[P-01]**.
- Sign an **MoU / pilot agreement with AzTU** covering pilot scope, data-sharing and processing terms, SSO and registry access, written permission to use the AzTU name and logo, and success criteria **[H-05]**.
- Start the legal path for e-documents: confirm with the university and the Ministry what makes a certificate valid; scope ASAN İmza / SİMA integration **[P-02, M-04]**.
- Write an English README, LICENSE (proprietary), SECURITY.md and CONTRIBUTING.md **[M-08]**.

**Day 30 exit criteria (go/no-go for pilot build):**
- [ ] All Day 0–7 items done; no Critical findings open.
- [ ] App runs on Postgres in staging via CI/CD; restore drill done.
- [ ] Interim staff login with TOTP live in staging; consent enforced on the API.
- [ ] Eval set v1 committed; baseline scores published for the offline engine and two LLM candidates.
- [ ] Signed AzTU pilot agreement **or** a dated decision to pivot the pilot to staff-only workflows.

---

## 5. Days 31–60 — Pilot readiness

**Goal:** everything a real cohort needs on day one, nothing more.

### 5.1 Identity and data integration
- University SSO (OIDC or SAML against `sso.aztu.edu.az`), just-in-time provisioning, role mapping from the registry, account deactivation **[M-01]**.
- Registry/LMS import: start with signed CSV exports (students, groups, courses, enrollments, timetable), then an API if available; idempotent nightly sync with a reconciliation report **[M-04]**.
- Teacher material ingestion for PDF (the most common format), with page-level citations **[M-05]**.

### 5.2 Workflows and administration
- Admin console for users, courses, enrollments, request types (form schema editor), knowledge-base articles and guides; content no longer lives only in seed JSON **[M-07]**.
- Move institution rules to per-tenant configuration: registry prefixes, grading components, lesson slots, document templates, prerequisites **[T-04]**.
- E-mail notifications (and SMS for urgent cases) with user preferences, in addition to in-app notifications **[M-04]**.
- Teacher-side analytics on real data: topic heatmap and "questions the materials cannot answer" queue (already prototyped, now on real events).

### 5.3 Performance, reliability and assurance
- Content-hashed static assets with long-lived caching and `ETag`; minify and bundle JS/CSS **[R-07]**.
- Pagination on all list endpoints; move BM25 to Postgres full-text search or `pgvector` hybrid retrieval; remove process-local state (one-time keys to the DB or Redis) so the app can run more than one worker **[R-05, R-06, S-07]**.
- Load test: 500 concurrent users with a realistic mix, p95 < 500 ms for non-AI routes, tutor time-to-first-token < 3 s.
- External light penetration test; close all Critical/High before go-live. ASVS Level 1 self-assessment documented.
- Accessibility audit (WCAG 2.1 AA) on the 10 most-used pages.
- Runbooks: deploy, rollback, restore, incident response, LLM provider outage (fall back to the offline engine).

**Day 60 exit criteria (go-live gate):**
- [ ] SSO works for all pilot roles; registry sync populated the pilot cohort with no manual SQL.
- [ ] Three pilot e-services run end to end with real dean's-office staff in staging.
- [ ] Load test and pen-test reports attached; no open Critical/High findings.
- [ ] Chosen LLM beats the offline engine on the eval set by an agreed margin; cost per question measured.
- [ ] Two engineers have each deployed to production and performed a rollback.

---

## 6. Days 61–90 — Pilot and evidence

**Goal:** turn the pilot into evidence an investor can audit.

- **Launch the pilot** (Day 61) with onboarding sessions for teachers and the dean's office, in-app tours (already built) and a support rota with the existing ticket desk.
- **Weekly pilot report** generated from events: adoption, engagement, AI quality, service turnaround, support load, incidents. The dashboard drops the "Pilot scenario" banner only when every tile is computed **[P-01]**.
- **Human review of AI answers:** teachers rate a sample of 20 tutor answers per course per week; results feed the eval set **[M-05]**.
- **Controlled comparison** (optional, needs university consent): compare practice-quiz scores of tutor users vs. non-users within the cohort as an early, clearly caveated learning signal. Do not claim effect sizes before this exists.
- **Multi-tenant readiness:** separate demo tenant from pilot tenant; a second university can be configured without code changes (dry-run with a fictitious tenant).
- **E-document validity:** either a working ASAN İmza / SİMA signing integration in staging or a documented legal path with timeline; until then documents stay marked "pilot, not legally valid" **[P-02]**.
- **Data room:** architecture and security overviews, DPIA, remediation table for every finding in [`AUDIT.md`](AUDIT.md), pilot report, eval results, measured unit economics, 12-month roadmap.

**Day 90 exit criteria = investor-ready MVP:** all seven items in §1 are true and evidenced in the data room.

---

## 7. Prioritized backlog and effort

Effort in engineer-weeks (ew). Owner roles: **FE** founder-engineer, **SE** senior backend/security engineer, **AI** AI engineer, **CEO** founder/CEO.

| Rank | Item | Findings | Phase | Effort | Owner |
|---|---|---|---|---|---|
| 1 | Close passwordless/admin exposure, demo flag | S-01, S-06 | Day 0–7 | 0.2 | FE |
| 2 | Fix keep-alive body handling + regression test | R-01 | Day 0–7 | 0.2 | FE |
| 3 | Server-side quiz integrity | R-03 | Day 0–7 | 0.3 | FE |
| 4 | Label/remove hard-coded KPIs | P-01 | Day 0–7 | 0.1 | FE |
| 5 | Sessions, headers, repo hygiene, CSV/PII fixes | S-02, S-03, S-07, S-10, R-11, H-01 | Day 0–7 | 0.5 | SE |
| 6 | AzTU pilot agreement, brand and data-sharing permission | M-04, H-05 | 1–30 | — | CEO |
| 7 | CI, Docker, pyproject, pytest conversion | T-02, H-03, H-04 | 1–30 | 2.0 | SE |
| 8 | Framework migration behind adapter | T-01, R-01, S-05 | 1–30 | 3.0 | FE + SE |
| 9 | Postgres + Alembic + object storage + backups | R-02, M-02, T-05, R-04 | 1–30 | 3.0 | SE |
| 10 | Interim staff auth with TOTP, rate limits | M-01, S-05 | 1–30 | 1.5 | SE |
| 11 | Upload hardening | S-04 | 1–30 | 0.5 | SE |
| 12 | Consent, retention, export/erasure | M-06, S-09 | 1–30 | 1.0 | FE |
| 13 | Logging, error tracking, uptime, audit coverage | M-03, S-08 | 1–30 | 1.0 | SE |
| 14 | Eval set + harness + LLM bake-off + async LLM | M-05, R-08, P-03 | 1–30 | 3.0 | AI |
| 15 | Event instrumentation and computed metrics | P-01 | 1–30 | 1.0 | FE |
| 16 | University SSO + provisioning | M-01 | 31–60 | 2.0 | SE |
| 17 | Registry/LMS import and sync | M-04 | 31–60 | 1.5 | FE |
| 18 | PDF ingestion with page citations | M-05 | 31–60 | 1.0 | AI |
| 19 | Admin console + per-tenant configuration | M-07, T-04 | 31–60 | 3.5 | FE |
| 20 | E-mail/SMS notifications | M-04 | 31–60 | 1.0 | FE |
| 21 | Search/retrieval on Postgres, pagination, stateless workers | R-05, R-06, S-07 | 31–60 | 1.5 | AI + SE |
| 22 | Static asset caching and bundling | R-07 | 31–60 | 0.5 | FE |
| 23 | Load test, pen-test remediation, accessibility audit, runbooks | — | 31–60 | 2.0 | SE |
| 24 | Pilot operations and support | — | 61–90 | 2.0 | FE + SE |
| 25 | Weekly evidence reporting and AI human review loop | P-01, M-05 | 61–90 | 1.5 | AI + FE |
| 26 | Multi-tenant dry-run, e-signature path | P-02, M-04 | 61–90 | 1.5 | SE |
| 27 | Data room and documentation | M-08 | 61–90 | 1.0 | CEO + FE |
| 28 | Readability refactors in touched modules; i18n template cleanup | T-03, T-06, T-07, T-08, R-09, R-10, R-12 | ongoing | 0.5 | all |
| | **Total** | | | **~36 ew planned vs ~32 ew capacity** | |

The plan is about 4 ew over capacity on purpose: estimates for the framework adapter and the admin console are the most uncertain and may come in lower. If they do not, cut from the bottom of each phase (ranks 22, 26 and 28 first), never from ranks 1–15.

---

## 8. Metrics we will report at Day 90

All computed from events, with definitions in the data room.

| Area | Metric | Why investors care |
|---|---|---|
| Adoption | Weekly active students and teachers (% of cohort) | Pull, not push |
| Engagement | Tutor questions per active student per week; return rate week-over-week | Habit formation |
| AI quality | Eval scores (groundedness, citation accuracy, Socratic compliance); share of answers with valid citations; helpfulness rating | Defensibility of the core feature |
| Teacher value | Questions drafted vs. approved in Test Studio; time from upload to published quiz; material gaps closed | Second user persona and buyer champion |
| Operations | Median request turnaround; SLA compliance; documents issued; support first-response time | Administrative ROI the university pays for |
| Reliability | Uptime; p95 latency; incidents and time to restore | Enterprise readiness |
| Unit economics | LLM + infrastructure cost per active student per month | Gross-margin story |

---

## 9. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| University access (SSO, registry) is slow | High | High | CEO owns it from Day 1; CSV import as fallback; staff-only pilot (dean's office + teachers) if student SSO slips |
| E-documents have no legal validity | High | Medium | Keep "pilot" marking; position documents as pre-filled requests until signature integration exists |
| LLM quality in Azerbaijani is uneven | Medium | High | Eval-driven model choice; keep grounded offline engine as fallback; teacher review loop |
| Student data leaves the country | Medium | High | Decide residency (D3/D4) with AzTU legal before real data; in-region open-weight option |
| Key-person risk and AI-written code nobody reviewed | High | High | Senior hire in month 1; mandatory PR review; tests before refactors |
| Scope creep from the broad demo | High | Medium | Pilot runs 3 e-services and the tutor; everything else stays in demo mode |
| Dashboard credibility | Medium | High | No literal metrics anywhere after Day 7; methodology notes on every tile |

---

## 10. Where the product can be genuinely differentiated

The audit shows the code already contains the seeds of a defensible position. The roadmap protects and proves them instead of adding breadth.

- **Azerbaijani-first, source-grounded Socratic tutor.** Most AI tutors answer in English and from the open web. Zəka answers from the teacher's own materials with citations and refuses to hand out final answers. The eval set (§4.4) turns this from a claim into a number.
- **Teacher-in-the-loop content flywheel.** Questions the materials cannot answer become a gap list for the teacher, and approved questions feed practice mode. The pilot measures whether the gap list actually changes materials.
- **Administrative workflows in the same product.** Tutoring plus e-services plus documents in one portal gives the university a measurable operational ROI (turnaround, SLA), which is what budgets are approved on.
- **Trilingual by construction.** AZ/EN/RU with full coverage already works and is rare in this market; it widens the path to other universities in the region.

Anything beyond these four is a post-pilot decision informed by the Day 90 metrics.
