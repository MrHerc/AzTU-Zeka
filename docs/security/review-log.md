# Zəka: security and code review log

Every review of the V1 sprint, with where each finding's verdict, fix and regression test is written. The method is the
same at every checkpoint:
1. Seven reviewers run on the phase's diff: `ecc:code-reviewer`, `ecc:security-reviewer`, `ecc:silent-failure-hunter`,
   `ecc:python-reviewer`, `agent-skills:code-reviewer`, `agent-skills:security-auditor` and `agent-skills:test-engineer`.
   From Checkpoint D on, an architecture pass and a threat model are added.
2. Duplicates are merged.
3. A separate agent tries to refute each claim against the code, with probes on a temporary database.
4. Only what is confirmed is fixed, each with a regression test that fails on the code before the fix.
5. The phase then gets the `security-review` skill (high-confidence, exploitable findings only).

| Checkpoint | Phase · range | Claims | Verdicts and fixes | Security-review skill |
|---|---|---|---|---|
| — | The demo before the sprint, `a59ef1f` | 23 (1 critical, 5 high, 8 medium, 9 low) | `docs/SECURITY_REVIEW.md`: every critical, high and medium fixed except the git-history purge (owner) | — |
| A | Faza 1, Tasks 1–9 · `7df5ad4..` | 32 confirmed (backup, second host, keys, …) | `docs/review/checkpoint-a-2026-11-18.md` ("Təsdiqlənən", "Təkzib olunan") | Run with the review |
| B | Faza 2, Tasks 10–17 · `5609033..f425638` | 47 | `docs/review/checkpoint-b-2026-11-18.md`; tests in `tests/integration/test_checkpoint_b.py` (28 fail on `f425638`) | Run with the review |
| C | Faza 3, Tasks 18–22, 45 · `..19e3ff8` | 57 | `docs/review/checkpoint-c-2026-11-19.md`; `tests/integration/test_checkpoint_c.py` | Run with the review |
| D | Faza 4, Tasks 23, 25–30, 36 · `78534df..823bc4d` | 118: 91 confirmed, 24 partial, 3 refuted | `docs/review/checkpoint-d-2026-11-19.md`; `test_checkpoint_d.py`, `test_exam_gaps.py`, `test_checkpoint_d_regressions.py` | SR-1 (medium, a department head managed another department's exam): fixed, tested |
| E | Faza 5, Tasks 31–35, 37 · `afbfeae..777682f`; Task 46 · `4c63b4a` | 83: 66 confirmed, 13 partial, 4 refuted; Task 46: 11 confirmed, 1 partial, 2 refuted | `docs/review/checkpoint-e-2026-11-19.md` (per area, with the test of each fix) | No new finding ≥ 0.8; an older leak (OLD-1, an anonymous asker's id) fixed |
| F | Faza 6, Tasks 38–43, 47, 48, the owner's decisions, the language change · `1bc85c8..3ea4371` | Round 2: 38 confirmed, 0 refuted (F1, SEC-TT-1..3, CORR-F1/F2, TE-F1..F11, M1, L1–L20); round 1 and the reviews held while the work was built: per report | `docs/review/checkpoint-f-2026-11-22.md` (round 2 table, with the commit and test of each fix) | Security lens of round 2: SEC-TT-1..3, all fixed, tested |
| F addendum | Task 24, Task 48's hours report and export, Checkpoint F's open checks · `e02f1d6..1161c6b` | 28 confirmed, 0 refuted; one side claim (OK-1, low) left open | `docs/review/checkpoint-f-addendum-2026-11-23.md` | Security lens: SEC-FW-1..4, all fixed, tested |

## High and medium security findings since the sprint began

| Id | Where | Finding | Verdict | Fix and test |
|---|---|---|---|---|
| SR-1 | Exams (D) | A department head could open any exam's management view: the roster, exclusion reasons, raw scores and the SEB secrets | Confirmed, medium | `may_manage` by the department head's grant · `test_checkpoint_d.py` |
| SEC-E1 | Forum (E) | A question forwarded from the tutor was shown to the whole class with the author's name | Confirmed, medium | `teacher_questions.private` (0331) · `test_qa.py` |
| SEC-E3 / OLD-1 | Forum (E) | An anonymous forward named the student to the teacher, in the forum and through `student_id` in the old questions page | Confirmed, medium | Private anonymous topics hide the name; the id is dropped · `test_qa.py::test_the_old_questions_page_gives_no_id_of_an_anonymous_asker` |
| SEC-E5 | Clubs (E) | Leaving and joining again cleared a removal and a mute | Confirmed, medium | Membership kept as "left" · `test_community.py` |
| SF-E1 | Webhooks (E) | One bad receiver stopped every delivery | Confirmed, high (availability) | Per-delivery error handling · `test_webhooks.py` |
| SEC-E6 | Webhooks (E) | Private and metadata addresses accepted as webhook targets | Confirmed, low-medium (admin only) | Public addresses only in prod, checked at send time; no redirects · `test_webhooks.py` |
| SR46-1 | E-services (E) | A student with a staff grant approved their own request | Confirmed, medium | 403 on one's own request · `test_service_honesty.py` |
| TE46-1/2 | E-services (E) | Two acts at once skipped a step or issued two documents | Confirmed, required | Status and step read under the write lock · `test_service_honesty.py::test_two_acts_at_once_run_one_after_the_other` |
| SEC-TT-1 | Timetable builder (F) | A faculty-scoped academic office changed the university-wide timetable settings and the term's plan | Confirmed, medium | 403 unless the caller's scope is university-wide (`4f573f9`) · `test_tt_builder.py` |
| SEC-TT-2 | Timetable builder (F) | A scoped office queued a check run on a university-wide version, which it could then neither read nor cancel, and blocked the other office with 409 | Confirmed, medium | A run or its base version must cover the version's stored scope, `_covers_scope` (`4f573f9`) · `test_tt_builder.py` |
| SEC-FW-1 | Syllabus framework map (F addendum) | A teacher of any section changed the framework tags of an approved, published syllabus, and the student's page showed it with no approval | Confirmed, important | A submitted version keeps its own tags, `syllabus_versions.tags` (`0241`, `1b8d7a3`) · `test_frameworks.py` |

Low security findings of Checkpoint F and its addendum, all fixed: SEC-TT-3 (a scoped office read every draft and its problem list), SEC-FW-2 (the coverage report showed another department's draft outcome texts), SEC-FW-3 (a relabelled NICE file skipped the SHA-256 check and became the default; now imported as unverified) and SEC-FW-4 (nit: a deeply nested file crashed the import). Each report lists its fix and test.

Refuted claims are kept with their refutation in each report, for example:
- **CR-E9:** `/api/v1` responses do have `Cache-Control: no-store`.
- **SR46-2:** the student sees who handled the request by design; acceptance criterion 2 asks for it.
- **TE46-6:** a closed type's in-flight request may finish; the spec scopes "closed" to the offer.

## Open security items

Tracked in `docs/security/threat-model.md` (risk register R1–R4) and `docs/security/nist-csf-profile.md` ("Open for
D1–3").
