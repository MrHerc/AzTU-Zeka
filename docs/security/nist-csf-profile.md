# Zəka: NIST CSF 2.0 profile (self-assessed)

Self-assessment of the controls of `docs/research/04-nist-ve-uygunluq.md` §4 against NIST CSF 2.0 functions and
SP 800-53 Rev. 5.2.0 identifiers. NIST offers no certification: the honest claim is "controls mapped to the SP 800-53
Rev. 5 moderate baseline (self-assessed)" and nothing more (§5 of that note).

When a control is due: **D1–3** before any real student data (the 72-hour sprint), **D30**, **D90**. Every D1–3 control
links to the code or the test that shows it.

Status:
- **Done**: in the code and tested.
- **Partial**: in the code, with a named gap.
- **Owner**: an organisational measure the product cannot carry (a contract, a person, a process).
- **Planned**: a later task.
- **Not claimed**: deliberately not asserted.

Last checked at the Checkpoint F branch tip (2026-11-20). The suite runs on every push (`.github/workflows/ci.yml`).
Related: `docs/security/threat-model.md` (STRIDE, accepted risks), `docs/security/review-log.md` (findings and verdicts),
`docs/security/hecvat-lite.md`.

## GOVERN

| # | Control | SP 800-53 | Due | Evidence | Status |
|---|---|---|---|---|---|
| 1 | Named security/privacy owner, policies, risk register, security plan | PM-2, PL-2, RA-3, CA-5 | D30 | `SPEC.md` (Boundaries), the risk register in `docs/security/threat-model.md` | Owner: name the owner |
| 2 | Data inventory, retention schedule, consent records, data-processing agreement | PM-5(1), PT-2, PT-4, SI-12 | D1–3 | Retention: `retention_purge` in `backend/zeka/legacy/periodic.py`, `tests/integration/test_periodic_jobs.py`. Consent: `POST /api/consent` in `backend/zeka/legacy/r_core.py`, `test_security_review.py::test_consent_is_recorded_as_choices`. Inventory, export, erasure and retention settings: `docs/privacy/data-inventory.md`, `backend/zeka/modules/identity/privacy.py` (Task 40). DPA per university: owner | Partial: versioned consent, the inventory, export and erasure are done (`tests/integration/test_privacy.py`); the DPA is the owner's |
| 3 | LLM-provider and sub-processor agreements | SA-9, SR-3, SR-6 | D1–3 | The offline engine is the default (`backend/zeka/legacy/engine.py`); an external LLM is called only when `config.json` names one and the user consented to external processing (`external_ai_allowed`) | Owner: the agreement itself |
| 4 | AI policy: no personal data to an external LLM without agreement; AI output labelled; humans decide grades | PT-3, AC-4, SA-9 | D1–3 | PII masking `engine.mask_pii` (`engine.py:335`), `test_security_review.py::test_history_is_masked_before_an_external_llm_call`; every tutor answer cites a chunk (`tests/unit/test_tutor.py`); grades are entered and published by the teacher (`journal.service.publish_grades`) | Done (code); the written policy is the owner's |
| 5 | Secure development: reviewed merges, threat model, release checklist | SA-3, SA-8, SA-11, CM-3 | D30 | Checkpoint reviews A–F (`docs/review/`), `docs/security/review-log.md`, `docs/security/threat-model.md` | Done |

## IDENTIFY

| # | Control | SP 800-53 | Due | Evidence | Status |
|---|---|---|---|---|---|
| 6 | Asset and dependency inventory (SBOM) | CM-8, SR-4 | D30 | No runtime dependency (Python standard library only, `CLAUDE.md`); dev tools in `requirements-dev.txt` | Done for the runtime; an SBOM file: planned |
| 7 | Dependency, secret and static scanning in CI | RA-5, SA-11, SI-2 | D1–3 | `.github/workflows/security.yml`: gitleaks, pip-audit, bandit | Done |
| 8 | Patch deadlines; annual external penetration test (ASVS L2) | SI-2, CA-8 | D90 | — | Owner |
| 9 | Privacy impact assessment for grades, exams, AI tutor | RA-8, RA-3 | D30 | `docs/privacy/data-inventory.md` (Task 40) is its input | Owner: the assessment itself |

## PROTECT

| # | Control | SP 800-53 | Due | Evidence | Status |
|---|---|---|---|---|---|
| 10 | Real authentication: SSO or 800-63B passwords, salted slow hashes | IA-2, IA-5(1), IA-8 | D1–3 | scrypt in `backend/zeka/modules/identity/domain.py`; `tests/unit/test_passwords.py`, `tests/integration/test_auth_login.py`, `test_oidc.py`; prod has no demo login (`test_auth_login.py::test_prod_signs_in_with_a_password_and_has_no_demo_login`) | Done |
| 11 | MFA for staff and admin; passkey option | IA-2(1), IA-2(2) | D1–3 | TOTP (Task 12): `tests/integration/test_mfa.py`, `tests/unit/test_totp.py`; a staff role needs the second factor (`tests/security/test_roles.py::test_a_student_needs_a_second_factor_to_act_in_a_staff_role`) | Partial: no passkey |
| 12 | Server-side role checks and object-level authorisation, deny by default | AC-3, AC-3(7), AC-6 | D1–3 | Every route's access pinned in `tests/security/matrix.json` (`test_authz_matrix.py`); object checks: `test_security.py`, `tests/security/test_staff_scope.py`, `test_community_access.py`, `test_exam_scope.py`, `test_exam_item_leak.py`; e-service steps by role and scope (`test_service_honesty.py`) | Done |
| 13 | TLS everywhere, HSTS; encrypted database volume | SC-8, SC-13, SC-28 | D1–3 | Caddy terminates TLS (`infra/Caddyfile`, `infra/compose.yml`); HSTS in `backend/zeka/core/web.py:289`; backups encrypted (`tests/migration/test_backup_restore.py::test_the_backup_files_hold_no_plaintext`) | Partial: the volume's disk encryption is the host's (owner) |
| 14 | Secure session cookies, timeouts, revocation, CSRF protection | SC-23, AC-12 | D1–3 | `tests/integration/test_sessions.py` (hash at rest, idle and absolute limits, id renewed), `test_security.py::test_session_cookie_flags`, `test_security_review.py::test_cross_site_requests_with_cookies_are_refused` | Done |
| 15 | Input validation, parameterised SQL, output encoding, CSP | SI-10, SI-15 | D1–3 | `tests/integration/test_input_validation.py`, `test_http_layer.py`; CSP in `web.py:285`, `test_security_review.py::test_api_response_headers`; the escaping `html` template (`frontend/js/core.js`); SQL bound in every `repo.py`; literal route parts escaped (`tests/unit/test_web.py::test_a_literal_dot_or_dash_in_a_route_matches_only_itself`) | Done |
| 16 | Rate limiting, login throttling and lockout | AC-7, SC-5 | D1–3 | `RateLimiter` in `backend/zeka/core/security.py:58`; `test_auth_login.py::test_ten_failures_block_that_address_for_that_account_only`, `test_a_hundred_failures_lock_the_account_until_an_admin_unlocks_it`; `test_security_review.py::test_rate_limiter` | Done |
| 17 | Secrets out of the repository; a secret store; rotate anything ever committed | IA-5(7), SC-12 | D1–3 | `.gitignore` (`config.json`, `.env`, `infra/secrets/`); gitleaks in CI; `docs/SECURITY_REVIEW.md` (history purge) | Partial: the git-history purge needs the owner's force-push |
| 18 | LLM safeguards: input and output untrusted, no data or tool authority, quotas | SI-10, SI-15, AC-6 | D1–3 | The tutor answers from retrieved chunks and falls back to the offline engine (`backend/zeka/legacy/tutor.py`, `tests/unit/test_tutor.py`, `test_engine_llm.py`); the model has no tools; per-user quota `LIMITS["ai"]` and the daily message limit (`test_flow_tutor.py::test_daily_message_limit`) | Done |
| 19 | Safe uploads and official-document integrity | SI-3, SI-7, AC-3 | D30 | Type and size checks (`test_material_files.py::test_files_that_are_not_materials_are_refused`); documents keep their payload and hash (`test_document_integrity.py::test_a_tampered_document_is_reported_changed`) | Partial: no malware scan; the document hash has no key (threat model, accepted risk R2) |
| 20 | Hardened configuration: no debug, security headers, least privilege, no real data in test | CM-6, CM-7, SC-7 | D30 | Headers `web.py:281–289`; prod mode never seeds people (`ZEKA_MODE`); synthetic fixtures only (`tests/fixtures/make_fixtures.py`) | Done |
| 21 | Tenant isolation between universities | AC-4, SC-4 | D30 | One deployment per university (single tenant, `infra/compose.yml`) | Done by design |
| 22 | Exam integrity: server-side timing, keys never sent, tamper-evident submissions | SI-7, AU-10 | D30 | SI-7: the exam log is a hash chain, append-only by trigger (`0301`), `manage.py exam-verify`; `tests/integration/test_exam_verify.py`, `test_exam_chain_concurrency.py`, `tests/unit/test_exam_chain.py`; keys never reach the student (`tests/security/test_exam_item_leak.py`); deadline by the server's clock (`test_exam_core.py`) | SI-7 done. AU-10: **not claimed** (no signature: the root is mailed, not signed) |
| 23 | Staff on/offboarding, access reviews, training | AC-2, PS-4, AT-2 | D90 | Role grants and revocation (`tests/security/test_roles.py::test_a_revoked_grant_ends_acting_in_that_role`) | Owner: the process |

## DETECT

| # | Control | SP 800-53 | Due | Evidence | Status |
|---|---|---|---|---|---|
| 24 | Audit log of logins, failures, role and grade changes, exports, admin actions; protected; no secrets | AU-2, AU-3, AU-9, AU-12 | D1–3 | `store.audit` (`backend/zeka/legacy/store.py:80`); reads of personal records audited (`audit_read` in `matrix.json`); grade changes in `grade_changes` (`test_grade_journal.py`); exports (`test_integration_checkpoint_e.py`, `test_export_since.py::test_only_the_administrator_exports`); append-only by trigger: no update, no delete of a row younger than a year (`0410_audit_append_only.sql`, `test_security_review.py::test_the_audit_log_is_append_only_and_keeps_a_row_at_least_a_year`); kept 1–10 years by the university's setting (Task 40) | Done |
| 25 | Central log retention and alerts | AU-6, AU-11, SI-4 | D30 | Access log (`ZEKA_ACCESS_LOG`), job runs (`manage.py jobs status`) | Planned: alerts (Task 44) |
| 26 | Vulnerability-disclosure contact (security.txt) | RA-5(11) | D30 | `GET /.well-known/security.txt` from `ZEKA_SECURITY_CONTACT` (`backend/zeka/legacy/r_core.py`), `test_security_review.py::test_security_txt_names_the_operator_s_contact_or_is_not_there` | Done; the address itself is the owner's |

## RESPOND

| # | Control | SP 800-53 | Due | Evidence | Status |
|---|---|---|---|---|---|
| 27 | Incident-response plan, contacts, breach-notification deadlines | IR-4, IR-6, IR-8 | D30 | `docs/runbooks/incident.md` (roles, levels, steps, evidence, notification), `docs/runbooks/exam-day.md` (Task 43) | Partial: names and phone numbers on the target server (Task 44); the notification deadline is the lawyer's |
| 28 | Tabletop exercise and lessons learned | IR-2, IR-3 | D90 | — | Owner |

## RECOVER

| # | Control | SP 800-53 | Due | Evidence | Status |
|---|---|---|---|---|---|
| 29 | Encrypted automated off-site backups with a tested restore | CP-9, CP-9(1), CP-9(8), CP-10 | D1–3 | `infra/backup.sh`, `infra/restore.sh`, `backend/zeka/core/backup.py`; `tests/migration/test_backup_restore.py` (restore into a clean directory, the second host, a damaged copy re-sent); `docs/runbooks/backup.md` | Partial: the restore on the target server's second machine is Task 44 |
| 30 | Contingency plan; data return and deletion at contract end | CP-2, CP-4, SI-12(3), MP-6 | D90 | Exports for the data return (`manage.py export`, OneRoster round trip `test_oneroster_roundtrip.py`) | Partial: `docs/runbooks/cutover.md` (rollback by export), `docs/runbooks/backup.md`; deletion at contract end is the owner's |

## Open for D1–3

Each still needs an owner action or a later task before real student data:
- #2 (the data-processing agreement per university: owner).
- #3 (the LLM agreement, if an external LLM is used at all).
- #11 (passkeys: an option, not a blocker).
- #13 (disk encryption on the host).
- #17 (history purge).
- #29 (restore on the second machine).
