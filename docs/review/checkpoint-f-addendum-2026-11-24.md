# Checkpoint F addendum (2026-11-24)

## Scope

Work on top of the addendum of 2026-11-23 (`ab28551`, `docs/review/checkpoint-f-addendum-2026-11-23.md`). It was built
in three branches and merged in the order 1, 2, 3 into `integrate-8d5`. The range is `ab28551..80d0aab`; nothing is
pushed.

- **Branch 1: the syllabus audit gaps that need no owner decision** (`0d14aa6`). These come from the audit of
  2026-11-23:
  - A new exam's defaults come from the published syllabus (plan A12, Task 25). `GET /api/courses/{id}/exam-defaults`
    gives the exam component's name, weight and the outcomes it assesses. An empty exam title takes the component's
    name. An exam already set keeps its title and plan.
  - Prerequisites are registry courses kept by code (`{"code"}`). The name is always read from the registry. An unknown
    code, or the course itself, is a translated 400. An older version's free text stays readable, shown in grey.
  - A draft can be copied from a published syllabus (`GET /api/syllabi/{id}/sources`,
    `POST /api/syllabi/{id}/copy`). The source is either the same code in an earlier semester or a course the teacher
    teaches. Contact hours come from this course's Forma №3, and the attendance limit is lowered to today's university
    limit. The source is kept on the new version: `syllabus_versions.source`, migration `0231`.
  - A semester overview (`GET /api/syllabi/overview`, page `/syllabi/overview`) lists the courses by syllabus state,
    with filters and a CSV (BOM, formula-safe cells). It is open to the academic office and the dean's office within
    their scope, and to leadership read-only.
  - The approval queue is paged (50 rows) and makes a constant number of queries per page (AR-11, deferred at
    Checkpoint D). Its answer is now `{items, total, page, pages}`. `tools/queryplan.py` gained a syllabus scenario.
- **Branch 2: timetable builder follow-ups** (`3e0ff28`, `91b0ea2`):
  - OK-1, left open on 2026-11-23: a published version's hours report counts its lessons, so a cancelled lesson
    lowers the hours.
  - The daily job `timetable.health` checks the published version of each open term with `domain.check`. The result is
    stored in `tt_versions.health` (migration `0485`). Each new problem is told once to the university-wide academic
    office.
  - A new run kind, `repair`, drafts from the published version. It keeps the weeks before today plus the notice days.
  - `manage.py timetable-replay --version V` solves a run again from its stored input and seed.
  - The Forma №3 preview offers a department choice per post whose subject two departments teach.
  - The room editor has two new boxes: open to the builder (`rooms.schedulable`) and reserved (`rooms.dedicated`).
- **Branch 3: accessibility of the screens built since Checkpoint F** (`1af60d4`). axe runs at 1280 and 390 px in
  the light and the dark theme. The user menu and the framework picker are checked by keyboard. The contrast and focus
  defects the run found are fixed.

## Method

The same as the addendum of 2026-11-23:
- Three lenses ran on the merged branch (`9d32346`): security, correctness of business rules, and test strength.
  Test strength means single mutants of every new rule, plus test order forward, reversed and shuffled.
- A separate agent tried to refute each finding on a clean copy of the branch, with probes and temporary tests.
- Only confirmed findings were fixed, each with a test that fails without the fix:
  - code fixes: shown failing with `git stash`, or by a mutation tool that removes the fix;
  - test gaps: shown by re-applying the review's mutant;
  - F3's browser check: shown failing without the JS fix.
  Every mutant is killed after the fixes.

## Findings

25 findings were confirmed and all are fixed. None was refuted outright. Two were narrowed, and one was split: S12's
half was refuted.

| Id | Severity | Finding | Fix |
|---|---|---|---|
| SEC-8D5-1 | Low | A teacher could copy the published syllabus of an earlier offering of the same code, taught by another teacher, which `may_read` refused to show them. When the source version had no frozen tags, the source course's working map (unpublished tags) came along. A course without a term listed later terms' syllabi as sources | `51c9ec8`: option (a), which is what `0d14aa6` meant. The author reads the earlier offering that `/sources` offers (`published_for` → `_earlier_offering`), so the read and the copy agree. The working map is copied only when the author may read that course. A course without a term has no earlier offering. **The owner must confirm (a) or ask for (b)**: a `may_read` condition on the copy source |
| F1 | Medium | A repair's publication rewrote every row (20 of 20 updated, 1 really moved), dropped and remade 39 lessons and sent a change notice to all 18 students. A repair places only future weeks, and `publish_plan` compared the full week sets | `80d0aab`: a repair version's plan compares weeks only inside the repair's future mask. An unmoved row keeps its weeks and lessons and sends no notice |
| F2 | Low | A published version's hours report explained missing weeks (before the first publication) as fortnight or block rounding | `80d0aab`: the reason is `lessons_differ` when the lessons do not give what the placements would. A unit of a published version without lessons counts 0 |
| F3 | Low | A faculty-scoped academic office saw the «Bərpa layihəsi hazırla» button, but every press was refused (400, then 404) | `80d0aab`: the page carries `can_repair` (manages and covers the published version's scope). A repair takes the publication's scope, so a scoped caller gets 404, not 400. The Playwright check runs in two roles |
| F4 | Low | A two-letter exam component in the syllabus (`Ək`) made a title-less exam fail with «3–200 simvol» | `51c9ec8`: an exam title may be 2–200 characters, like a component name. The key was renamed with `tools/i18n.py rename` (`a040989`) |
| ORD-1 | Test hygiene | `test_syllabus_registry.py` failed in reverse order: two tests shared the module's course, and one of them published it | `51c9ec8`: the exam-defaults tests make their own courses. The file passes forward, reversed and in 6 shuffled orders |
| MUT-S23 | Test gap (high) | The department head's scope filter on the paged syllabus queue | `51c9ec8` |
| MUT-S16 | Test gap (high) | `may_manage` on `exam-defaults` (another teacher's course: 404) | `51c9ec8` |
| MUT-T05-T06 | Test gap (high) | The scoped view of the daily check (SEC-TT-3): count and problems | `80d0aab` |
| MUT-T09 | Test gap (high) | `_covers_scope` on a repair run (a scoped office starting a university-wide repair) | `80d0aab` |
| MUT-T04 | Test gap | The health notice goes only to the university-wide academic office (no scoped grant) | `80d0aab` |
| MUT-S15 | Test gap | A teacher's own exam title is not replaced by the syllabus name | `51c9ec8` |
| MUT-T17 | Test gap | A repair without a published version is a 409. The refuter narrowed it: the mutant answered 400 with a logged `TypeError`, not 500 | `80d0aab` |
| MUT-T07-T08 | Test gap | A repair's `from_week` (today + notice days) and the 409 past the term's last week | `80d0aab` |
| MUT-T02-T03 | Test gap | `timetable.health` waits while an exam is open and checks open terms only | `80d0aab` |
| MUT-T11-T13 | Test gap | `timetable-replay`: the input's SHA-256, the unplaced comparison and a vanished placement | `80d0aab` |
| MUT-S07 | Test gap | A copied attendance limit is lowered to the university limit | `51c9ec8` |
| MUT-S09 | Test gap | A copy drops a prerequisite that names the target course | `51c9ec8` |
| MUT-S26 | Test gap | The queue compares with the latest published version | `51c9ec8` |
| MUT-S19-S22 | Test gap | The overview's counts ignore the state filter. The overview's department list follows the caller's scope | `51c9ec8` |
| MUT-S10 | Test gap (low) | A parallel offering in the same semester is not a copy source | `51c9ec8` |
| MUT-S14 | Test gap (low) | `copy_from`'s 403 when the teacher may read but not write the course | `51c9ec8` |
| MUT-S01-S05 | Test gap (low) | Duplicate prerequisites are dropped. The course's own name stays text in the first draft | `51c9ec8` |
| MUT-T16 | Test gap (low) | A published version's hours count only lessons inside the term's dates | `80d0aab` |
| MUT-I06 | Test gap (low) | The department choice is offered only for a subject two departments teach | `8c42851` |

Narrowed or refuted:
- **SEC-8D5-1** is a contradiction between two rules (the read rule refused, the copy rule allowed), not a code slip:
  `0d14aa6` and its test meant the copy. What could leak was only the published version, which that course's students
  already see, with one exception: the working-map fallback carried unpublished tags.
- **F2:** the hours are right and only the reason is wrong. Units 17, 18 and 21 showed «holidays», which hid the same
  loss under another name.
- **MUT-T17:** the mutant answered 400 with a logged exception, not 500.
- **MUT-S12 refuted:** `test_syllabus_registry_pages.py::test_a_draft_is_copied_from_the_course_s_earlier_offering_and_names_its_source`
  kills the mutant (the course itself as its own source) deterministically. Only S10 was kept.

The security lens checked these too and found nothing more:
- the overview's roles and scope, its unknown term (404) and its CSV formula guard;
- `exam-defaults` for other roles;
- the department choice of the import (admin only; a wrong map, list, row or bool is 400);
- the repair run's permission and the health view's scope;
- the room boxes' roles and types.

No new UI path uses `raw()` or `innerHTML`, and the server log had 0 tracebacks.

## Measured

**Suite.** 2 138 tests are collected. The last full run on the fixed branch (`80d0aab`): `2111 passed, 27 skipped,
4 warnings in 562.04s (0:09:22)`. The 27 skipped are the 25 axe checks (axe-core is not installed in the suite's
environment) and 2 SEB vectors that wait for the owner's files. Other checks:
- `ruff check .` and `mypy` (138 files) are clean, and `node --check` passes on `frontend/js`.
- i18n `stats` is 100 % for en and ru: ui 2 930, server 1 359, content 1 489. `lint` stays at 72.
- `tests/security/matrix.json` has 332 routes, 4 of them new (exam-defaults, sources, copy, overview), with no other
  change.
- Two migrations: `0231` (syllabus source, `courses(code)` index) and `0485` (`tt_versions.health`).

Before the fixes, on the merged branch (`9d32346`):
- The first full run had 1 failure: `test_concurrency.py::test_the_load_tool_runs` (two 500s on `PUT /api/me/prefs`
  under load, with the query-plan tool running beside it, p99 1 056 ms against the TX guard's 1 s). It passed alone
  (13 passed), and the clean re-run was `2091 passed, 27 skipped`. No branch touches that route.
- `tools/queryplan.py --dataset university`: exit 0. The only scans are in the leader scenario, which reports scans and
  does not fail on them.
- The syllabus scenario (2 100 versions, 2 507 courses) has no full scan. The queue's query count per page is
  constant; an N+1 mutant gave 54/14/54 queries and failed the test.

**Accessibility (axe-core, WCAG 2.2 AA tags; `tests/integration/test_a11y.py` with `npm ci --prefix tests/e2e`).**
- 11 screens built since Checkpoint F were checked:
  - the sign-in page with every role card;
  - the syllabus editor with the framework picker open;
  - the reviewer's window and the print view;
  - the framework coverage report and the hours report;
  - the builder's build page, draft version, department, availability and faculty pages.
- Each screen ran at 1 280 and 390 px, in light and dark: 44 runs. No violation of any impact is allowed, and no rule
  is excluded (`EXCLUDED` is empty). The 10 core pages keep the earlier bar: desktop and phone, no serious or critical
  violation.
- Before the fixes the run found:
  - dark-theme text contrast: `--faint` 4.13:1, `--amber` 4.33:1, `--red` 3.64:1, `.b-blue` 2.18:1, and green text on
    `--green-50` 4.47:1. New tokens: `#848eb0`, `#ce9335`, `#e07074` and `#09211a`. `.b-blue` and the excused
    attendance cell now use `--link`.
  - five tables that scroll at 390 px with nothing focusable: the reviewer's three, the syllabus queue and the hours
    table. They now have `tabindex="0"`, `role="region"` and the section's name.
  - Escape from a top-bar menu left focus on `body`. It now returns to the button.
- After the fixes: `test_a11y.py` 25 passed. That is 10 pages, 11 screens, and the keyboard checks of the menu and
  the picker in two themes.
- On the merged branch, the 9 browser wrappers (Playwright and axe) gave 72 passed in 4 min 38 s.

## Not verified

- Prod mode and `--workers N` were not tried for any of the new routes, the health job or the repair.
- The axe run and the 9 browser wrappers were not repeated after the fix commits. F3's changed button was checked by its
  own Playwright test only, at 1 400 px in the light theme.
- The dark-theme token change affects every page. The 10 core pages are checked by axe only in the light theme.
  `.btn-success` (white on green) is below 4.5:1 in the dark theme and was not changed, because no checked screen has
  it.
- The print view has no dark theme, so its "dark" run repeats the light one. The keyboard checks ran at 1 280 px only.
- The builder draft in the a11y fixture is written straight into the tables, not by a solve run.
- F1 was checked only in the test world (`chain`), not on the departments' real files. After a repair, a moved row's
  weeks are still future weeks only (for example `10-15`). This is the solver's design and was not changed.
- The health check and the repair were not timed at university scale. The overview's search and department filter run
  in Python over a semester's courses and were checked only by query plan.
- `queryplan --dataset university` was not re-run after the fix commits.
- The full suite has not run on Windows or in CI for this range.

## Remaining risk

- **SEC-8D5-1** runs on option (a) until the owner confirms it.
- The queue's answer changed from a list to `{items, total, page, pages}`. An outside client of that route would break.
  None is known.
- Free-text prerequisites are still accepted in new versions, and enrolment is not blocked by a prerequisite.
- A copy replaces the target course's whole framework map with the source's.
- The prerequisite search uses `/api/directory/courses`, which gives a staff member with `directory.read` the full
  course row.
- `timetable-replay` reports "different" for a run whose time budget stopped the first placement; the code notes it.
- A health notice is one per day with the count of new problems; the list itself is on the page.
- The department choice of a Forma №3 import is the administrator's, since only that role imports on screen.
- Checkpoint F's release recommendation is unchanged: not ready for production; ready for the owner's review and a
  pilot on a test server with synthetic data.

## Owner-dependent gaps still open

- **SEC-8D5-1:** confirm (a), the author reads an earlier offering's published syllabus, or choose (b), a copy source
  must pass `may_read`.
- **Plan A12:** the exam's duration, form and question count per outcome are not in the syllabus, and exam questions
  carry no outcome. The outcome → question → outcome chain needs a decision on whether the syllabus holds them.
- Whether a free-text prerequisite should be refused, and whether a prerequisite should block enrolment.
- Q1 (are holidays made up), and the order of the timetable's soft rules (the timetable office): both from the
  2026-11-23 addendum.
- The demo specialty's department binding and the first draft's outcome links, from the syllabus acceptance of
  2026-11-23.
- Task 44 (release) and Checkpoint F's gate:
  - the target server, the restore test and the `university` load test;
  - the first faculty's T0 export and its reconciliation;
  - the SEB reference files;
  - the owner's written release decision.
