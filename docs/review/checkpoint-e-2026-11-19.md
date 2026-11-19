# Checkpoint E review (2026-11-19)

## Scope and method

Faza 5 was reviewed at `777682f`: Tasks 31–35 and 37 (rooms and routes in the campus assistant, the knowledge base
and handoff, the course forum, office hours, clubs and channels, the integration hub). Task 46 (e-service honesty) was
built in parallel and merged later (`4c63b4a`); it had its own code and security review (section "Task 46").

Seven reviewers ran on `777682f`:
- `ecc:code-reviewer`
- `ecc:security-reviewer`
- `ecc:silent-failure-hunter`
- `ecc:python-reviewer`
- `agent-skills:code-reviewer`
- `agent-skills:security-auditor`
- `agent-skills:test-engineer`

An architecture/performance pass and a threat model were folded in. Their ids are `AR-` and `TM-`.

How the findings were handled:
- Duplicates were merged. The claims were split into seven areas: A forum, B clubs, C webhooks, D exports and API keys,
  E office hours, F assistant and knowledge base, T tests.
- For each area a separate agent tried to refute the claims against `777682f`, with probes on temporary databases,
  real HTTP servers, browser runs for the club page and mutation runs of the whole suite for T. No repository file
  was changed during refutation.
- Only confirmed parts were fixed, each with a regression test that fails on the code before the fix (checked by
  putting the old file back and running the test).

Fix commits:
- `c87c374`: area E.
- `582c3cd`: areas A and C, and NEW-B1.
- `52a9490`: area B and the owed tests of area T.
- `0d7ead9`: areas F and D.
- `e29ec1f`: a lint follow-up.
- `de5fc7b`: the Task 46 review and the security review's OLD-1/OLD-2.

## Counts

| Area | Claims | Confirmed | Partial | Refuted |
|---|---|---|---|---|
| A forum | 11 | 10 | 1 | 0 |
| B clubs | 8 + NEW-B1 | 7 | 2 | 0 |
| C webhooks | 10 | 6 | 4 | 0 |
| D exports, keys | 14 | 11 | 2 | 1 (CR-E9) |
| E office hours | 6 | 6 | 0 | 0 |
| F assistant, KB | 12 | 8 | 2 | 2 (SF-E12, T-E11 as a code claim) |
| T tests | 21 | 18 | 2 | 1 (T-E15) |
| **Total** | **83** | **66** | **13** | **4** |

## A. Course forum (`582c3cd`, tests in `tests/integration/test_qa.py`, `tests/migration/test_schema_migrations.py`)

| Id | Severity | Finding | Fix |
|---|---|---|---|
| SEC-E1 / TM-E1 | Medium (blocks the pilot) | A question forwarded from the tutor became a course-wide topic with the author's name; the 3 seeded forwards too | `0331`: `teacher_questions.private`; forwards are read only by the author and the course's teachers; existing rows without an audited forum post become private (fail closed) |
| SEC-E3 | Medium | The tutor promises an anonymous forward hides the name from the teacher; the forum showed it | A private anonymous topic shows "Anonim tələbə" to the teacher too; the old assertion in `test_qa.py` is flipped |
| SEC-E2 / CR-E1 / PY-E4 / TM-E2 / T-E2 | Medium | The anonymous author's own reply carried their name | The reply of the topic's anonymous author keeps the topic's anonymity |
| CR-E6 | Low | After the FAQ material was deleted the topic still said FAQ; turning it off created an untitled material | Deleting a material clears its topics' FAQ flag; `_faq_off` never creates the material |
| CR-E7 / AR-E12 | Low | The old answer route changed the accepted reply but not the FAQ text | `qa.service.answer`; one notice instead of two |
| TM-E5 | Low (partial) | An accepted student reply could become the FAQ the tutor cites as the course's own | Only a teacher's answer reaches the FAQ |
| SF-E6 | Low | The tutor's refusal was saved as the AI draft | Not saved; the page says no source was found |
| TM-E13 | Low | A dean's office of another faculty saw and resolved forum reports, anonymous authors included | Queue and resolve limited to the office's faculties (`scope_sql`, `serves`) |
| AR-E4 | Medium | The teacher's question badge (every 30 s) scanned `teacher_questions` | `idx_courses_teacher` |
| AR-E8 (forum part) | Low | `qa/service.py` imported `learning.repo`; `r_learning` imported `qa.repo` | Through `learning.service` and `qa.service` |
| AR-E14 | Nit | No paging (`LIMIT 500`) | Open |

## B. Clubs and channels (`52a9490`, tests in `test_community.py`, `test_clubs_page.py` + `tests/e2e/clubs.js`)

| Id | Severity | Finding | Fix |
|---|---|---|---|
| SEC-E5 / CR-E2 / TM-E3 / PY-E8 | Medium | Leave deleted the row: leave + join cleared a removal and a mute; 25 cycles = 25 notices to the leader | The row stays `left` with its mute; a removal is never undone; join asks again; leave audited |
| TM-E4 / SEC-E9 (club part) | Medium | The leader saw the reporter, closed reports on their own messages and could remove the reporter | No reporter name and no reports on one's own messages for a leader; "keep" on one's own message → 403; those reports stay in the office's queue |
| TM-E17 | Low | 60 reports of one message, 60 proposals | One open report per person and message; `club_ask` 10 per 10 minutes on propose, join and report |
| SF-E8 / AR-E6 | Medium | Chat messages under Announcements, duplicates, a second polling loop, hidden tabs polling, a hidden message staying on screen | Generation token, no poll while hidden, `hidden` ids in the poll answer (browser tests: old code 6 GETs in 9 s, new 3) |
| SF-E7 | Low (partial) | Failing polls were silent | A status line after two failures, cleared on success |
| SF-E9 | Low | A failing pending list showed an empty card | Only 403 is "nothing to show"; anything else is an error |
| SF-E13 / PY-E9 | Info (partial) | `"abc"` rolled back the purge job; `-1` deleted every message | A setting that is not an int ≥ 1 keeps 180 days |
| NEW-B1 | Low | `empty()` got the text as its icon in `community.js`, `qa.js`, `apps.js` | Icon passed; the text shows |

## C. Webhooks (`582c3cd`, tests in `test_webhooks.py`)

| Id | Severity | Finding | Fix |
|---|---|---|---|
| SF-E1 / PY-E1 / SEC-E7 | High | An exception outside `OSError` (BadStatusLine, InvalidURL) stopped every run; the queue behind it starved | Any exception fails only its own delivery |
| SF-E2 | Medium | 301/302/303 were followed as a GET with the signature header and logged as sent | No redirects; a 3xx is a failure |
| SEC-E6 / TM-E6 | Low-Medium | Private and metadata addresses accepted, also in prod | Prod: https only, and every address the host resolves to must be public, checked when each delivery goes |
| PY-E5 | Low (partial) | Bad ports, spaces and `user:password` accepted; credentials stored and audited | Refused at `hook_input` and at send |
| AR-E3 / TM-E7 | Medium (partial) | A hanging or dripping receiver held the run (34 s for one delivery) | 10 s connect, 15 s per POST overall; a webhook that times out waits for the next run |
| AR-E2 | Low-Medium | `barred_scan` computed under the write lock | Computes first; skips when no webhook listens (SF-E3) |
| AR-E7 / TM-E12 | Low | Deliveries never purged (`student_no` in payloads) | Finished deliveries purged after 90 days |
| SF-E15 | Low | An exhausted delivery told nobody | The webhook's creator is told |

## D. Exports and API keys (`0d7ead9`, tests in `test_integration_checkpoint_e.py`)

| Id | Severity | Finding | Fix |
|---|---|---|---|
| CR-E3 / SF-E4 | Medium | A row written in the pull's own second was never returned | `>=` (the pull's second comes again) |
| AR-E1 | Medium | 1.22 M marks: 13.7 s, 102 MB body, 1.73 GB peak inside a regular handler slot | Export routes in the slow slots; grades/attendance over HTTP capped at 300 000 rows with the way round; the command has no cap |
| PY-E2 | Low (partial) | `0001-01-01T00:00+04:00` overflowed inside the export | `moment` refuses years outside 1900–2999 |
| SF-E11 | Low | A revoked key still in use left no trace | `api_call_revoked` audit row; other 401s are not audited (no anonymous flooding) |
| AR-E9 | Low | A RateLimiter built per call (3 commits per call) | One per limit value |
| AR-E13 | Low | An empty export read the whole link table | Early return |
| SF-E5 | Low-Medium (documented) | OneRoster leaves out enrolments with no attended class, silently | Audit detail "enrolments left out N" |
| SF-E14 / TM-E15 | Low | `--out` failed after the audit commit; file 0644 | File opened first (no audit on a bad path); 0600 |
| (side finding) | Low | A source id shared by two rows was checked per export, so one person got different ids in different files | Checked over all links |
| CR-E8 / SEC-E8 / TM-E11 | Low | Drafts are exported through a key | By design (`status` column); **owner decision** |
| TM-E8 | Low | Keys have no expiry or address limit | Open |
| PY-E3 | Low | Python 3.10 refuses some ISO forms 3.11+ reads (`+0400`, `.5`) | Open (no wrong data; prod runs 3.12) |
| AR-E11 | Low | SQL in `tokens.py` and `webhooks.py`, not `repo.py` | Open (the layer test checks service/routes/domain only) |
| PY-E6 | Nit (partial) | A corrupt stored `order_date` becomes a raw 400 | Open |
| CR-E9 | — | `/api/v1` without Cache-Control | Refuted: `web.py` adds `no-store` |

## E. Office hours (`c87c374`, tests in `test_office_hours.py`)

| Id | Severity | Finding | Fix |
|---|---|---|---|
| TM-E10 | Medium | The teacher's iCal feed (read by Google/Outlook) named the student and carried the topic | "Qəbul saatı" only; the student's own feed keeps them |
| TM-E9 | Low | Parallel requests passed the cap of two bookings | Write lock before the count; deterministic race test |
| CR-E4 | Low | Ending a range cancelled meetings that already happened; past meetings counted toward the cap | Only future meetings |
| CR-E5 | Low | Overlapping ranges allowed double booking | Refused |
| AR-E5 | Low | A person's bookings scanned `office_bookings` | `0341` index |
| PY-E11 (part) | Nit | `+1:00` and non-ASCII digits accepted as times | Strict `HH:MM` |

## F. Assistant and knowledge base (`0d7ead9`, tests in `test_kb_admin.py`, `test_assistant_rooms.py`, `test_layers.py`)

| Id | Severity | Finding | Fix |
|---|---|---|---|
| SEC-E4 | Low | `/api/source/kb/{id}` served draft and archived articles to anyone signed in | Published only |
| PY-E3 (KB) | Low (partial) | `20261118` stored raw as a review date | Exactly `YYYY-MM-DD` |
| SF-E10 | Low | Roles other than student/teacher got "no lessons" with no lookup | Anyone but a student reads their own teaching lessons |
| PY-E8 | Low | "EK-121" matched EK-12 too | Longest code first |
| TM-E16 / SEC-E9 | Low | A handoff carried a phone number and FIN from days before | Same day only |
| SF-E15 (chat) | Low | `İT-214`, `ƏK-101`, `EK.101` failed the link pattern; a button with no target | Unicode pattern; nothing drawn without a target |
| TM-E14 | Low | The apps audit said only "2 tiles" | The saved addresses are in the audit |
| AR-E8 | Low | 5 cross-module `repo` imports | Pass-throughs in the providers' services; `test_layers.py` refuses new ones (it caught one in Task 46, fixed before its commit) |
| PY-E11 | Nit (partial) | `splitlines()` broke a U+2028 label; an `assert` in the seed | `newline=""`; `RuntimeError` |
| AR-E10 | Low (optional) | Import cycles through `r_learning` | Open |
| SF-E12 | — | Handoff notifies nobody | Refuted |
| T-E11 (code) | — | Every tile to every role | Refuted (the missing test is real and was added) |

## T. Tests (`52a9490`)

18 of the 21 test findings were confirmed. 17 surviving mutants survived the whole suite at once (1494 passed). The
refuter's tests kill each of them and were added:
- T-E1: a teacher of another course.
- T-E3: a second faculty in the status change list.
- T-E4: order and effective dates differ.
- T-E5: a requester gets 403.
- T-E6: a hidden topic.
- T-E7: exam.released is sent once.
- T-E8: deactivation.
- T-E9: the end of office hours.
- T-E10: the reminder job run twice.
- T-E11: the apps page.
- T-E13: export audit by user.
- T-E14: a 179-day-old message stays.
- T-E16: key limit bounds.
- T-E17: the secret's value.
- T-E19: a bare assistant answer gets the handoff.

T-E2 was a live bug (area A). T-E12's barrier version was not added: area E's lock makes the race test deterministic
already. T-E15 was refuted (the route matrix pins `kb.manage`). T-E18 and T-E19 are partial, T-E20 is doc-only and T-E21
is latent (it bites only if the test anchor moves to a Saturday).

## Task 46

Two reviewers ran on `4c63b4a`: `agent-skills:code-reviewer` (TE46-) and `ecc:security-reviewer` (SR46-). The
Faza 5 security review added OLD-1 and OLD-2. A separate agent tried to refute all of them, with probes; the races were
widened with a barrier in `_req_for`.

Result: 11 confirmed, 1 partial (SR46-3), 2 refuted (SR46-2, TE46-6). Fixes are in `de5fc7b`; tests
are in `test_service_honesty.py`, `test_qa.py` and `test_schema_migrations.py`.

| Id | Severity | Finding | Fix |
|---|---|---|---|
| TE46-1 | Required | Two approves at once both passed: step 0 → 2, the department head's step skipped (a double click was enough) | The request's status and step are read under the write lock (`_lock`, `BEGIN IMMEDIATE`) in action, resubmit and cancel; the race test fails without it |
| TE46-2 | Required | Two issues at once: two QR documents (and two status orders) for one request; reject + issue left a rejected request with a valid document | Same lock |
| SR46-1 | Medium | A student with a staff grant approved and issued their own certificate, excused their own absences | 403 on one's own request |
| TE46-3 | Required | exam_reschedule's department-head step had nobody in the demo (and in prod for a course with no head): stuck for good, nobody told | Approve refuses (409) when nobody holds the next step; the current role can still return or reject |
| OLD-1 | Medium | `/api/teacher/questions` (and the teacher's home) gave `student_id` with "Anonim tələbə" (older code; it undid SEC-E3) | The id is dropped for an anonymous asker |
| TE46-4 | Required (tests) | 8 of 9 mutants of the scope and notice rules survived | Tests for a department head of another course, the academic office's attachment, and every notice (new, resubmitted, message, overdue) going to the step's role; a mutant of `covers` now fails |
| TE46-5 | Low | A demo database seeded before Task 46 had no academic office: certificates stuck at step 0 | `0462`: the demo's dean's office also gets the academic office (only where demo logins exist) |
| TE46-7 | Low | In prod with every type closed, the assistant still offered a "sərbəst ərizə" | Another text when it is closed (the home page's quick links remain: open) |
| TE46-8 | Low | An excuse whose absences were corrected to present meanwhile still said "excused" to the student and the teachers | Only the lessons actually excused count; none: the factual template, no notice |
| TE46-9 | Low | The overdue reminder was once per request, so a later step's role never heard of it | Once per threshold and step |
| OLD-2 | Low | The SLA reminder linked to `/office/requests/{id}`, a page that does not exist (since Task 36) | `/office/request/{id}` |
| SR46-3 | Low (partial, latent) | A step role reads the request's attachments whatever the current step | A content test: a type that promises only the dean's office sees its documents has only office steps |
| SR46-2 | — | The student sees staff names in the history | Refuted: acceptance criterion 2 asks for it |
| TE46-6 | — | A closed type's returned request can still be resubmitted | Refuted: in-flight requests must finish (the spec scopes "closed" to the offer) |

## Security review (security-review skill, `afbfeae..4c63b4a`)

The security-review skill ran over `afbfeae..4c63b4a` (Tasks 31–35, 37 and the Checkpoint E fixes; Task 46 got a
lighter pass because its own security review ran in parallel). Bar: confidence ≥ 0.8, High or Medium, new in this range.

**Result: no finding reaches the bar.** What held, among others:
- **Key routes.** A key route reads only the Bearer token and returns before the cookie path. An admin cookie on
  `/api/v1/grades` gets 401.
- **Admin-only routes.** Webhooks, exports, apps and keys are admin only. The webhook URL is admin-controlled and has
  a public-address check and no redirects.
- **Forum.** Every forum handler that takes an id has an object check. Anonymity and private topics hold in
  `/api/qa*`.
- **Clubs.** Membership is checked on every channel route.
- **Office hours.** Bookings stay with the two parties.
- **Escaping.** `/r/{code}` escapes everything it prints. The new frontend uses the escaping template and `md()`.
- **Exports.** CSV cells are protected against formula injection.

One **older** leak (unchanged since `afbfeae`) undercuts SEC-E3: `GET /api/teacher/questions` (and `/api/teacher/home`,
which uses it) returns `tq.*` with `student_id` for anonymous topics, private forwards included. The teacher sees
"Anonim tələbə" and the real id. It went to the Task 46 refuter as OLD-1 (below).

## Checkpoint E criteria

- Assistant evaluation set: 48/50 = 96% with a source or a handoff (≥ 90% required); 0 bare answers.
- Every new route is in `tests/security/matrix.json` (288 routes).
- Prod offers only the request types the administrator opened (`test_service_honesty.py`). `manage.py jobs status` on a
  fresh database shows a last successful run for all 8 periodic jobs.
- Review flow done; the owner's review remains.

## Open items and owner decisions

- CR-E8: drafts in the key exports (by design today).
- Task 46: a role with no step in a type gets 404 on its requests, not 403 (no existence leak). The acceptance text says
  403 for every other role.
- Task 46: certificates and transcripts moved to the academic office; the demo's Nigar has an academic-office grant.
- Task 46: individual_plan's outcome text still says the plan is "added to your profile".
- Task 46: the home page's quick links still lead to a closed type in prod ("Xidmət tapılmadı"); the demo has no
  department head, so its exam_reschedule stops at the office (409) until the administrator grants one.
- Open low items: AR-E14, TM-E8, PY-E3 (since), AR-E11, PY-E6, AR-E10, and the off-topic draft scoring (area A side
  finding).
- From earlier checkpoints: T24 (the NICE file's host is blocked by the proxy); T28 (the owner's reference .seb file and
  a manual SEB 3.x test); the real route CSVs from floor plans; the 10-day deadline against Decree No. 225.
