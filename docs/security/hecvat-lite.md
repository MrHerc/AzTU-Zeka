# Zəka: HECVAT Lite self-assessment (draft)

A vendor self-assessment in the order of the EDUCAUSE HECVAT Lite questionnaire, for a university's procurement. It is a
draft. The current HECVAT 4.1.x workbook is the form to submit; these answers fill it. Each answer names its evidence. "Owner" marks an answer only the
operating organisation can give.

## Company and product

| Question | Answer | Evidence |
|---|---|---|
| Product and scope | Zəka, a campus platform: AI tutor grounded in course materials, campus assistant, attendance and grade journal, exams with Safe Exam Browser and a tamper-evident log, e-services with QR-verified documents, forum, clubs, integration hub | `SPEC.md` |
| Hosting model | Installed per university on the university's or a contracted server (single tenant); one container behind Caddy (TLS) | `infra/compose.yml`, `docs/runbooks/deploy.md` |
| Third-party runtime dependencies | None: Python standard library and vanilla JavaScript | `CLAUDE.md`, `requirements-dev.txt` (dev tools only) |
| Sub-processors | None by default. An external LLM only when the university configures one and the user consents | `nist-csf-profile.md` #3 |

## Application security

| Question | Answer | Evidence |
|---|---|---|
| Secure development lifecycle | Spec → plan → build → test → review (seven reviewers, refutation, regression tests) → security review, at every phase | `docs/security/review-log.md` |
| Automated security testing | Every push: lint, types, the full suite on Python 3.10–3.13 and Windows, gitleaks, pip-audit, bandit | `.github/workflows/ci.yml`, `security.yml` |
| Authorisation model | Deny by default; every route's access pinned in a matrix test; object-level checks per handler | `tests/security/` |
| Input handling | Typed body accessors, parameterised SQL only, output escaping, CSP | `nist-csf-profile.md` #15 |
| Penetration test | Not yet performed by a third party | Owner (planned: ASVS Level 2) |
| Vulnerability disclosure | `/.well-known/security.txt` with the operator's contact | `nist-csf-profile.md` #26 |

## Authentication

| Question | Answer | Evidence |
|---|---|---|
| Methods | Password (NIST 800-63B policy, scrypt) and OIDC single sign-on | `tests/integration/test_auth_login.py`, `test_oidc.py` |
| MFA | TOTP required for every staff role; recovery codes; passkeys not yet | `test_mfa.py` |
| Session management | Cookie only, hashed at rest, idle and absolute limits per role, renewed at sign-in and privilege change | `test_sessions.py` |
| Brute-force protection | Throttling per account and client, lock after 100 failures | `test_auth_login.py` |

## Data

| Question | Answer | Evidence |
|---|---|---|
| Data inventory and retention | Table × purpose × period × legal basis | `docs/privacy/data-inventory.md` (Task 40); retention job in `backend/zeka/legacy/periodic.py` |
| Encryption in transit | TLS (Caddy), HSTS | `infra/Caddyfile`, `backend/zeka/core/web.py` |
| Encryption at rest | Backups encrypted. The database volume: the host's disk encryption | `test_backup_restore.py`; owner |
| Backups | Encrypted, automated, mirrored to a second host, restore tested | `docs/runbooks/backup.md`, `tests/migration/test_backup_restore.py` |
| Data export and return | OneRoster, grades, attendance and registers; the user's own data (Task 40) | `manage.py export`, `test_oneroster_roundtrip.py` |
| Data deletion | A user's deletion request; academic records anonymised where the law keeps them (Task 40) | `docs/privacy/data-inventory.md` |
| Test data | Synthetic only; real files given by the university never enter the repository | `tests/fixtures/make_fixtures.py` |

## AI

| Question | Answer | Evidence |
|---|---|---|
| Is student data used to train a model? | No. The default engine is offline (retrieval over the course's own materials) | `backend/zeka/legacy/engine.py` |
| Is personal data sent to an AI provider? | Only if the university configures an external LLM and the user consents; PII is masked first | `test_security_review.py::test_history_is_masked_before_an_external_llm_call` |
| Are AI answers grounded and attributed? | Every tutor answer cites the course material it used; with no source it says so and hands over | `tests/unit/test_tutor.py`, `tests/eval/assistant_az.jsonl` (48/50) |
| Do humans make academic decisions? | Yes: the teacher publishes grades; the AI never grades an exam | `journal.service.publish_grades`, `exam` module |

## Incident response and continuity

| Question | Answer | Evidence |
|---|---|---|
| Incident-response plan | Roles, severity levels, containment, evidence, notification | `docs/runbooks/incident.md` |
| Breach notification | Per the university's contract and Azerbaijani law | Owner |
| Exam-day continuity | Exam-day runbook with a paper fallback; answers survive a killed worker or server | `docs/runbooks/exam-day.md`; `tests/integration/test_chaos.py`, `test_exam_verify.py` |

## Accepted risks disclosed

See `docs/security/threat-model.md`:
- **R1:** TOTP seeds are stored in the database.
- **R2:** the document hash has no key.
- **R4:** SEB 3.x has not been tested by hand.
