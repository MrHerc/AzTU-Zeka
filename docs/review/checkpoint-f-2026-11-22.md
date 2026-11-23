# Checkpoint F review (2026-11-22)

## Scope

Everything on the branch since Checkpoint E (`1bc85c8..HEAD`, 63 commits):

- **Tasks 38–43.** ETL and reconciliation (`63bdd9d`). Measured indicators and accreditation evidence, and privacy
  (`69a3850`). The security review, security.txt, the NIST CSF profile, the threat model, HECVAT Lite and the
  append-only audit (`20726b5`, `4030a9b`). E2E, accessibility, load and chaos tests (`f6d57a1`, `7485b26`, `dada9cd`,
  `66e7663`). Runbooks (`f6d57a1`).
- **The owner's decisions of 2026-11-21** (`4078686`). The AI tutor and the assistant need a consent. The Radar score
  goes into the student's own export. The legal decisions are recorded, and Task 44 has its placeholders.
- **Task 47.** The Forma №3 reader was rewritten for the departments' real files (`a1f8b2e` and 19 review commits).
- **Task 48.** The timetable builder in three slices (`8410971`, `ac6e9c1`, `2835ace`), its review (`ade0fd5`,
  `bd28765`, `740dbdf`), the merge with Task 47 (`640166a`) and the joint acceptance on the real files (`639b1c7`,
  `ff6d606`, `6538943`).
- **The language change** (`69a02cf`, `9e72aec`, `5261122`, `57014ff`). The commits call it "Task 20", which is the
  session's work item. It is not `tasks/todo.md`'s Task 20, the attendance journal.

## Method

Checkpoint F ran in two rounds. The ids restart in each round, so a round-2 `TE-F1` is not a round-1 `TE-F1`.

**Round 1** covered `1bc85c8..01a7072`: Tasks 38–43 before the owner's decisions.
- Reviewers: `ecc:security-reviewer`, `ecc:silent-failure-hunter`, `ecc:code-reviewer`, `ecc:python-reviewer`,
  `agent-skills:security-auditor`, `agent-skills:code-reviewer` (architecture, `AR-`) and `agent-skills:test-engineer`.
- The claims were grouped into five clusters: migration, privacy, insight and tools, architecture, and test gaps.
- A separate agent tried to refute each cluster with probes on temporary databases (`scratchpad/probe/test_probe.py`).
  The test gaps were checked with mutation runs.
- The owner's decisions, Task 42's performance work, Task 47 and Task 48 each had their own review and refutation as
  they were built (section "Reviews held while the work was built").

**Round 2** covered `1bc85c8..5a43734`, the whole range, plus the language change on top. Six lenses ran:

| Lens | What it did | Findings |
|---|---|---|
| Security | Read every new or changed route from the matrix diff and the builder's scope helpers. Fuzzed `forma3.read` with 2 800 mutated copies of the two synthetic fixtures: none raised anything but `FormError`, and none took more than 5 s. Probed a live demo server and a copy of `test_tt_builder.py` with a faculty-scoped office. | 3 (SEC-TT-1..3) |
| Correctness of business rules | Timetable hours and scoring, Forma №3 re-import, publication and lessons, migration domain, privacy. Reproductions with pure scripts and a temporary integration test. | 2 (CORR-F1, F2) |
| Test engineering | 38 single mutants of the new rules. Every survivor was run against wider test sets, and all nine survivors together against the full suite. Test order was run forward, reversed and shuffled, under CPU contention too. | 11 (TE-F1..F11) |
| Earlier claims | Re-ran the checks behind Checkpoints B–E's claims: the exam hash chain, one-time keys across workers, sessions, step roles, forum privacy, prod mode, and a real backup and restore. | 1 (F1) |
| Mechanical i18n | Checked old keys left in lookups, en/ru for every new key, placeholders and plural forms, translations lost between `5a43734` and HEAD, and whether `0463` reaches an existing database. | 1 (M1) |
| Browser language pass | Opened 85 NAV routes for five roles in az, en and ru at 1 280 and 390 px (510 page loads; en and ru with `?i18n=debug`). Also ran the Forma №3 preview with both fixtures. | 20 (L1–L20) |

A separate agent per lens tried to refute each finding, on a scratch copy of the branch. Every finding was
**confirmed**, and none was refuted. Some details were narrowed:
- TE-F10: the 200+ ms was scheduler delay, not handler work.
- TE-F11: the 500 itself was not reproduced.
- SEC-TT-2: the violation count stayed 0 in the probe.
- CORR-F1: the owner's Q1 and the deferred hours page apply.
- L20: the «Bənd» part is close to taste.

Every fix has a regression test. Each test was shown to fail on the code before its fix, by stashing the fix or by
re-applying the review's mutant. The one exception is TE-F11 (see "Not verified").

Of the 38 mutants: 26 were killed, 3 were equivalent and 9 survived (TE-F1..F9).
- Equivalent: f301 (a year conflict also blocks), et04 (re-applies the newest order) and tt05 (`bump_rev`'s status
  filter answers 409 either way).
- Order and flakiness: the 16 new test files gave the same counts forward, reversed and shuffled (seed 7). The 222
  new unit tests passed in reversed and in random order.

## Round 2 findings

| Id | Severity | Finding | Fix |
|---|---|---|---|
| F1 | Medium (demo) | The demo reset (`store.reseed`, `POST /api/admin/reset`) lifted only the `audit` and `exam_events` triggers. One `student_status_events` row made it fail with a 500. It left the other append-only triggers dropped, because `DROP TRIGGER` ran in autocommit before the transaction began. Its connection held the write lock, so the next request waited 15 s. | `112b8ba`: every trigger is dropped, the data deleted, the triggers re-created and the seed written inside one `BEGIN IMMEDIATE`. Any failure rolls back and closes the connection (`test_demo_reset.py`) |
| SEC-TT-1 | Medium | A faculty-scoped academic office could change the university-wide timetable settings (`notice_days`, `review_required`) and the term's plan, including its confirmations | `4f573f9`: settings and plan answer 403 unless the caller's scope is university-wide |
| SEC-TT-2 | Medium | A scoped office could queue a check run on a university-wide version. The run stored the version's scope, and the caller could then neither read it nor cancel it. Meanwhile the other office's precheck and moves got 409. | `4f573f9`: a check run, or a run's base version, must cover the version's stored scope (`_covers_scope`, the same rule as runs) |
| SEC-TT-3 | Low | The version list and `GET /versions/{id}/scorecard` served every draft and its full problem list to a faculty-scoped office. This contradicts Task 48's "an out-of-scope id is 404". | `4f573f9`, revised in `7c24210`: a draft limited to named departments is visible only to a caller who covers each of them. A university-wide draft stays visible, and its scorecard lists only the caller's own units' problems. The first fix hid such drafts entirely, which broke the office's own work in them (`test_tt_pages`). |
| CORR-F1 | Medium | The S10 hours score counted a weekly placement's hours "before holidays". In the spring term (8 holidays), Monday lost 4 h and Thursday 0 h at the same soft cost, so the solver chose Monday. `hours_report` (holiday-aware) was called only by a test. On the real spring version, 183 units missed their Forma №3 hours by more than 2 h (−1 062 h in all). | `0c4bd6b`: `domain.lost_weeks(term, holidays, n)` gives the weeks each weekday loses. The solver, the scorecard and `hours_report` share it. The scorecard also counts the units off their hours, shown on the version page. The golden signature is unchanged. |
| CORR-F2 | Medium | A re-imported Forma №3 whose post became blocked (one subject cell blanked) left all of that post's earlier units active. The builder kept scheduling units the new file disowns, and no report said so. | `4aebb25`: the preview and the report list the earlier units this file no longer applies (`stale`). Applying sets those of a blocked or vanished post inactive, and a later file that has them again restores them. Units the registry cannot place this time are listed and kept. |
| TE-F1 | Test gap | The `stale_parent` publish gate had no test (the mutant passed the full suite) | `4f573f9`: tested at publish and in the queued publication's check |
| TE-F2 | Test gap | A department head approving their own availability grid: the 403 had no test, and without it the self-approval goes through | `4f573f9` |
| TE-F3 | Test gap | `scope_of` for a dean's-office grant below faculty scope had no test (such a grant can be created) | `4f573f9` |
| TE-F4 | Test gap | A back-dated status order must leave enrolments and the group unchanged: no test | `e83d0ae` |
| TE-F5 | Test gap | The newest order into a closed group: no test | `e83d0ae` |
| TE-F6 | Test gap | A second `visit` row on the same day: no test (it would inflate the active-student tile) | `e83d0ae` |
| TE-F7 | Test gap | A `dept_head` with no grants: no test | `4f573f9` |
| TE-F8 | Test gap | The T1 tolerance of Forma №3 could be loosened to 1.0 h unnoticed | `e83d0ae`: T1/T2 boundary tests |
| TE-F9 | Test gap | A break exactly equal to the travel time (`<=` vs `<`) had no test | `e83d0ae` |
| TE-F10 | Flaky test | Under CPU load, `test_import.py` failed 5 of 6 runs on the 200 ms write-lock guard. The real hold was 1–2 ms. | `a6ed8c0`: the guard fails on 200 ms of the handler thread's CPU time or 1 s of wall time (`test_tx_guard.py`). Next to 4 busy cores: 2 of 3 runs failed before, 0 of 3 after. |
| TE-F11 | Test gap | A 500 during the e2e node run was swallowed: the module-scoped fixture ran before the per-test server-error guard took its snapshot | `a6ed8c0`: the e2e fixture asserts that the server logged no exception during the node run, and prints the tracebacks |
| M1 | Low (demo) | `0463` did not rewrite the seeded `support_tickets` and `support_messages` of an existing demo database, so their old Azerbaijani keys lost their en/ru | `8a14f54`: `0464_language_review.sql` rewrites them, a column only while it still holds the old seeded text. `0463` is not edited. |
| L1 | Low | "Məsləhət" (consultation, a load type) shared the key of the tip label: EN "Tip" | `8a14f54`: split keys |
| L2 | Low | A parameter read from a file was translated: «Fizika» from a cell became "Physics" | `8a14f54`: `i18n.Lit` marks a parameter shown as written |
| L3, L4, L11, L16 | Low | Shared keys with the wrong sense: "Auditoriya" (audience/classroom), "Qeydiyyat" (enrolments/register), "Sahələr", "Yoxlama", "Yeni müraciət" under a count | `8a14f54`: split keys |
| L5 | Low | The academy levels read "Start" / "Average" | `8a14f54`: renamed levels, `0464` for existing rows |
| L6 | Low | The student's next lesson showed "1, 09:00": `next_lesson` put the row after the weekday name, so the row's number overwrote it | `8a14f54`: server key order; `test_flow_student.py` checks the weekday |
| L7 | Low | The seed's grade component names had no catalogue entry (EN showed "SƏRBƏST IŞ 1") | `8a14f54`: extracted and translated |
| L8 | Low | A readiness label with ": " was left untranslated as a whole | `8a14f54`: translated part by part |
| L9 | Low | RU "{what} не найден(а)" did not agree with its noun | `8a14f54`: one message per kind |
| L10 | Low | RU statuses were gendered or plural against `STYLE.md` §6 | `8a14f54`: neutral |
| L12, L13, L14, L19 | Low | Azerbaijani forms the new `STYLE.md` bans: «-anda/-əndə» clauses, «olmaz», «günlük», «pəncərə» for a time window, «X-i silmək?» questions, “ ” quotes, no comma after «məsələn» | `8a14f54` through `tools/i18n.py rename`; achievements use «» |
| L15 | Low | Numbers and dates ignored the interface language (`2.2%`, `187.6667 saat`, an az date in the EN Radar line) | `8a14f54` (`i18n.date3`), `3ea4371` (the Radar test checks each language's format) |
| L17 | Low | The audit page showed the raw action `rooms_linked` | `8a14f54`: labelled |
| L18 | Low | "{x} xana" had no plural forms ("1 cells") | `8a14f54`: plural forms |
| L20 | Low | Single wordings: RU "Новая новость", "Bağlı" → "Closed" for a disabled tutor, "Yoxla" → "Review" on a dry-run button, "Bənd" → "Clause" in readiness | `8a14f54` |

## Reviews held while the work was built

These findings were confirmed by refutation and fixed before round 2. Each has a regression test that fails before
its fix.

**Round 1 (Tasks 38–43)**

| Commit | Findings fixed |
|---|---|
| `a879a73` | SEC-F1/SA-F2: the screen import refuses the history kinds (status orders stay with the registry office). SEC-F2/SA-F1/AR-F6: a users import never undoes an erasure. SEC-F4/SF-F7: the last admin cannot be erased. SA-F5: nothing reaches the external LLM unmasked. SA-F6: the erasure notice names the request, not the person. SA-F7: no AI draft in the export. SA-F8: no self-grant. SF-F8: one retention period. SF-F9: consent names its version. PY-F2: the privacy queue filters by scope before its limit. SF-F3: a failed event write never fails the request. CR-F1: pre-cut-over lessons leave the journal tile. TE-F12, TE-F14, SF-F13. |
| `dd26c61` | AR-F1: only the newest status order acts. AR-F7/PY-F7: historic orders may name closed groups. AR-F8/CR-F2: reconcile compares the very records Zəka holds. AR-F2/SF-F10: openings stop at `--as-of`, and a repeated lesson is refused. SF-F1: the ETL checks every part before writing any. SF-F2: history is marked only when the wave reconciles. SF-F4, SF-F5, SF-F11, PY-F1 (the exam check is repeated under the write lock), PY-F4, PY-F8. TE-F1/F3/F5/F8/F9/F13/F15. SA-F11: security.txt's `Expires` is the operator's date. |
| `3a9bd4f`, `c41dc4c` | AR-F4: 27 person-column indexes (`0401`), and export is limited to 5 per hour. AR-F5: batched retention purge; the settings request purges in its own transaction (review R1, R2). TE-F2: exact export counts. TE-F10: tile periods. TE-F11: the runner loop's lease. PY-F5, TE-F6: query-plan exam steps over 1 000 rows. |
| `7cf3526`, `4030a9b` | SA-F3: the audit is purged after its retention period, never "never" (and `0410` makes it append-only). SA-F10: docs cite symbols, not line numbers. A pre-existing failure: the demo reset failed after any exam event. Round 2's F1 found that fix incomplete. |
| `dada9cd`, `66e7663` | AR-F11 (partial): active-user tiles read `active_days` (`0421`, `0422`) instead of `COUNT(DISTINCT)` over events |

Refuted in round 1: SF-F12 (the scenarios run in sequence), SEC-F3 (it is the person's own data, documented), AR-F10
(by design) and round-1 TE-F4 (`test_student_status` catches it). Partial and kept as decisions: SF-F6 (`audit.detail`
keeps usernames; append-only, recorded in `data-inventory.md`), SA-F7 (the Radar score in the export: the owner
decided yes in `4078686`) and SA-F9 (the 'ai' consent is now enforced, by the owner's decision).

**Owner's decisions review**: `4c194ba` (F1: refusing the AI consent no longer raises the Radar score) and `b3eb5ed`
(F2: an external AI the notice does not name is not used).

**Task 42 review**:
- `d63a73a` (F1): the dashboard's Radar card reads the summary too.
- `38948e3` (F2): the load tool resends only after a closed connection, never after a timeout.
- `c7ed152` (F3): the news selection is tested itself.
- `41984fb` (F4): the migration number is `0421`.

**Task 47 review**: 16 confirmed findings in 19 commits. They cover T5 as a real check, T6 on the vacancy cell and
the grand totals, a reader linear in bad rows, the anchor cell as the unit key, the error value as a conflict, people
and sheet-name matching (PTS-1..4) and the hidden sheet never applied. The list is in `tasks/todo.md`, Task 47.

**Task 48 review** (`ade0fd5`, `bd28765`, `740dbdf`):
- F1–F7: the solver and the checker read one rule.
- TT-SEC-1..4: a publication past its check never stays half done; hand-written units keep their rows; only a
  university-wide office publishes.
- UX1–UX14, L1–L5: the pages say what is wrong and where.

## Measured

**Suite.** 2 016 tests are collected.
- Round-2 fix run: 1 999 passed, 16 skipped and 1 failed (the Radar date test L15 changes on purpose, fixed in
  `3ea4371`).
- Re-run on HEAD for this report: 2 000 passed, 16 skipped, 0 failed ("Suite on HEAD" below).
- `ruff check .` and `mypy` are clean, and `node --check` passes on every `frontend/js` file.
- i18n: `stats` 100 % for en and ru, `lint` 72 (official documents) and `i18n/todo` empty.
- 321 routes are in `tests/security/matrix.json`. Round 2 changed no route.

**Load and query plans** (`docs/perf/task42.md`; development container, 4 cores, `university` dataset):

| Run | Result |
|---|---|
| Mixed, 1 000 users, 600 s, think 5 s, 2 workers | 120 784 requests, 201 req/s, p50 9 ms, p95 37 ms, p99 256 ms; 5xx 0, 4xx 0, connection errors 0; 296 resent on a new connection |
| Exam, 500 students, 1 800 s, entries within 60 s, 2 workers | p95 20 ms, p99 58 ms, 5xx 0; 0 of 5 000 answers lost; proctor board p95 48 ms; `exam-verify` passed |
| Leadership dashboard `GET /api/analytics` | 13 335 ms → 6 196 ms (`0420`) → 94 ms; 169 ms with the Radar card from the summary |
| Radar page `GET /api/radar` | 6 927 ms, still live (it is the page, not the dashboard) |
| Query plans, mixed and exam routes | no `SCAN` of a table over 1 000 rows |
| Chaos | `kill -9` of a worker or of the whole server, and a write lock held for 2 s by another process: every answer the server confirmed is stored, 5xx 0 |

Caveats:
- The mixed run used the old resend rule (fixed in Task 42 F2) and was not repeated.
- The exam run came before `active_days` added one `INSERT OR IGNORE` per writing request, and was not repeated
  either.

**Forma №3 and the builder on the two departments' real files.** Only counts are given here. The files and their
names never entered the repository or this report.
- Read exactly: RT 348 units / 7 942 h and MR 1 245 units / 29 783.5 h (1 233 outside the hidden sheet). T1–T3 pass
  on every post (34/34 and 164/164). 0 cells are unclassified.
- Imported through the preview and apply routes: 1 530 units (RT 335, MR 1 195). The registry refused 0. The rest
  were held back by the reader's blocks (RT 3 posts, MR 4) or by the hidden sheet (12). Apply held the write lock
  10.9 ms and 37.9 ms.
- Autumn: 860 units and 924 meetings, all placed, 0 hard violations. Spring: 670 units and 701 meetings, all placed,
  0 hard violations. Each run did 50 000 iterations in 4.4 s wall (4.2 s CPU).
- Spring was published: 701 rows, 7 280 lessons and 102 notifications, with the longest transaction 27 ms. A
  separate SQL check over the rows and lessons found 0 violations, and the server logged 0 tracebacks.
- The spring hours difference (−1 062 h, 183 units more than 2 h off) was measured before CORR-F1, and is the
  evidence for that finding.

**Earlier claims re-verified** (round 2, earlier-claims lens):
- 191 tests behind Checkpoints B–E passed, plus 104 in `tests/security` and the privacy and exam files.
- A real `infra/backup.sh` / `restore.sh` round trip kept 118 tables, 28 544 rows and 19 uploads, with
  `integrity_check` ok, all 6 append-only triggers and all 59 `schema_migrations` rows.
- In prod mode, `--reset` is refused, a non-database `campus.db` is left untouched, the demo routes answer 404 and 0
  users are seeded.

### Suite on HEAD

`python -m pytest -q -p no:cacheprovider` on HEAD (`3ea4371`), once, for this report: **2 000 passed, 16 skipped, 0
failed** (exit code 0). The skips are the 14 axe-core page checks (axe-core is not installed here) and the 2 SEB vector
tests that need the owner's reference `.seb` file.

## The language change

- `tools/i18n.py rename MAP.json [--apply]` rewrites an Azerbaijani key wherever it is a key:
  - a `t()/S()/T3()/E()/S_()` argument, an implicit server key, a content string the extractor reads, or a test
    literal;
  - en/ru move with the key, merge into an existing key, or change in place;
  - a key that is also an unrelated literal, or that sits inside a longer content string, is refused;
  - it is a dry run by default, and a second run changes nothing (`tests/unit/test_i18n_rename.py`).
- 912 mapping entries were applied: 521 keys renamed, 556 code literals and 1 test literal rewritten, 1 511
  translations moved or changed, 0 refused. 6 shared keys were split.
- The 505 strings added after the mapping (Tasks 42, 47, 48) were checked: 37 keys were renamed and 100 translations
  changed.
- `0463_language_catalogue.sql` (86 updates) and `0464_language_review.sql` bring the seeded texts of an existing
  database to the new keys. A column changes only while it still holds the old seeded text.
- `engine.grade` accepts the Russian and English true/false words (8 cases failed before).
- `i18n/STYLE.md` is the style guide, and `i18n/BRIEF.md` holds the glossary.

## Open

- **Task 44, the owner's inputs** (`docs/runbooks/release-v1.md`, `tasks/todo.md` Task 44): the target server and the
  backup host, the manual SEB 3.x test on Windows, the reference `.seb` file and its key, the incident contacts, the
  security contact and review date (`ZEKA_SECURITY_CONTACT`, `ZEKA_SECURITY_EXPIRES`), and T0. Without them, the
  restore test, the load test on the target server, the wave-0 import and the reconciliation against T0 cannot run.
- **The departments' questions**: `docs/forms/forma-3.md` §12, 19 questions. They cover group-code suffixes, the
  weeks per term and odd hours, student counts, who teaches the vacancy load, the other-year sheets, kinds of work,
  subject identity, data errors by cell and the doctoral supervision column. Until they are answered, the reader
  reports each case as a note or a conflict.
- **The timetable office's questions** (Q1–Q21 of the builder's design, outside the repository). They cover term
  dates, holidays and whether holiday losses are made up (Q1, which also decides CORR-F1's target), the weekly
  pattern and its tolerance, the bell schedule and Saturdays, who publishes and signs, central or per-faculty
  building, shifts, rooms, splits, daily limits, availability of external staff, electives, vacancies and unplaced
  classes, streams, the order of the soft rules, notice and deadlines, review and silence, the document's layout, the
  weekly load, practice and military weeks, and whether the current timetable becomes version 0. The publish gate
  refuses while the defaults D1–D3 are unconfirmed. The acceptance run confirmed them only for the measurement.
- **The builder's deferred parts** (`tasks/todo.md`, Task 48): review and notes, the faculty's QR document and its
  print, blocks (practice weeks), the department's sign-off, the rooms' "open for timetable" and "reserved" boxes, a
  department choice on import, the hours-report page, CSV and `manage.py export --kind timetable`, `timetable-replay`,
  `timetable.health` with the repair run, and adopting existing rows as version 0.
- **Task 24** is blocked: this environment's proxy refuses the NICE file's host.
- From earlier checkpoints: T28 (the owner's `.seb` file and the manual SEB test), the route CSVs from floor plans,
  the 10-day deadline against Decree No. 225, and the open low items of Checkpoint E.
- `docs/security/review-log.md` (Task 41) does not yet list Checkpoint F's findings. This report is their record.

## Not verified

- The full suite ran once on HEAD; the e2e/a11y browser checks ran without axe-core (14 skipped).
- TE-F11: the new e2e assertion was not shown failing, because that needs a 500 during the browser run.
- The new labels of the language fixes were not opened in a browser.
- CORR-F1 was not re-measured on the real files after the fix. There is still no hours-report page, and the publish
  gate does not block on hours; the scorecard row shows the count.
- M1: the Azerbaijani text inside `notifications` and `interventions` rows was not rewritten. Those rows carry their
  own en/ru, so no translation is lost. The seeded test questions in `content/seed.json` still use “ ” quotes.
- The import count: `tasks/todo.md` (Task 48 acceptance) says 70 units were held back by the reader, but the
  acceptance output gives 13 (RT) + 38 (MR) + 12 (hidden) = 63. The difference was not reconciled.
- The load figures come from the development container, not the target server.

## Remaining risk

- CORR-F1 changes S10 costs for every real term. Drafts and versions computed before it keep their old scores until
  they are re-run or re-checked.
- CORR-F2 deactivates units on apply. A department file that is wrong in one cell takes that post's units out of the
  builder until a corrected file is applied. The preview lists them before apply.
- SEC-TT-3's final rule shows a university-wide draft's grid to a faculty-scoped office, with the problems limited to
  its own units. This is a decision to confirm in the owner's review.

## Release recommendation

**Not ready for production release. Ready for the owner's review and for a pilot on a test server with synthetic
data.**

- No confirmed finding of this checkpoint is open, and no open security finding is High. The Checkpoint F box "no
  open high security finding" is met.
- The other three gate boxes need what only the owner can give: the SPEC success criteria that need the target
  server (backup to a second host, the target-server load test, T0 reconciliation), the restore test there, and the
  written release decision.
- Before a real timetable is published, the timetable office must answer Q1–Q21 and confirm D1–D3, and the
  departments should answer the Forma №3 questions.
- Also before release: repeat the exam load test (after `active_days`) and the mixed load test (new resend rule) on
  the target server.
