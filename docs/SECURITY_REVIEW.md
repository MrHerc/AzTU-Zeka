# Security review — Zəka (AzTU Rəqəmsal Kampus demo v0.3)

| | |
|---|---|
| Date | 2026-11-05 |
| Scope | Whole repository at `a59ef1f` (main): Python server (`app/`, `run.py`), SPA (`static/`), content, deployment (`render.yaml`), tooling, full git history, the committed `aztu-ai-campus.zip` |
| Standards | OWASP Top 10 (2021 categories), OWASP ASVS 4.0.3 Level 1 |
| Method | Manual code review of every route and helper, git-history and archive inspection, `bandit`, `detect-secrets` over every historical blob, `pip-audit`, black-box probing of a running server (curl, raw sockets), browser check of the changed login flow in Chromium |
| Result | 1 critical, 5 high, 8 medium, 9 low findings. All critical, high and medium findings are fixed in this branch, except the git-history purge, which needs a force-push by the owner. |

## Summary

The application is a stdlib-only Python server with a vanilla-JS single-page app. The code base is in good shape on
the classic injection classes: every SQL statement is parameterised, the SPA escapes by default and the CSP forbids
inline script. The serious problems were in **deployment and protocol handling**:

- The password-less demo login was published on the internet by `render.yaml` (`--host 0.0.0.0`). Anyone could become
  **admin** with one request, read every student's records and attachments, issue or revoke documents and wipe the database.
- A committed archive contained a **database snapshot with live session tokens**, internal notes and an older code copy.
- The hand-written HTTP layer allowed **response-header injection**, an **open redirect** and **request desync** on
  keep-alive connections behind a proxy.
- Uploaded PDFs and Office files could **exhaust CPU and memory** (decompression bombs, quadratic parsing).

No API keys, passwords or private keys were found anywhere in the working tree, the git history or the archive.

## Secrets that must be rotated

| # | Secret | Where it was exposed | Exposure | Action |
|---|---|---|---|---|
| 1 | 5 session tokens (`sessions` table: student, teacher, office, leader and **admin** personas, created 2026-10-05) | `aztu-ai-campus.zip` → `data/campus.db`, committed in `46a4e87` and still in history | Valid only against that database file: the developer's local copy and any copy made from the zip. Not valid on Render, where the database is regenerated at start. | Delete or reset the local database (`python run.py --reset`) on every machine that ran the zip. After this branch is deployed, sessions older than 12 hours are rejected anyway. Purge the archive from history (below). |
| — | API keys, passwords, private keys, cloud credentials | none found | — | Nothing to rotate. `config.json` (LLM key) has always been git-ignored. |

New secret introduced by this branch: `ZEKA_ACCESS_CODE`. Keep it only in the Render environment, never in the repository.

## Findings

Severity reflects the deployed configuration (public Render web service). Status: **Fixed** means fixed in this branch
with a regression test where practical; **Open** means a recommendation that needs a product decision or owner action.

### Critical

#### C-1 · Anyone on the internet can log in as administrator — Fixed
*OWASP A01 Broken Access Control, A07 Identification and Authentication Failures · ASVS V2, V4*

`POST /api/auth/demo {"role":"admin"}` (and `GET /demo/login?role=admin`) issued an admin session without any
credential. `render.yaml` starts the server with `--host 0.0.0.0` on a public `onrender.com` host, while the README
assumed a password-protecting reverse proxy that the blueprint does not create. With the admin or office role an
anonymous visitor could read all students' requests, medical-certificate attachments, grades and audit log, issue and
revoke QR-verified documents, and call `POST /api/admin/reset` to wipe the shared demo.

Fix (`app/security.py`, `app/r_core.py`, `run.py`, `render.yaml`, `static/js/main.js`):
- New shared **access code** `ZEKA_ACCESS_CODE`. A new visitor must enter it on the login page; it is compared in constant time.
  A visitor with a valid session can still switch roles through the demo menu.
- `run.py` **refuses to start** on a non-loopback host without a code. The only opt-out is the explicit `ZEKA_ALLOW_OPEN_DEMO=1`.
- `render.yaml` generates the code (`generateValue: true`). The owner reads or replaces it in the Render dashboard.
- Wrong codes are throttled: 10 per client per 10 minutes, then HTTP 429 even for the right code. Each attempt is audited.

Residual risk, accepted by design until SSO: anyone holding the code can take any role, including admin.
See L-5 for the reset endpoint.

### High

#### H-1 · Archive with a live database snapshot committed to the repository — Fixed in tree, history purge Open
*A05 Security Misconfiguration · ASVS V8 (data protection), V14 (configuration)*

`aztu-ai-campus.zip` (2 MB, commit `46a4e87`) contained `data/campus.db` with 5 session tokens, 147 user records
(synthetic personas), uploaded files, logs, compiled bytecode, and `.dev/` working notes that reveal a local Windows user path.
It also shipped an older copy of the code without later fixes.

Fix: removed from the tree; `.gitignore` now excludes `*.zip`, database files, `.env*` and key files.
Open, needs the owner: the blob remains in history. To purge it, all collaborators must re-clone afterwards:

```bash
git filter-repo --invert-paths --path aztu-ai-campus.zip
git push --force --all && git push --force --tags
```

GitHub may keep the object reachable from cached pull-request refs. Ask GitHub Support to run garbage collection
if the archive must disappear completely.

#### H-2 · Response-header injection and open redirect in `GET /demo/login` — Fixed
*A03 Injection, A01 · ASVS V5.1, V5.3*

`next` was decoded from the query string and written into the `Location` header unchecked apart from a prefix test.
`http.server` does not reject CR/LF, so `next=/x%0d%0aSet-Cookie:...` injected arbitrary headers
(session fixation, response splitting). `next=/%09/evil.example` passed the `//` test, and browsers strip the tab,
which made it an **open redirect**.

Fix: `safe_next()` accepts only same-site paths from a strict character set. As defence in depth, `_send()`
refuses any response header containing CR, LF or NUL.

#### H-3 · HTTP request smuggling / response desync on keep-alive connections — Fixed
*A05 · ASVS V13 (API), V14*

The server speaks HTTP/1.1 keep-alive behind Render's proxy, and three gaps let one client desynchronise a connection:
- When a handler failed before reading the body (401, 403, 415), the unread body was parsed as the **next request**.
  Behind a proxy that reuses upstream connections, a response can then be delivered to a different user.
- `Transfer-Encoding: chunked` was ignored, so the chunked body was parsed as a request.
- A negative `Content-Length` made `rfile.read(-1)` block until the client hung up. There was also no socket timeout,
  so slow clients could hold threads indefinitely.

Fix (`app/web.py`): chunked bodies are refused with 501. A missing, negative, non-numeric, conflicting or oversized
(>16 MB) `Content-Length` is refused before reading. The connection is closed whenever a body was not consumed.
Clients get a 30-second socket timeout.

#### H-4 · Stored HTML injection in the printable syllabus — Fixed
*A03 Injection (XSS) · ASVS V5.3*

`PUT /api/syllabus/{cid}` stored any JSON a teacher sent. `GET /syllabus/{cid}`, opened by teachers, leadership and
admins, interpolated `week`, assessment points, workload numbers and credits **without escaping**. Inline script was
blocked by the CSP, but `<form>`, `<meta http-equiv=refresh>` and `<base>` were not restricted, so credential phishing
and redirects inside the trusted origin were possible.

Fix: every value on the page is escaped. Saved syllabi are reduced to the known fields and types by
`clean_syllabus()`, and oversized ones are refused. The CSP now sets `base-uri 'none'`, `form-action 'self'`,
`object-src 'none'` and `frame-ancestors 'self'`.

#### H-5 · Denial of service through uploaded files — Fixed
*A05, A04 Insecure Design · ASVS V12.1 (files), V5.2*

- **PDF preview:** any signed-in user can upload a 10 MB PDF and request its preview. `zlib.decompress` had no output
  limit, so a 200 KB file expanded to 200 MB and more. The object regex `(.*?)\bendobj` is quadratic on files with many
  object headers and no terminators. Other tokeniser regexes have the same worst case.
- **DOCX/PPTX** (materials, previews): `ZipFile.read` decompressed members without limit (zip bombs). XML with a DTD
  was parsed; current expat versions limit entity amplification, but older system builds may not.
- Material uploads had no size limit below the 30 MB request limit.

Fix: PDF text extraction runs in a **separate interpreter** with a 15-second timeout, CPU and address-space limits
(POSIX) and at most two in parallel. Each stream is capped at 8 MB decoded, and the object scan is linear.
Office members are read with size caps per member and per archive. XML containing `<!DOCTYPE` or `<!ENTITY` is refused.
Materials are capped at 10 MB, and previews and uploads are rate-limited per user. A 200 MB bomb now returns in under
a second.

### Medium

#### M-1 · Sessions never expired — Fixed
*A07 · ASVS V3.3*

Sessions lived until logout. A role switch created a new session but left the old one valid, and nothing purged old rows.
Fix: absolute lifetime `ZEKA_SESSION_HOURS` (default 12) enforced on every request, with cookie `Max-Age` to match.
A role switch deletes the previous session, and expired rows are purged at login. Tokens grew from 24 to 32 random bytes.

#### M-2 · No rate limiting — Fixed
*A04, A07 · ASVS V2.2, V11 (business logic)*

Nothing limited logins, which create database rows, LLM calls (teachers had no daily cap), uploads, previews, one-time
links or the public verification page. Fix: in-memory limiters in `app/security.py`, keyed per user or per client
address. `ZEKA_PROXY_HOPS` controls how the address is taken from `X-Forwarded-For` behind a proxy; Render uses 1.

#### M-3 · CSRF defence relied on SameSite alone and a substring check — Fixed
*A01 · ASVS V4.2.2, V13.2*

State-changing requests were accepted from any origin if the cookie was sent. The JSON content-type test was a
substring match, so `text/plain; x=application/json` passed while still being a CORS "simple" request.
`SameSite=Lax` does not protect against same-site attackers such as sibling subdomains.
Fix: POST, PUT and DELETE are refused when `Sec-Fetch-Site` is not `same-origin` or `none`. Without Fetch Metadata,
the `Origin` header must match the host or the configured public URL. The media type must be exactly `application/json`.

#### M-4 · Outdated, vulnerable runtime pinned for deployment — Fixed
*A06 Vulnerable and Outdated Components · ASVS V14.2*

The app uses only the standard library, so CPython is its runtime dependency. `render.yaml` pinned **3.12.6**
(September 2024), ten patch releases behind the 3.12 line (3.12.16 at the time of review). Those releases include
security fixes to standard-library modules such as `urllib.parse`, `zipfile` and `tarfile`.
Fix: `PYTHON_VERSION: "3.13"` lets Render build with the newest 3.13 patch on every deploy. The self-test passes on
3.13.18. The security workflow fails when the pinned line is end-of-life or an exact pin is behind the latest patch,
and it warns six months before end-of-life.

#### M-5 · Privacy controls not enforced server-side — Fixed
*A04 · ASVS V8.3 (sensitive private data)*

- The consent dialog's optional "send masked questions to an external AI service" choice was **ignored**, so student
  questions went to the external LLM whenever one was configured.
- PII masking applied only to the new question. **Earlier chat turns were sent to the LLM unmasked.**
- `POST /api/consent` wrote the raw request body into the audit log, which allowed unbounded data.
- The 180-day chat retention promised in the consent text and set in admin settings was never enforced.

Fix: consent is stored as the two explicit choices. Students' questions reach an external LLM only with the external
consent, and the offline engine answers otherwise. History is masked before it leaves the server. Conversations older
than `retention_days` are deleted at start-up and whenever the setting changes.

#### M-6 · Missing security headers — Fixed
*A05 · ASVS V14.4*

There was no clickjacking protection (`frame-ancestors` or `X-Frame-Options`), no HSTS, and API responses carrying
personal data were cacheable. The `Server` header revealed the Python version.
Fix: `frame-ancestors 'self'`, `X-Frame-Options: SAMEORIGIN`, `Cross-Origin-Resource-Policy`, `Permissions-Policy`,
HSTS when the public URL is HTTPS, `Cache-Control: no-store` for dynamic responses and `Server: Zeka`.
Same-origin framing of documents inside the app was re-checked in Chromium.

#### M-7 · Assessment rules enforced only in the browser — Fixed
*A04 Insecure Design · ASVS V11.1 (business logic)*

The quiz time limit existed only as a browser timer, so a direct API call could submit at any time.
`POST /api/academy/module/{id}/complete` returned the full answer key on a failed attempt, which made the QR-verifiable
AI Academy certificate trivial to obtain. Fix: submissions later than the limit plus 2 minutes are recorded but not graded.
A failed academy attempt reveals only the answers the teacher already got right.

#### M-8 · Malformed input produced 500s and unbounded log growth — Fixed
*A09 Security Logging and Monitoring Failures · ASVS V7.4*

`int()` on request fields raised errors that became HTTP 500, and each wrote a full traceback to `logs/errors.log`,
which nothing rotated. Any client could fill the disk. There was also no access log.
Fix: `ValueError` and `TypeError` from handlers map to HTTP 400. Tracebacks are rate-limited to 30 per minute, and
the log rotates at 5 MB. Public hosts get a one-line access log on stdout (client, method, path without query, status, time).

### Low

| ID | Finding | Status |
|---|---|---|
| L-1 | **CSV formula injection** in the feedback export: user comments starting with `=`, `+`, `-` or `@` ran as formulas in Excel or LibreOffice (CWE-1236). | Fixed: such cells get a `'` prefix and all cells are quoted. |
| L-2 | The LLM `base_url` scheme was not restricted, so `urlopen` would also follow `file://`. The admin "test LLM" error could echo request details. | Fixed: https only (http only for localhost). The API key is masked in the error. |
| L-3 | The session token is also returned in JSON, kept in `sessionStorage` and accepted via `X-Session`, so script running in the page could read it, defeating `HttpOnly`. | Open: kept because the cookie-less fallback is used for embedded viewing. The strict CSP mitigates it. Recommended: drop the header fallback when SSO arrives. |
| L-4 | One-time document links carry the key in the URL query. | Accepted: single use, 5-minute expiry, `Referrer-Policy: same-origin`, and the access log omits query strings. |
| L-5 | `POST /api/admin/reset` lets any admin, meaning anyone with the access code, wipe the shared demo. | Open: product decision. Recommended: disable it on public deployments or require a second confirmation code. |
| L-6 | The login page said the server runs only on 127.0.0.1 even when it was public. | Fixed: the text depends on the deployment mode. |
| L-7 | Stdlib `ElementTree` parses untrusted XML (bandit B314). | Mitigated: DTDs are refused, and ElementTree does not resolve external entities. |
| L-8 | Uploaded PDFs and images are served inline from the application origin. | Mitigated: magic-byte type check, fixed MIME type, `nosniff`, no SVG or HTML accepted. Recommended later: a separate download origin. |
| L-9 | The office "document preview" uses an `iframe srcdoc`, which inherits the app origin, without `sandbox`. | Open: server-side escaping and the inherited CSP protect it today. Recommended: `sandbox="allow-same-origin"` after a print-flow check. |

### Verified with no issue found

- **SQL injection:** every statement uses placeholders. The f-string queries bandit reports interpolate only fixed
  column names, fixed table names or placeholder lists; each is annotated with its justification.
- **Authorization:** reviewed per route for files, requests, documents, tickets, courses, materials, quizzes, attempts,
  teacher questions, syllabi, news and analytics. Students see only their own records, teachers only their courses,
  and staff endpoints check the role. No IDOR found.
- **Path traversal:** static files are resolved and checked against the static root. Uploads are stored under their
  SHA-256 name. Download filenames are sanitised and RFC 5987-encoded.
- **XSS in the SPA:** the `html` tagged template escapes every interpolation. `md()` escapes before formatting.
  The CSP is `script-src 'self'` without `unsafe-inline`. Server-rendered documents escape all data.
- **Randomness:** session tokens, one-time keys and verification codes use `secrets`. `random` serves only demo data and quiz shuffling.
- **Third-party code:** there are no Python packages at runtime and no CDN; fonts and assets are vendored.
- **Outbound TLS:** `urllib` verifies certificates by default.

## ASVS 4.0.3 Level 1 coverage

| Chapter | Status after this branch |
|---|---|
| V1 Architecture | Threat surface documented here. SSO is planned for the pilot. |
| V2 Authentication | Demo uses a shared access code with throttling and audit (C-1). Per-user authentication is out of scope until SSO. |
| V3 Session management | Random 256-bit tokens, `HttpOnly`, `SameSite=Lax`, `Secure` on HTTPS, absolute expiry, logout and role-switch invalidation (M-1). |
| V4 Access control | Role and object checks on every route. CSRF protection (M-3). |
| V5 Validation, sanitisation, encoding | Output encoding everywhere, header and redirect validation (H-2), body and syllabus validation (H-3, H-4). |
| V7 Error handling and logging | Generic errors, bounded logs, access log, audit trail (M-8). |
| V8 Data protection | No-store caching, consent enforcement, history masking, retention (M-5, M-6). |
| V9 Communication | HTTPS at Render's edge, HSTS (M-6), TLS verification for LLM calls. |
| V10 Malicious code | No dependencies. CI scans secrets and code. |
| V12 Files and resources | Type by magic bytes, size limits, isolated parsing, zip and XML bomb guards (H-5). |
| V13 API | JSON only, strict content type, no CORS, request smuggling guards (H-3). |
| V14 Configuration | Security headers, maintained runtime, no secrets in the repo, fail-closed start-up (C-1, M-4, M-6, H-1). |

## Continuous scanning added

| File | What it does |
|---|---|
| `.github/workflows/security.yml` | **gitleaks** over the full history (weekly and on demand) and the new commits (push and PR). **pip-audit** for every `*requirements*.txt`. **CPython support check** for `render.yaml`. **bandit** at medium severity and confidence. Read-only token, SHA-pinned actions, no persisted credentials. |
| `.github/dependabot.yml` | Weekly grouped updates for the pinned actions and scanner versions. |
| `.gitleaks.toml` | Default rules plus an allowlist for two known non-secrets: the test fixture code and the verification-code alphabet. |
| `SECURITY.md` | Private vulnerability reporting through GitHub, and deployment rules. |
| `tests/selftest.py` | 43 new security regression checks. The self-test now runs 179 checks, all passing. |

## Owner actions

1. **Before or right after merging:** check that the Render service shows `ZEKA_ACCESS_CODE` under Environment.
   Blueprint sync should create it. If it is missing, for example because the service is not managed by the blueprint, add it by hand: without it the new
   build refuses to start and Render keeps the previous, vulnerable deploy running. Share the code only with demo audiences.
2. Rotate the leaked sessions (table above) and purge the archive from history (H-1).
3. In GitHub **Settings → Code security**, enable private vulnerability reporting, secret scanning with push protection,
   Dependabot alerts and Dependabot security updates. Then require the `Security` workflow in branch protection for `main`.
4. If the repository moves to a GitHub organisation, add a `GITLEAKS_LICENSE` secret, which gitleaks requires for organisations.
5. Decide L-3, L-5 and L-9 before the pilot.
