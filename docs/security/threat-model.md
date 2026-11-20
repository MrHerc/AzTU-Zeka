# Zəka: threat model for identity and exams (STRIDE)

Scope: the two areas where a breach changes a student's record or a degree. Identity covers sign-in, sessions, roles,
the second factor and API keys. Exams covers the exam session, answers, grading, release and the exam log. Every
mitigation names its code and its test; an accepted risk says why it is accepted and what would change the decision.
The controls are in `docs/security/nist-csf-profile.md`.

Actors:
- **Student**: may try to cheat or to read others' records.
- **Staff member**: a teacher, a dean's office, the academic office or a department head. Acts within a scope, and may
  overreach.
- **Administrator**.
- **Outsider on the network**.
- **Someone holding a database copy**: a backup thief, or an insider with file access.

## Identity

| STRIDE | Threat | Mitigation (code · test) | Residual |
|---|---|---|---|
| S | Password guessing, credential stuffing | scrypt hashes, NIST 800-63B policy, throttling per account and per client (IPv6 /64), account lock after 100 failures (`modules/identity/` · `test_auth_login.py`, `tests/unit/test_passwords.py`) | Low |
| S | A stolen staff password | TOTP required for every staff role; a code works once in its window; 5 wrong codes cancel the sign-in (`test_mfa.py`) | Low |
| S | Demo login on a reachable host | Prod mode has no demo routes; demo on a non-loopback host needs `ZEKA_ALLOW_OPEN_DEMO=1` (`test_auth_login.py::test_prod_signs_in_with_a_password_and_has_no_demo_login`, `test_modes.py`) | Low |
| T | A session id fixed or replayed | The id is renewed at sign-in and at every privilege change (`rotate_session`); only its SHA-256 is stored (`test_sessions.py`) | Low |
| T | A forged cross-site request with the user's cookie | Origin and content-type checks (`test_security_review.py::test_cross_site_requests_with_cookies_are_refused`) | Low |
| R | A staff member denies an act | Audit rows for role switches, grants, grade changes, exports, e-service steps (`request_events.role`); the audit table is append-only by trigger and keeps a row at least a year (`0410`, `test_security_review.py::test_the_audit_log_is_append_only_and_keeps_a_row_at_least_a_year`) | Low (someone holding the database file can drop the triggers) |
| I | A database copy reveals live sessions | Sessions are hashed (`test_sessions.py::test_a_copy_of_the_database_holds_no_usable_session`); backups encrypted | See R1 for TOTP seeds |
| E | A user acts in a role they do not hold, or outside its scope | The session's role is checked against `role_grants` on every request; scopes per role (`tests/security/test_roles.py`, `test_staff_scope.py`); every route pinned (`test_authz_matrix.py`) | Low |
| E | A student holding a staff grant decides their own request | Refused (Checkpoint E, SR46-1 · `test_service_honesty.py::test_a_student_with_a_staff_grant_decides_no_request_of_their_own`) | Low |
| E | An API key reaches a cookie route, or a cookie reaches a key route | Key routes read only the Bearer header and return before the cookie path (`test_api_tokens.py`) | Low |

## Exams

| STRIDE | Threat | Mitigation (code · test) | Residual |
|---|---|---|---|
| S | Someone else sits the exam for the student | The exam session ends every other session of the student; a sign-in during the attempt is logged and does not reach the exam (`test_exam_page.py`, `tests/security/test_exam_scope.py`) | Medium: identity at the desk is the proctor's job |
| S | The exam opened outside the hall or the browser | The exam's network list on every request; Safe Exam Browser config key and browser exam key checks (`test_proctor.py`, `test_seb_verify.py`, `tests/unit/test_seb_config_key.py`) | Medium: SEB 3.x on Windows still needs the owner's manual test (R4) |
| T | Answers changed after submission, or a score changed after grading | Each attempt is frozen at submission (answers' SHA-256, form seed); grading and release write events; `manage.py exam-verify` finds a changed answer or score (`test_exam_verify.py`) | Low |
| T | The exam log rewritten | A hash chain, append-only by trigger (`0301`), the root mailed at closing to the teacher and the dean's offices; `exam-verify --root` catches a chain rewritten in the database (`test_exam_verify.py`, `test_exam_chain_concurrency.py`) | Low, while the mailed root is kept outside the server |
| T | An answer after the deadline | Refused by the server's clock; autosubmit at the deadline (`test_exam_core.py`) | Low |
| T | A migration import writes during an exam | A writing import refuses while an exam is open; `--force` is audited (Task 38 · `tests/migration/test_etl.py::test_no_writing_import_while_an_exam_is_going_on`) | Low |
| R | A student denies having submitted, or a proctor denies an action | Every exam event in the chain with its time; proctor actions need a reason and are audited (`test_proctor.py`) | Low. AU-10 (non-repudiation by signature) is **not claimed** |
| I | Questions or keys reach a student before or outside their attempt | Exam questions out of the tutor's index, of practice and of Radar; a student sees only the public keys of their own form (`tests/security/test_exam_item_leak.py`) | Low |
| I | Results seen before release | Results visible only after release, to the course's teachers before it (`test_exam_release.py`) | Low |
| D | The server overloaded at the exam's start | The handler gate and the queue wait (503 with Retry-After); the load test of 300 students (`docs/perf/baseline.md`; Task 42 for 500) | Medium until Task 42 measures 500 on the university dataset |
| E | A teacher or department head of another course manages the exam | `may_manage` by the course's teachers and the department head's grant (Checkpoint D, SR-1 · `test_checkpoint_d.py`) | Low |

## Accepted risks and the risk register

**R1, TOTP seeds in clear (Task 12).** A database copy holds every second-factor seed. An attacker who also holds an
account's password can then generate its codes. Accepted for the pilot: with no key store and no runtime dependency, an
application-held key would sit next to the database it protects. Revisit when a secret store (an HSM, the OS keyring or
a KMS on the host) is available.

**R2, a document hash without a key (Task 45).** An issued document's hash is a plain SHA-256 of its stored payload, not a
keyed MAC or a signature. Someone with write access to the database could change a document and its hash together, and
the public verification page would still say it is valid. Accepted for the pilot: the registry number comes from a
sequence and the verification page shows the stored payload, so a forgery needs a database break-in, which the audit and
the backups expose. Revisit before third parties rely on documents at scale: sign the payload with a key held outside the
application database.

| Id | Risk | Decision | Owner | Revisit when |
|---|---|---|---|---|
| R1 | TOTP seeds in clear in the database | Accepted | Product owner | A secret store is available on the host |
| R2 | Document hash without a key | Accepted | Product owner | Third parties verify documents at scale |
| R3 | No append-only protection on the audit table | Fixed (`0410_audit_append_only.sql`, Task 41) | Development | — |
| R4 | SEB 3.x not tested by hand | Open | Owner | Before the first SEB exam |
