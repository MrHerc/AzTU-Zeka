# Checkpoint D review (2026-11-19)

## Scope and method

Faza 4 was reviewed at `823bc4d`: Task 23, Tasks 25–30 and Task 36. That covers the syllabus workflow, the exam core,
the student exam page, SEB, the proctor board, the hash chain and release, the e-mail outbox and the periodic job
runner. The fixes are in commit `1a6ac58`.

Seven reviewers ran:
- `ecc:code-reviewer`
- `ecc:security-reviewer`
- `ecc:silent-failure-hunter`
- `ecc:python-reviewer`
- `agent-skills:code-reviewer`
- `agent-skills:security-auditor`
- `agent-skills:test-engineer`

An architecture/performance pass and a threat model were folded in. Their ids are `AR-` and `TM-`.

How the findings were handled:
- Duplicates were merged. The claims were split into nine areas, A–H and T.
- For each area, a separate agent tried to refute the claims against HEAD. The agents worked on copies of the
  reviewers' faculty and university datasets, used real HTTP servers, ran browser runs for the exam page, and ran
  mutation runs of the whole suite for T. No repository file was changed during refutation.
- Only confirmed parts were fixed. A fix is listed below only if it can be seen in `1a6ac58`.

Abbreviations in the tables:
- `cd` = `tests/integration/test_checkpoint_d.py`
- `gaps` = `tests/integration/test_exam_gaps.py`
- `cd` tests fail on `823bc4d`.
- "no test" means the fix has no dedicated regression test yet (see "Other open items").

## Counts

| | Claims |
|---|---|
| Reviewed and refuted against the code | 115, plus 3 found during refutation (E6, NEW-G1, NEW-G2): **118** |
| Confirmed (including confirmed with a lower severity) | 88 + 3 = **91** |
| Partial (mechanism real, claim overstated or part refuted) | **24** |
| Refuted | **3** (PY-4, PY-10, PY-13) |
| Fixed in `1a6ac58` and `28f65c6` | **87** ids (AR-4, CR-9 and SF-7's backoff completed in `28f65c6`); AR-9 only in part |
| Fixed without a dedicated regression test | **25** of those 85 |
| Open: an owner decision | **7** ids in 6 topics (SF-14, TM-8, SEC-3, TM-17, TM-13, TM-14, AR-8), plus retake eligibility (from TM-6) |
| Open: deferred | **3** (AR-7, AR-10, AR-11), plus the polling part of AR-9 |
| Open: test-only gaps | **14** (T-1, T-4, T-8–T-11, T-15, T-16, T-19, T-20, T-22, T-23, T-27, T-28) |
| No change: informational, nit or by design | **4** (SEC-9, PY-8, AR-12, AR-17); AR-14 is answered by the load rerun (below) |
| Confirmed and still open | **18**: 4 owner decisions, 2 deferred, 12 test gaps; plus AR-9, which is only partly fixed |

## A. Attempt state, races, the write lock

The root cause is the same throughout this area. The transitions read attempts with autocommit and then wrote
unconditionally, so a request that read during the write window of `close()` could undo the close. The fix is
`repo.lock(c)` (`BEGIN IMMEDIATE`), taken before the first read in every transition.

| Id | Claim | Verdict | Fix | Test |
|---|---|---|---|---|
| CR-1 | Read-then-write: a submit, answer or end racing `close()` undoes it | Confirmed, High | `exam/service.py`: lock before the read in `answer`, `submit`, `autosubmit`, `close`, `act` | `cd::test_cr1_a_submit_racing_close_does_not_turn_a_graded_attempt_back` |
| AR-1 | Graded goes back to submitted; release skips the student and loses the score | Confirmed, High | Same lock; `autosubmit` locks before `overdue` | `cd::test_cr1_…`; `gaps::test_t3_…` |
| AR-2 | `release()` is N+1 under the lock; 213 ms at 300 students over HTTP | Confirmed, Medium | `journal/service.py` `put_exam_scores` (batch, one `refresh_finals`); release returns `{ok, released, skipped}` | `cd::test_ar2_close_and_release_of_300_students_keep_the_write_lock_short` |
| AR-3 | `close()` runs about 11 statements per attempt under the lock; 264 ms at 1 000 | Confirmed, Medium | Forms, answers and questions are read once before the first write; grading is done in memory | `cd::test_ar2_…` |
| AR-4 | `results()` is N+1; `change_score` builds results under the lock | Confirmed, Low | `change_score` returns `{ok, score}`; `results()` and `refresh_finals` use `journal.published_results` (a fixed number of queries per course, `28f65c6`) | equivalence test owed (see below) |
| TM-10 | An answer read before a submit, end or close is written after it (false `answers_changed`) | Confirmed, Medium | Lock-first in `answer` and `act` | `cd::test_cr1_…` (submit path); no separate answer/act test |
| CR-2 | Close and release hold the lock "for seconds" | Partial, Medium | As AR-2 and AR-3 | `cd::test_ar2_…` |
| CR-10 | Two concurrent statement closes give 500 instead of 409 | Confirmed, Low | `close_statement` locks first; the second waits, then gets 409 | no test |
| E6 | Two concurrent closes give 2 protocols and 2 roots | Confirmed (new) | Lock in `close`; the second close is refused | `cd::test_cr1_…` (second close → 400) |

## B. The hash chain and exam-verify

| Id | Claim | Verdict | Fix | Test |
|---|---|---|---|---|
| TM-1 | Correctly linked events appended after the close pass verify with the e-mailed root | Confirmed, High | `service.verify` flags `submission_after_close` / `grading_after_close`; the root is accepted anywhere in the chain | `cd::test_tm1_events_appended_after_the_close_fail_even_with_the_e_mailed_root` |
| TM-2 | Verify does not bind an attempt's existence, student, status or `max_score` | Confirmed, Medium | `attempt_missing`, `student_changed`, `status_changed`, `score_changed` (`max_score` included) | `cd::test_tm2_the_attempt_row_is_checked_against_its_events` (3 cases), `cd::test_tm2_tm5_…` |
| TM-3 | Events after the closing root have no anchor outside the database | Confirmed, Medium | `_send_root` on release, statement close and score change; the e-mail names the stage and seq | `cd::test_tm3_tm12_every_stage_mails_the_new_head_and_none_mailed_is_recorded` |
| TM-5 | The form that decides a grade is outside the chain | Confirmed, Low | `form_sha256` in the submission event; `form_changed` | `cd::test_tm2_tm5_…`, `gaps::test_t18_…` |
| TM-12 | The root e-mail can silently never leave | Confirmed, Medium | Audit row `exam_root_mailed` / `exam_root_not_mailed` at every stage | `cd::test_tm3_tm12_…` |
| SF-4 | Same as TM-12 (one sub-claim false) | Partial, Medium | As TM-12 | as TM-12 |
| TM-15 / PY-1 | `manage.py exam-verify` raises `KeyError` on an anchor problem | Confirmed, Low | `manage.py` prints `FOREIGN event`, `ANCHOR …`, `ROOT not in the chain` | `cd::test_tm16_sf11_…` (runs `manage.main`) |
| TM-16 | The anchor check reads the unhashed copy of the document | Confirmed, Low | `_anchors` reads the hashed payload (`payload_state`) | `cd::test_tm16_sf11_an_anchor_is_read_from_its_hashed_payload_and_must_exist` |
| SF-11 | A missing attempt or anchor is not a problem | Confirmed, Medium | `attempt_missing`, `anchor_missing`, `anchor_unreadable` | `cd::test_tm2_…`, `cd::test_tm16_sf11_…` |
| TM-21 | Nothing stops an UPDATE/DELETE of the log | Confirmed, Info | `0301_exam_events_append_only.sql`: `BEFORE UPDATE/DELETE` triggers | `test_exam_verify.py::test_the_log_refuses_an_update_or_a_delete_in_the_database` |
| CR-11 | Refusals, signals and sign-in notes are appended to a closed exam's chain | Confirmed, Low | `may_enter` answers "closed" before any event; no signals or notes on a closed exam | `cd::test_cr11_nothing_is_added_to_a_closed_exam_s_chain` |
| — | Release could put a raw score above the component maximum | Found while fixing | Release clamps the raw score | `cd::test_release_never_puts_more_than_the_component_maximum` |

The triggers stop mistakes, not someone who holds the database file. The e-mailed root stays the real guard.

## C. Release, the statement lock, who reads results

| Id | Claim | Verdict | Fix | Test |
|---|---|---|---|---|
| TM-6 / SEC-5 | A later release overwrites a score whose statement is closed | Confirmed, Medium | `put_exam_scores` skips with `statement_closed`; `exam_locked` follows the roster group | `cd::test_tm6_cr7_a_later_release_respects_a_closed_statement_and_a_newer_exam` |
| CR-7 | An older exam's release replaces a newer exam's score; `change_score` writes over another exam's cell | Confirmed, Low–Medium | Skip with `newer_exam`; `change_score` returns 409 if the cell belongs to another exam | `cd::test_tm6_cr7_…` |
| SEC-6 | Any appeal (rejected, of another course, reused) or free text counts as the basis | Confirmed, Low | The appeal must not be rejected or cancelled and must not have been used; an order number needs a digit | `cd::test_sec6_py9_an_appeal_counts_once_and_a_hand_score_is_rounded` |
| PY-9 | A hand score is stored unrounded | Partial, Low | `domain.points` rounding | `cd::test_sec6_py9_…` |
| TM-19 | Moving a student to another group removes the statement lock | Confirmed, Low | `exam_roster.group_id` (migration 0301); `roster_groups` and `locked_students` read it | `cd::test_tm19_moving_the_student_keeps_the_statement_lock` |
| SEC-4 | A department head outside the course reads results | Confirmed, Medium | `_may_see_results` and `course_results` use `journal.can_read_course` | `cd::test_sec4_a_department_head_outside_the_course_sees_no_results` |
| AR-5 | The office list drops its own exams past 200; groups are checked once per row | Confirmed, Medium | `released_exams_for_office`; each group is checked once | no test |
| SF-14 | Release publishes the exam cell while the final grade is dropped (no attendance) | Partial, Low | **Open: owner decision** (tied to J2) | — |
| TM-17 | SEB secrets reach wide audiences; the quit password is 32 bits | Confirmed, Low | **Open: owner decision** (with TM-8) | — |
| PY-10 | `StopIteration` on the exam column | Refuted | — | — |

## D. Exam questions in use, the pool, exceptions, refusals

| Id | Claim | Verdict | Fix | Test |
|---|---|---|---|---|
| CR-3 | Editing or deleting a question after forms are drawn mis-grades or breaks starts | Confirmed, High | `r_learning._exam_question_free`: 409 while an exam of the course is open; audit rows `exam_question_changed` / `_deleted` | `cd::test_cr3_tm4_an_exam_question_is_frozen_while_its_exam_is_open` |
| TM-4 | A silent key edit before close changes scores, with no trace | Confirmed | As CR-3. An approved exam question does not go back to draft (400). `open_exam` re-checks the plan against the pool | `cd::test_cr3_tm4_…`, `cd::test_tm4_opening_checks_the_pool_again` |
| SF-15 | A changed question scores an all-correct attempt 2/3, with no log | Confirmed | As CR-3 | `cd::test_cr3_tm4_…` |
| CR-4 | An exception on a draft exam is overwritten when the exam opens | Confirmed | `exception` needs an open exam (409) | `cd::test_cr4_tm11_an_exception_needs_an_open_exam_and_refusals_are_capped` |
| TM-11 / SEC-1 | `/enter` refusals write unlimited events | Partial, Low | `_refusal`: at most `REFUSAL_CAP` (10) per student, kind and exam; the 403 always happens | `cd::test_cr4_tm11_…` |
| TM-13 | The pool can equal the plan; no latest-start time | Partial | **Open: owner decision** | — |

## E. Exam sessions, SEB, proctor actions

| Id | Claim | Verdict | Fix | Test |
|---|---|---|---|---|
| TM-7 | Leave, sign in normally, re-enter: the ordinary sign-in is hidden | Confirmed, Medium | `leave` returns 409 while the attempt runs | `cd::test_tm7_leaving_is_refused_while_the_attempt_runs` |
| TM-9 / T-17 | An entry from an ordinary browser ends a verified SEB session | Partial, Low | `enter` on an SEB exam uses `end_sessions_except`; `seb_verify` ends the earlier session only on success | `cd::test_tm9_an_ordinary_browser_does_not_end_a_verified_seb_session` |
| TM-18 | An attempt extended past the window cannot re-enter after `closes_at` | Confirmed, Low | `may_enter` lets a running attempt back in | `cd::test_tm18_an_extended_attempt_comes_back_in_after_the_window` |
| PY-7 / SEC-7 | A non-ASCII hash is a 400 that rolls back the `seb.refused` event | Confirmed, Low | `compare_digest` on bytes (`seb.py`, `service.py`) | `cd::test_py7_sec8_a_non_ascii_hash_is_a_logged_refusal_and_unlock_needs_an_open_exam` |
| SEC-8 | Proctor `unlock` works in any exam state | Confirmed, Low | `unlock` only while the exam is open | `cd::test_py7_sec8_…` |
| SF-12 | The signal cap drops later flags of other kinds | Confirmed, Low | The cap is per kind | `test_proctor.py` (updated) |
| TM-8 / SEC-3 | A student holding the `.seb` file can forge the SEB check | Confirmed mechanism; accepted limitation | **Open: owner decision** | — |
| TM-14 | Proctor extend and reopen are unbounded | Confirmed, Low; partly accepted | **Open: owner decision** | — |
| SEC-9 | The config token is static and travels in the URL | Partial, Info | None: by design (128 bits) | — |
| PY-8 | `seb.read` is used only by tests; gzip errors escape | Confirmed, Info | None: it reads the reference file, by spec | — |

## F. E-mail outbox and the job runner

| Id | Claim | Verdict | Fix | Test |
|---|---|---|---|---|
| SEC-2 / SF-6 | A message that cannot be written (newline in the subject) blocks the queue | Confirmed, Medium | `mail.py` collapses whitespace in the subject; `send_due` fails a `ValueError` message alone | no test |
| PY-3 | A non-ASCII password or address breaks the batch | Confirmed, Medium | As SEC-2 | no test |
| CR-6 | Any 5xx (sender, login) fails a message for good | Confirmed, Medium | `permanent()` only for recipient refusal or a DATA 5xx; otherwise every message waits | no test |
| T-7 | A two-hour relay outage fails mail for good | Confirmed, High | `MAX_ATTEMPTS` 8 → 20 (about three days) | `gaps::test_t7_a_three_hour_outage_loses_no_mail` |
| AR-6 | A run has no time budget, so a root waits behind a long batch | Confirmed, Medium | `BUDGET_S = 20` per run | no test |
| SF-5 | A bad SMTP setting silently queues nothing | Confirmed, Low | `run.py` checks `mail.settings()` at start (`ap.error`) | no test |
| PY-2 | A failed bookkeeping write leaves the runner wedged | Confirmed, Medium | `jobs.loop` rolls back after a failed cycle | `cd::test_py2_a_failed_cycle_does_not_wedge_the_runner` |
| CR-8 | A run left `running` by a dead runner blocks the job for 30 min | Confirmed, Low | `_claim` counts as busy only a row whose holder still holds the lease; stale rows are marked `error` | `cd::test_cr8_a_run_left_running_by_a_dead_runner_does_not_block` |
| SF-20 | The runner's own stale `running` row blocks it | Confirmed, Low | Same query (`r.holder<>?`) | `cd::test_cr8_…` covers a dead holder only |
| SF-8 | An SLA reminder is marked sent with no recipient | Confirmed, Low | Mark it only when there is an office recipient | no test |
| AR-13 | `job_runs` and `outbox` are never purged | Confirmed, Low | `retention_purge` drops finished runs and mail older than 90 days | no test |
| PY-14 | A bad `ZEKA_JOBS_DELAY` gives a bare traceback; a failing runner restarts every second | Partial, Low | Clear exit message; restart backoff up to 60 s | no test |
| PY-6 | A failed `starttls`/`login` leaves a socket | Partial, nit | `connect` closes on failure | no test |
| CR-9 | `question`, `answer` and `plan` are e-mailed and cannot be switched off | Partial, Low | The kinds are in `KINDS` with labels and can be switched off; `plan` is off by default like `radar` (`28f65c6`) | `tests/unit/test_comms_domain.py` |
| SF-7 | A failing job has no backoff, and `job_runs` grows | Partial, Low | Growth is handled by AR-13. A failing job waits 1, 2, 4 … minutes, at most its interval and 30 min (`core/jobs.py`, `28f65c6`) | `test_jobs.py::test_a_failing_job_waits_longer_after_each_failure` |
| AR-7 | Radar snapshot and retention purge cost | Partial, Low | **Deferred** (see below) | — |
| AR-17 | `notify_email` loops over 10 000 recipients and queues none | Confirmed, nit | None (optional) | — |
| PY-4 | 999-variable SQLite limit | Mostly refuted | — | — |

## G. Exam page, proctor board, exam list (frontend)

None of these fixes has an automated test. `tests/e2e/exam_offline.js` and `test_exam_page.py` were not extended.
The only check is `node --check`, plus the suite's existing browser test.

| Id | Claim | Verdict | Fix (`frontend/js/…`) |
|---|---|---|---|
| SF-1 | An answer refused with 401/403/5xx/503 is deleted from the queue | Confirmed | `exam.js`: 400/404 drop it; 401/403 → `load()`; other statuses → offline and keep it |
| SF-2 | If localStorage cannot be written, no answer is ever sent | Confirmed | In-memory `memQueue`, `storageOk` notice |
| SF-3 | Submit wipes answers that were not sent | Confirmed | `submit` waits for the flush; a manual submit is refused while answers are queued |
| SF-9 | Answers that arrive after the deadline are dropped without a word | Partial | `lateDropped` shown on the final card |
| SF-10 | A submit refused with a non-zero status does nothing | Partial | A 409 → `load()`; other statuses → offline message |
| SF-13 | The board countdown jumps back after a failed poll | Partial | `proctor.js`: `fetchedAt` set only when data arrives; 401/403/404 → failure view |
| SF-16 | The student's exam list disappears on any error | Confirmed | `exams.js`: `failed(err.message)` |
| SF-17 | Repeated 5xx: a blank page and stacked retries | Confirmed | A single `loadTimer`/`loadBusy` |
| NEW-G1 | The page's own timer undoes a proctor's late extend or pause | Confirmed (new), Medium | Server: `submit(auto=True)` gets 409 before the deadline or while paused (`service.submit`); the page sends `{auto}` |
| NEW-G2 | A reopened attempt never reaches the open page | Confirmed (new), Medium | Polls also in the submitted state |
| AR-9 | The 20 s poll fetches the whole view | Confirmed, optional | **In part:** the enrolment check is one indexed lookup (`repo.is_enrolled`). Polling volume is deferred |
| AR-10 | Every board poll is a full snapshot; `act()` rebuilds it under the lock | Confirmed, optional | **Deferred** |

The NEW-G1 server rule has no dedicated test either.

## H. Syllabus and other items

| Id | Claim | Verdict | Fix | Test |
|---|---|---|---|---|
| CR-5 | An older approved version can be published over a newer one | Confirmed, Medium | `syllabus/service.actions()` refuses publish when a higher version is published | `test_syllabus_workflow.py::test_an_older_version_is_not_published_over_a_newer_one` |
| PY-5 | An over-long description is silently emptied | Confirmed, Medium | `syllabus/domain.py`: paragraphs kept; over 4000 characters or not a string → 400; `maxlength` in `syllabus.js` | `test_syllabus_validation.py::test_the_description_keeps_its_paragraphs_and_a_too_long_one_is_refused` |
| PY-11 | `tutor_modes` returns the module's own lists | Confirmed, nit | `TUTOR` holds tuples | `test_syllabus_validation.py::test_the_diff_orders_plan_weeks_as_numbers_and_tutor_modes_are_constants` |
| PY-15 | The diff sorts plan weeks as strings | Confirmed, nit | Numeric order | same test |
| PY-12 | The `pool_size` argument of `exam_input` is unused | Confirmed, nit | Argument removed | `test_exam_rules.py` (updated signature) |
| CR-12 | Without a tz database, exam windows are taken as UTC | Confirmed, Low | `to_utc` without a zone uses the server's local zone (`wall.astimezone()`) | no test |
| T-5 | Overlapping plan items fail a student at start (400 for 73 of 200 seeds) | Partial, High | `exam/domain._assign`: augmenting-path matching in `plan_problem` and `build_form` | `test_exam_rules.py::test_overlapping_plan_items_never_fail_a_student_at_start` |
| AR-8 | `analysis()` similarity is O(n²) in the request | Partial, Low | **Open: owner decision** (threshold) | — |
| AR-11 | The syllabus queue is N+1 with no pagination | Confirmed, Low | **Deferred** | — |
| AR-12 | Legacy imports the new modules in a cycle (inside functions) | Partial, nit | None | — |
| AR-14 | No scaling check covers the new write paths | Partial, Low | `cd::test_ar2_…` covers close and release at 300. The load rerun after the fixes: 3 000 / 3 000, 0 lost, p95 11 ms, board p95 28 ms | `tools/loadtest.py --scenario exam` |
| PY-13 | `build_form` depends on `random` staying stable | Refuted (the form is stored once) | — | — |

## T. Test review

| Id | Claim | Verdict | Fix | Test |
|---|---|---|---|---|
| T-2 | No integration test grades MCQ/TF answers by the shown index | Confirmed, High | Test only | `gaps::test_t2_right_mcq_and_tf_answers_by_shown_index_score_full_marks` |
| T-3 | No test runs autosubmit while an attempt still has time | Confirmed, High | Test only | `gaps::test_t3_autosubmit_leaves_an_attempt_with_time_left` |
| T-6 | No test sends a teacher of another course to the exam routes | Confirmed, High | Test only | `gaps::test_t6_a_teacher_of_another_course_manages_nothing` |
| T-7 | A relay outage loses mail | Confirmed, High (code) | See F | `gaps::test_t7_…` |
| T-12 | The student-view key test misses extra keys and post-close views | Confirmed, Medium | Test only | `gaps::test_t12_the_student_sees_only_the_public_keys_of_a_question` |
| T-13 / T-25 | No test catches a release that writes 0 for absentees, or scaling end to end | Confirmed, Medium/Low | Test only | `gaps::test_t13_t25_release_scales_end_to_end_and_writes_nothing_for_an_absent_student` |
| T-14 | Appeal checks untested; any appeal status accepted | Confirmed, Medium | See SEC-6 | `cd::test_sec6_py9_…` |
| T-18 | A form changed after submission changes the grade unseen | Confirmed (code gap) | See TM-5 | `gaps::test_t18_a_form_changed_after_submission_is_seen_by_exam_verify` |
| T-21 | Tests fail when run alone | Confirmed, Low | `test_exam_core.py` (3 tests start their own attempts); the syllabus test enrols and publishes its own version | the 4 tests pass alone and in their modules |
| T-1 | The leak test cannot see a Radar leak and accepts 400/404/409 | Partial, Low | **Open** (test not strengthened; `test_exam_item_leak.py` now also accepts 409 because of CR-3) | — |
| T-4, T-8, T-9, T-10, T-11, T-15, T-16, T-19, T-20 | A vacuous outbox kill test; Playwright never runs in CI; no backoff assertion; weak reminder, job race and syllabus-scope tests; `POLL_MS` not read; purge untested; the tutor limit | Confirmed (T-16 partial) | **Open: test gaps** | — |
| T-22, T-23, T-27, T-28 | Confirmed by reading | Low | **Open: test gaps** | — |

T-24, T-26 and T-29 to T-32 (all Low) were not re-verified.

## Owner decisions pending

| Topic | Options | Recommendation |
|---|---|---|
| **SF-14** (with J2): the exam score is released, but the final grade stays empty when the course has no attendance | (a) keep J2 (no attendance → no final grade) and show "attendance missing" in the results and statement; (b) count missing attendance as full marks; (c) import attendance first | (a). The office sees why the total is empty, and "missing" never becomes 0. |
| **TM-8 / SEC-3 / TM-17**: SEB hardening | (a) keep it as a documented limit (the check proves knowledge of the config only); (b) show the token and quit password only to the course's proctors and teacher, and lengthen the quit password; (c) allow-list Browser Exam Keys per SEB build; (d) an encrypted `.seb` with a password given out in the room | (b) now, because it is cheap. (c) after the owner's reference `.seb` and a manual SEB 3.x test on Windows. |
| **TM-14**: unbounded proctor extend and reopen (each needs a reason and is chained and audited) | (a) keep unbounded; (b) cap the total extension per attempt; (c) over the cap, office approval | (b)+(c): cap the total extension at the exam's duration, with office approval above it. |
| **TM-13**: pool equal to the plan; no latest-start time | (a) a warning at create/open when the pool is under 2× the plan per item; (b) refuse; (c) an optional latest-start time | (a)+(c). A refusal would block small courses. |
| **Retake eligibility**: `open_exam` puts every enrolled student on a retake or individual exam's roster | (a) the roster is the students with a failed or absent result in the main exam; (b) the office draws the list; (c) keep everyone, with exceptions | (a), with office exceptions for the rest. |
| **AR-8**: the similarity threshold in `analysis()` (O(n²) in the request) | (a) a fixed share of identical wrong answers; (b) a per-exam setting; (c) compute in a job above N students | The owner sets (a). Add (c) above 300 students. |

## Deferred (optional)

- **AR-10**: the board poll is a full snapshot, and `act()` rebuilds it under the lock. At 300 students and 3 proctors the board's p95 is 27 ms (`docs/perf/baseline.md`). Revisit after the load rerun.
- **AR-11**: the syllabus queue is N+1 with no pagination. Queues per head are small, and it was measured on the demo only. Revisit at university scale.
- **AR-7**: the radar snapshot holds the write lock for 191 ms on the university copy, and the retention purge scans tables. These are nightly jobs, not requests. The fix needs `created_at` indexes (a migration).
- **AR-9**: polling volume (a delta or ETag for the 20 s view poll). The 300-student exam run stayed within limits.

## Other open items

- **Fixed without a dedicated regression test:**
  - A: CR-10, AR-5
  - F: SEC-2/SF-6, PY-3, CR-6, AR-6, SF-5, SF-8, AR-13, PY-14, PY-6
  - G: all ten frontend fixes (including the NEW-G1 server rule) and the AR-9 lookup
  - H: CR-12
  - This falls short of the method's rule. These tests are owed before Checkpoint E.
- **Partly fixed:** AR-9 (the polling volume is deferred). AR-4, CR-9 and SF-7 were completed in `28f65c6`.
- **Test gaps** from area T, listed above.

## Verification at this point

- Full suite: **1374 passed, 2 skipped**, about 3.5 min.
  - The two skips are the SEB owner reference file (`tests/fixtures/reference.seb` and `.key`, not supplied yet) and
    `SEB_TEST_VECTORS`.
  - With the Moodle vectors from the scratchpad: 7 passed.
- `ruff check .`: clean.
- `mypy`: clean.
- `node --check` on every `frontend/js/*.js`: clean.
- i18n: en/ru 100%. `lint` has 72 known findings (official documents are in Azerbaijani). There are new strings for
  the syllabus, the exam service, the comms kinds and stages, and `exam.js`.
- Authz matrix: 231 routes.
- `tools/queryplan.py --dataset university`: no scans.
- `cd` tests fail on `823bc4d` and pass on `1a6ac58`. The four T-21 tests pass alone.

## Not verified, remaining risk

- **SEB:** no real SEB 3.x run on Windows. The SEB check proves knowledge of the config only (TM-8). The owner's
  reference file is missing.
- **E-mail:** no real SMTP relay. The 5xx classification, the time budget and the three-day retry were exercised
  against fakes and a closed port only.
- **Load:** the 300-student exam load test was rerun after the fixes on one worker: 3 000 / 3 000 answers, 0 lost,
  p95 11 ms, board p95 28 ms (`docs/perf/baseline.md`). Lock contention across several worker processes is measured
  only by the in-suite close/release test and the two-process chain test.
- **Untested fixes:** 25 fixes have no dedicated regression test (above), including all of the frontend fixes.
- **The races:** they were reproduced with threads on separate connections, not with separate worker processes.
- **GPL vectors:** the Moodle `quizaccess_seb` vectors are GPL. They stay in the scratchpad and are not committed, so
  CI cannot run them.
