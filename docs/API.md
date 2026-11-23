# HTTP API

Zəka exposes a JSON API under `/api/` and a few server-rendered pages. The single-page application in `frontend/` (served under `/static/`) is the only client in this repository; the API is not versioned and has no stability guarantee across demo releases. Everything below is taken from the route modules in `backend/zeka/legacy/r_*.py` and the HTTP layer in `backend/zeka/core/`; the examples are real responses from a server started on a fresh demo database, shortened where marked with `…`.

- [Conventions](#conventions)
- [Authentication and session](#authentication-and-session)
- [Profile, notifications, search and files](#profile-notifications-search-and-files)
- [Courses, schedule, attendance and grades](#courses-schedule-attendance-and-grades)
- [AI tutor and campus assistant](#ai-tutor-and-campus-assistant)
- [Tests and Test Studio](#tests-and-test-studio)
- [Teacher tools](#teacher-tools)
- [E-services and documents](#e-services-and-documents)
- [News and events](#news-and-events)
- [AI Academy, tools and syllabus](#ai-academy-tools-and-syllabus)
- [Support desk and feedback](#support-desk-and-feedback)
- [Analytics and administration](#analytics-and-administration)
- [Zəka Radar](#zəka-radar)
- [Public endpoints](#public-endpoints)
- [Server-rendered pages](#server-rendered-pages)
- [Endpoint index](#endpoint-index)

## Conventions

### Transport

- Base URL: the server's own origin, for example `http://127.0.0.1:5070`. The API and the application share one origin; no CORS headers are sent.
- Request bodies are JSON objects. `POST`, `PUT` and `DELETE` requests that carry a body must send `Content-Type: application/json`, otherwise the server answers `415`. A body that is not valid JSON or not a JSON object, or that uses `NaN` or `Infinity`, is rejected with `400`. The maximum body size is 16 MB.
- `POST`, `PUT` and `DELETE` requests that a browser marks as cross-site are refused with `403`: the server checks `Sec-Fetch-Site` (`same-origin` and `none` pass) and, when the browser does not send it, compares `Origin` with the `Host` header and the public URL. Clients that send neither header, such as scripts, are not affected.
- `Transfer-Encoding` (chunked bodies) is not supported (`501`); a non-numeric or conflicting `Content-Length` is a `400`. When a handler does not read a request body, or the request is refused before its body is read, the server closes the connection.
- Responses are `application/json; charset=utf-8` unless stated otherwise, with `Cache-Control: no-store` unless the endpoint sets its own. `HEAD` is answered like `GET` without a body.
- Path parameters shown as `{id}` are integers. Query parameters are plain strings.
- Timestamps are ISO 8601 in the server's local time with second precision and no offset, for example `2026-11-05T05:58:04`. Dates are `YYYY-MM-DD`.
- File content is sent inside JSON as Base64 in a `content_b64` field; there are no multipart endpoints.

### Language

Send `X-Lang: az`, `en` or `ru` (or the query parameter `lang`). The default is `az`. The server translates every response before sending it:

- Interface strings, catalogue entries, error messages and notification texts are returned in the requested language.
- Codes such as roles, statuses, kinds, categories and keys are never translated.
- User-written text (chat messages, questions, ticket text), course material headings and quotations, and the titles of external references stay as written.

Form values for options may be sent either in Azerbaijani or in the translated label shown to the user; the server maps them back to the canonical Azerbaijani value before storing.

### Errors

Errors have one shape:

```json
{"error": "Course not found"}
```

| Status | Meaning in this API |
|---|---|
| `400` | Validation failed: a required field is missing, a value is out of range or of the wrong JSON type, a file is rejected, the body is not a JSON object |
| `401` | No valid session for an endpoint that needs one, including a session older than its lifetime |
| `403` | The session's role is not allowed, the object belongs to someone else, the demo access code is wrong, or the request came from another site |
| `404` | Unknown path or object, or a demo-only route in prod mode; also returned instead of `403` for requests, document links, support tickets and support plans that belong to another user |
| `405` | The path exists but not for this method |
| `409` | The action conflicts with the object's state (attempt limit reached, request already closed, event full, an open support plan already exists) |
| `413` | Body larger than 16 MB; also a course material over 10 MB or a syllabus over 200,000 characters |
| `415` | Body sent without `Content-Type: application/json` |
| `422` | Test Studio could not generate questions from the material, or Radar found no plan step for the student |
| `423` | The teacher has locked the tutor for this course (students only) |
| `429` | A rate limit is reached (see below), or the student's daily message limit for the tutor and campus assistant |
| `501` | The request uses `Transfer-Encoding` |
| `500` | Unhandled server error; the traceback is written to `logs/errors.log` |

A field of the wrong JSON type answers `400` with "Invalid value: <field>" (for example a list where text is expected). Malformed input that a handler does not check itself is also answered with `400`, not `500`.

### Rate limits

Counters are kept per client address or per user in fixed windows; over the limit the server answers `429`.

| Limit | Per | Endpoints |
|---|---|---|
| 30 per minute | client address | `POST /api/auth/demo`, `GET /demo/login` |
| 10 wrong access codes per 10 minutes | client address | The same; afterwards logins without a session are refused until the window ends |
| 30 per minute | user | `POST /api/tutor/{cid}/ask`, `POST /api/campus/ask`, `POST /api/studio/generate` |
| 40 per 10 minutes | user | `POST /api/files`, `POST /api/courses/{id}/materials` |
| 30 per minute | user | `GET /api/files/{id}/preview` |
| 120 per minute | user | `POST /api/files/{id}/link`, `POST /api/documents/{id}/link`, `POST /api/syllabus/{cid}/link` |
| 60 per minute | client address | `GET /verify/{code}` |
| 100 wrong passwords per 15 minutes | client address | `POST /api/auth/login`: any account, checked before the password is hashed (generous, because a campus network puts many students behind one address) |
| 30 per minute | client address | `GET /api/auth/sso/start`, `POST /api/auth/sso/link` |

The client address is the connection's peer address; when the server runs with `ZEKA_PROXY_HOPS=N`, it is the N-th address from the right of `X-Forwarded-For`.

### Roles

| Code | Who |
|---|---|
| `student` | Student |
| `teacher` | Teacher |
| `office` | Dean's office and registrar |
| `leader` | Leadership (rector's office) |
| `admin` | Platform administrator |

In the tables below, "any" means any signed-in user. "Staff" means `office`, `leader` and `admin`.

## Authentication and session

Demo login is by role and has no password. It exists only in demo mode (`ZEKA_MODE=demo`, the default); with `ZEKA_MODE=prod` the routes `POST /api/auth/demo`, `GET /demo/login`, `GET /api/demo/storyline` and `POST /api/admin/reset` answer `404`, and accounts sign in with a password (`POST /api/auth/login`, below). `GET /api/bootstrap` reports the mode as `app.mode`. When the server runs with `ZEKA_ACCESS_CODE`, a visitor must send that shared code to sign in; `GET /api/bootstrap` reports this as `app.access_required`. The session id travels only in the `HttpOnly` cookie `zeka_sid` (never in a response body; the `X-Session` header is ignored since Task 11), and the database keeps only its SHA-256. A session ends after an idle time and an absolute age that depend on the role: staff 1 hour idle and 24 hours in all, students 8 hours idle and 30 days (the setting `session_limits` overrides them); after that the server answers `401`. Signing in, a password change and, later, the second factor give the session a new id. Logout deletes the session; `GET /api/me/sessions` lists one's own sessions, which can be ended one by one or all but the current one.

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/bootstrap` | public | Application settings, the current user if signed in, home path and unread count |
| `POST` | `/api/auth/demo` | public | Sign in as the demo user of a role |
| `GET` | `/demo/login` | public | Sign in by link and redirect |
| `POST` | `/api/auth/logout` | any | Delete the session and expire the cookie |
| `POST` | `/api/auth/login` | public | Sign in with a user name or e-mail and a password (Task 10) |
| `POST` | `/api/auth/password` | any | Change one's own password; the only route open to a temporary password |
| `POST` | `/api/admin/users/{id}/temp-password` | admin | Issue a one-time password; the account must change it |
| `POST` | `/api/admin/users/{id}/unlock` | admin | Lift a lock or block, with a reason (audited) |
| `POST` | `/api/auth/mfa/verify` | pending | Second step of a sign-in: a 6-digit TOTP code or a recovery code |
| `POST` | `/api/auth/mfa/enroll` | any | New TOTP secret with its `otpauth://` URI and QR (SVG); staff must enrol before anything else |
| `POST` | `/api/auth/mfa/confirm` | any | Confirm the secret with a code; returns 10 one-time recovery codes once |
| `POST` | `/api/auth/mfa/disable` | student | Turn the second factor off (staff cannot) |
| `POST` | `/api/admin/users/{id}/mfa-reset` | admin | Lost device: clear the second factor and end the account's sessions, with a reason |
| `GET` | `/api/auth/sso/start` | public | Single sign-on (Task 14): redirect to the provider with PKCE (S256), `state` and `nonce` |
| `GET` | `/api/auth/sso/callback` | public | The provider's answer: code exchange, ID token and userinfo checks, then a session; redirects to `/` or `/#/login?sso=<reason>` |
| `POST` | `/api/auth/sso/link` | any | Link one's own account: `{"url"}` of the provider; staff only from a password + TOTP session |
| `GET` | `/api/me/sso` | any | One's own provider bindings |
| `GET` | `/api/admin/users/{id}/sso` | admin | A user's provider bindings |
| `POST` | `/api/admin/users/{id}/sso` | admin | Bind the configured provider's `sub` to the account (audited) |
| `DELETE` | `/api/admin/users/{id}/sso/{iid}` | admin | Remove a binding (audited) |
| `GET` | `/api/me/sessions` | any | One's own sessions: created, last active, address, browser, current |
| `GET` | `/api/me/roles` | any | The primary role and every granted role with its scope; the active one |
| `POST` | `/api/me/role` | any | Act in another held role; the session gets a new id (audited) |
| `GET` | `/api/admin/users/{id}/roles` | `roles.grant` | A user's roles |
| `POST` | `/api/admin/users/{id}/roles` | `roles.grant` | Grant a role, optionally scoped to a faculty, department or course (audited) |
| `DELETE` | `/api/admin/users/{id}/roles/{gid}` | `roles.grant` | Revoke a grant; sessions acting in it fall back at once (audited) |
| `GET` | `/api/directory/{entity}` | `directory.read` | `faculties`, `departments`, `specialties`, `groups`, `terms`, `users`, `courses`, `units`: `?q=` search, `?page=` (50 a page), `?active=1/0`, filters such as `?role=`, `?group_id=`, `?term_id=`, `?course_id=`; `users` only for `directory.manage` and never with password or TOTP columns |
| `POST` | `/api/directory/{entity}` | `directory.manage` | Create (validated, unique code, audited); `users` only for `users.manage` |
| `PUT` | `/api/directory/{entity}/{id}` | `directory.manage` | Change (rules checked on the merged row, e.g. teaching ends before the exam session); a changed role ends the account's sessions; one's own role cannot be changed |
| `POST` | `/api/directory/{entity}/{id}/deactivate` | `directory.manage` | Deactivate; there is no delete. A deactivated account cannot sign in and its sessions end; its history stays |
| `POST` | `/api/directory/{entity}/{id}/activate` | `directory.manage` | Activate again |
| `GET` | `/api/directory/units/{id}/groups` | `directory.read` | The groups a teaching unit (lecture, seminar, lab) is for |
| `PUT` | `/api/directory/units/{id}/groups` | `directory.manage` | Replace them: `{"group_ids": [..]}` |
| `GET` | `/api/directory/courses/{id}/enrollments` | `directory.manage` | Enrolments with group (own group when empty), subgroup, `begin_date`, `end_date` |
| `POST` | `/api/directory/courses/{id}/enrollments` | `directory.manage` | Enrol an active student: `{"user_id", "group_id"?, "subgroup"?, "begin_date"?}`; `409` when enrolled |
| `POST` | `/api/directory/courses/{id}/enrollments/{uid}/end` | `directory.manage` | End an enrolment on `{"end_date"}`; nothing is deleted |
| `GET` | `/api/courses/{id}/roster?day=` | teacher (own course), admin, academic_office | The lesson list on a day: enrolments with `begin_date <= day < end_date` of active accounts |
| `GET` | `/api/directory/students/{id}/status` | `students.status.read` | The student's status today and every status order; a dean's office only for its faculty; the read is audited |
| `POST` | `/api/directory/students/{id}/status` | `students.status` | Add a status order (below) |
| `DELETE` | `/api/me/sessions/{id}` | any | End one of one's own sessions (`404` for another person's) |
| `POST` | `/api/me/sessions/end-others` | any | End every session but the current one |
| `POST` | `/api/admin/import` | admin | Bulk import of one file (below); `dry_run` is true unless it is sent as `false` |
| `POST` | `/api/admin/activation-codes` | admin | One-time activation codes for a faculty's students without a password, as CSV, shown once |
| `POST` | `/api/auth/activate` | public | `{"student_no", "code", "password"}`: a student chooses a password with the code and is signed in |
| `GET` | `/api/integration/export/{kind}` | `integration.manage` | A file: `grades`, `attendance`, `oneroster` (zip), `registry`, `status-changes` (Task 37, below), `timetable` (`?term=`, `?version=`; Task 48) |
| `GET` | `/api/integration/status-changes?since=` | `students.status.read` | The "Tələbə-məzun" change list: status orders entered after `since` (below) |
| `POST` | `/api/integration/status-changes/{id}/reported` | `students.status` | Mark an order as entered into "Tələbə-məzun": `reported_at` is set once |
| `GET` | `/api/admin/settings` | admin | The university settings by section (Task 17) |
| `PUT` | `/api/admin/settings/{section}` | admin | `{"value": {...}}`: check and save one section (audited `settings_change`) |
| `GET` | `/r/{code}` | public | The page behind a room's QR code (Task 18): the room, the lesson in progress and the next one; 60 per minute per client address |
| `GET` | `/api/facilities/buildings/{id}/qr` | `directory.manage` | A printable sheet with every active room's QR code (HTML) |
| `POST` | `/api/facilities/link-rooms` | `directory.manage` | Link timetable rows to rooms by their text; report the texts that name no room |
| `GET` | `/api/timetable?term_id=&group_id=&teacher_id=` | `directory.read` | Timetable rows of a term (default: the current one) with unit, teacher, groups, room, weeks and hours (Task 19) |
| `POST` | `/api/timetable` | `timetable.manage` | A row of a teaching unit: `{"unit_id", "weekday", "start", "end", "room", "weeks", "academic_hours"}`; `409` with `conflicts` on a clash |
| `PUT` | `/api/timetable/{id}` | `timetable.manage` | Change a row; its future lessons nobody recorded follow, and their students are told |
| `POST` | `/api/timetable/{id}/deactivate` | `timetable.manage` | Take a row out; its future unrecorded lessons are deleted |
| `POST` | `/api/timetable/generate` | `timetable.manage` | Make the lessons of a term's rows (`{"term_id"}`, default current); idempotent |
| `GET` | `/api/lessons?day=&group_id=&teacher_id=` | `directory.read` | The lessons of one day |
| `POST` | `/api/lessons/{id}/cancel` | `timetable.manage` | `{"reason"}`; `409` once attendance is recorded; the lesson's students are told |
| `POST` | `/api/lessons/{id}/move` | `timetable.manage` | `{"day", "start", "end", "room"?}`; checked for clashes on that day; the students are told |
| `GET` | `/api/timetable/versions/{id}/hours?department_id=&outside=1&offset=&format=csv` | `timetable.prepare` | A builder version's hours report (Task 48): per unit in the caller's scope the Forma №3 hours, the hours its placements yield in the term (holidays and term edges), the difference and whether it is within the tolerance; totals of the listed units; 200 a page; CSV with a BOM. Same scope as the builder (a draft only to `timetable.manage`, an id outside the scope `404`); publication does not wait on it |
| `GET` / `POST` / `DELETE` | `/api/me/calendar` | any | Whether one has a calendar feed / a new secret feed address (shown once; the old one stops) / revoke it |
| `GET` | `/ical/{token}` | public (the token) | The feed as iCalendar (RFC 5545), lessons from 60 days back to 200 ahead; 30 per minute per address |
| `GET` | `/api/journal/lessons?day=` | staff | The user's own lessons (the last two weeks, or one day) with how many marks they have (Task 20) |
| `GET` | `/api/journal/courses/{id}/lessons` | the course's teachers, correctors, readers | The course's lessons up to today |
| `GET` | `/api/journal/lessons/{id}` | the lesson's teacher, the course's teacher, correctors, admin, academic office, leadership | The list with marks and what the user may do |
| `PUT` | `/api/journal/lessons/{id}/attendance` | as above | `{"marks": {"<student id>": "absent" \| "late" \| "present"}, "reason"?}`: everyone else on the list is present |
| `POST` | `/api/journal/lessons/{id}/teacher` | `journal.correct` | A substitute teacher for an upcoming lesson: `{"teacher_id", "reason"}` (audited) |
| `GET` | `/api/journal/courses/{id}/standing` | the course's teachers, correctors, admin, academic office, leadership, dean's office (its faculty) | Each student's planned and missed hours, share and status |
| `PUT` | `/api/journal/openings/{id}` | `journal.correct` | Correct an opening balance with a reason |
| `GET` | `/api/journal/courses/{id}/grades` | the course's teachers, correctors, readers | The grade table: columns, each student's cells (draft or published), attendance component, result, `writable` (Task 21) |
| `PUT` | `/api/journal/courses/{id}/grades` | as above | `{"cells": [{"student_id", "component", "score"}], "reason"?}`; a refused cell answers `400 {"cells": [{"student_id", "component", "reason"}]}` and nothing is written |
| `POST` | `/api/journal/courses/{id}/grades/publish` | as above | Publish the user's drafts; final grades follow |
| `GET` | `/api/journal/courses/{id}/grades/log` | as above | Changes of published scores: who, old, new, reason |
| `GET` | `/api/journal/debts?format=csv` | office (its faculty), academic office, admin, leadership | Final grades that did not pass (academic debts); CSV with formula-safe cells |
| `POST` | `/api/journal/students/{id}/reconcile` | office (its faculty), academic office, admin | Mark the student's history before Zəka as checked (audited) |
| `GET` | `/api/courses/{id}/assignments` | the course's teachers, its enrolled students | Assignments (a student's with their own submission) (Task 22) |
| `POST` | `/api/courses/{id}/assignments` | the course's teachers | `{"title", "body", "due_at": "YYYY-MM-DDTHH:MM", "max_score", "component", "late_rule": "mark" \| "refuse"}` |
| `POST` | `/api/assignments/{id}/submit` | enrolled student | `{"text"?, "file_id"?}` (the student's own file); `409` when late and the rule refuses; again until graded |
| `GET` | `/api/assignments/{id}/submissions` | the course's teachers | Every submission with its file |
| `GET` | `/api/submissions/{id}` | its student, the course's teachers | One submission (an audited read for the teacher) |
| `POST` | `/api/submissions/{id}/grade` | the course's teachers | `{"score", "feedback"?}`; the component's total goes to the grade journal as a draft |
| `GET` | `/api/materials/{id}/file` | the course's students (current version), its teachers (any) | A material's original file as uploaded |
| `POST` | `/api/consent` | any | Record or withdraw a consent per purpose (Task 40, below) |

### Bulk import (Task 16)

`POST /api/admin/import` with `{"kind", "source", "filename", "content_b64", "dry_run", "prefer_source"}`, or
`python backend/manage.py import --kind K --source S --file F [--dry-run] [--prefer source]` for files over the screen's
20 000 rows. Kinds: `users`, `orgs` (faculties and departments), `terms`, `courses`, `classes` (teaching units),
`enrollments` (`role=teacher` sets the unit's teacher; `role=student` enrols in the unit's course with its group,
subgroup, `beginDate`, `endDate`), `timetable`, `rooms` (Task 18: `identifier` is the room code, `number`, `name`,
`building` as a building code, `floor`, `kind`, `capacity`, `accessible`), and `teaching-load` (Forma №3 `.xlsx`,
`docs/forms/forma-3.md`).
Columns are OneRoster 1.2 CSV names or Azerbaijani headings; CSV is UTF-8 with commas, semicolons or tabs; XLSX is read
with the standard library and the Office reader's size and DTD guards. Every row is checked and resolved first; one
refused row and nothing is written (`errors`: row number and reason). A row is linked to its source by `import_links`
(`kind`, `source_system`, `sourcedId`), so a second run of the same file changes nothing. A linked row that Zəka changed
since the import and the file says otherwise is a conflict: it is listed with its row and fields and not overwritten;
`prefer_source` overwrites it and writes `import_overwrite` to the audit log. The write is one `BEGIN IMMEDIATE`
transaction and the report gives `lock_ms`. An import never changes an account whose role is not student or teacher,
and never creates an account from Forma №3 (an unknown teacher, course or group is a conflict).

A `teaching-load` answer also carries `forma3`, the reader's report (Task 47, `docs/forms/forma-3.md`): `layout`, `year`,
`sheets` (class, state, whether imported and why), `posts` (`ref`, teacher or vacancy, `pay`, `status` = `ok` | `blocked` |
`hidden`, `controls` T1–T3, units and hours), `units` (counts of the posts in the department's totals: all, `ready`,
`hourly`, `vacancy`, `joint`, and `refused`, the units the registry cannot place, which `ready` leaves out; and `hidden`,
`outside` for the rest), `excluded` (the posts outside the totals: a hidden
sheet or a block the summary leaves out, with their units, hours and load lines),
`conflicts` and `notes` (cell ref, code, message; at most 500 each, with `conflict_count`, `blocking_count`,
`note_count`), `load` (lines and hours per kind, of the counted posts), `controls` (file and sheet checks, and failed post checks) and
`unclassified`. Units of a blocked or hidden post are never planned; a vacancy unit is written with no teacher
(`vacancy` 1); each unit keeps `pay`, `post_ref` and `anchor`. A file that is not a form is a 400.

### API keys, webhooks and the apps page (Task 37)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` / `POST` | `/api/integration/keys` | `integration.manage` (`admin`) | Keys / a new key `{"name", "scopes": [...], "per_minute"}` (scopes `grades.read`, `attendance.read`, `registry.read`, `status.read`; 1–600 calls a minute); the key (`zk_…`) is in the answer once and kept as its SHA-256 |
| `POST` | `/api/integration/keys/{id}/revoke` | as above | Revoke (audited) |
| `GET` / `POST` | `/api/integration/webhooks` | as above | Webhooks / a new one `{"url", "events"}` (https, or http to this machine outside prod; no user:password, spaces or bad ports; events `grade.published`, `attendance.barred`, `exam.released`); the signing secret is in the answer once |
| `POST` | `/api/integration/webhooks/{id}/deactivate`, `GET …/deliveries` | as above | Switch off; the last 100 deliveries with status, attempts, last HTTP status and error |
| `GET` / `PUT` | `/api/apps` | any / `integration.manage` | The tiles of one's role (the administrator also gets every tile) / save the tiles `{"apps": [{"title", "url" (https), "roles", "icon"?, "note"?}]}` (at most 30) |
| `GET` | `/api/v1/grades`, `/api/v1/attendance`, `/api/v1/status-changes` (`?since=`), `/api/v1/oneroster.zip` | an API key with the route's scope | The exports below, through the same audited `export.run` |

A `/api/v1/` route reads only `Authorization: Bearer <key>` and never a cookie (`401` without a valid key, also to a
signed-in browser); a key reaches no other route. Outside the key's scopes `403` (an `api_call_refused` audit row);
over the key's own limit `429`; every call is an `api_call` audit row and sets `last_used_at`. A webhook delivery is a
`POST` of `{"event", "at", "data"}` with `X-Zeka-Event`, `X-Zeka-Delivery` and `X-Zeka-Signature: t=<unix time>,v1=<hex
HMAC-SHA256(secret, "<t>.<body>")>`; a failure (not 2xx, refused, timed out) waits 1, 2, 4 … minutes (at most 6 h) and is
tried up to 12 times by the periodic job `webhooks.send`; no write transaction is open during the request. Redirects are
not followed (a 3xx is a failure). In prod the address must resolve to public addresses only, checked when each delivery
goes. A POST has 10 s to connect and 15 s in all; a webhook that times out or refuses waits for the next run. Any error
fails only its own delivery. When the last try fails, the webhook's creator is told. Finished deliveries are purged after
90 days. A revoked key still in use is audited (`api_call_revoked`); other `401`s are not.
`grade.published` comes with publishing and with a change of a published score, `exam.released` with a release, and
`attendance.barred` from the job `attendance.barred` (every 15 minutes: courses with marks since its last run; once per
student and course).

### Exports (Task 37)

One export service (`backend/zeka/modules/integration/export.py`) behind the screen and the command:
`GET /api/integration/export/{kind}` (`integration.manage`, a file with `Content-Disposition: attachment`) and
`python backend/manage.py export --kind grades|attendance|oneroster|registry|status-changes|timetable [--since ISO] [--term T] [--version V] [--out FILE]`
(a CSV goes to standard output without `--out`; `oneroster` needs `--out`; the `--out` file is opened before the export
and written 0600). Every export writes `export` to the audit log; a OneRoster export adds how many enrolments it left out.
Over HTTP (the screen and `/api/v1/`) the export routes run in the slow handler slots, and a grades or attendance file
over 300 000 rows is refused (`400`, naming `since` and `manage.py export`); the command has no cap.

- `oneroster`: a zip of `orgs.csv`, `terms.csv`, `users.csv`, `courses.csv`, `classes.csv`, `enrollments.csv` in the
  columns of the import kinds, so the importer reads them back (import them in that order; study groups must exist
  first). A row's `sourcedId` is the id its first import linked it to, else `zeka:<table>:<id>`; an enrolment's is
  derived from its class and person. A source id that two rows share names neither: both get the `zeka:` form, in
  every export alike. `enrollments.csv` lists each student for every teaching unit of the course they
  attend (group and subgroup), with `beginDate`/`endDate`, and each unit's teacher as `role=teacher`. Every row is
  exported, deactivated ones too; users are students and teachers. Limits: an enrolment in a course with no unit the
  student attends is not listed, and a student taking a course with another group only through units of several
  groups comes back with their own group.
- `grades` (`courseSourcedId`, `courseCode`, `userSourcedId`, `identifier`, `component`, `score`, `max`, `status`,
  `source`, `updatedAt`) and `attendance` (`courseSourcedId`, `courseCode`, `userSourcedId`, `identifier`, `lessonId`,
  `lessonDate`, `lessonStart`, `status`, `source`, `markedAt`). With `since` (`?since=` / `--since`, ISO 8601, e.g.
  `2026-12-01T00:00:00+04:00`; without an offset it is Baku time; a year outside 1900–2999 is `400`) only the rows
written or changed at or after that second (so a row written in the second of the last pull comes again, never lost):
  `updated_at` / `marked_at`, compared in the university's wall clock. Drafts are included (`status`). A mark without
  `marked_at` (the demo seed, rows from before Task 20) is never "after". An approved absence excuse stamps the rows it
  excuses.
- `registry`: `?registry=students|users&columns=a,b` (`--registry`, `--columns`), columns from a fixed list
  (students: `student_no`, `full_name`, `patronymic`, `username`, `email`, `group`, `faculty`, `specialty`,
  `admission_year`, `funding`, `form`, `status`; users: `username`, `full_name`, `patronymic`, `role`, `email`,
  `department`, `status`); all of them when none is given; an unknown one is `400` naming the allowed columns.
- `status-changes`: the change list below as CSV.
- `timetable` (Task 48): `--version V` / `?version=` a builder version's placements (draft or published), else
  `--term T` / `?term=` (default: the current term) the term's rows in force, published and hand-written. Columns
  `group`, `subgroup`, `course_code`, `course`, `kind`, `teacher`, `room`, `day` (1 = Monday), `pair`, `start`, `end`,
  `weeks` (`all | odd | even | N[-M],...`), `effective_from` (of the version that published the row; empty for a
  hand-written one); one line per group of the row. An unknown term or version is `400` (exit 2).

**"Tələbə-məzun" change list.** `GET /api/integration/status-changes?since=` gives every status order entered
(`created_at`) after `since`: an order entered late with an earlier effective date is still new to the operator. Each
item has `id`, `student_id`, `student_no`, `full_name`, `grp`, `kind`, `order_no`, `order_date`, `effective_date`,
`created_at`, `deadline` (`order_date` + 10 days), `days_left` (negative when overdue) and `reported_at`; a dean's office
sees its own faculty. `POST /api/integration/status-changes/{id}/reported` sets `reported_at` once (audited
`status_reported`); a second mark changes nothing. Assumption: the 10 days are counted from `order_date`; to be checked
against Decree No. 225 (SPEC Open Questions 17).

### Buildings and rooms (Task 18)

`buildings` and `rooms` are directory entities (`/api/directory/buildings`, `/api/directory/rooms?building_id=`). A room
code (2–30 letters, digits, `.`, `_`, `-`) is stored in upper case and is unique across the university: it is the room's
address `/r/<code>` and what its QR code holds. `number` is what the door says; `kind` is `lecture_hall`, `classroom`,
`lab`, `computer_lab`, `office` or `other`; `floor` and `capacity` are optional numbers; `accessible` is 0 or 1.

A timetable row keeps the room as text and gets `room_id` when that text, without case and spaces (ı = i), is a room's
code, `<building name>, <number>` or `<room name>, <number>`. A text that two rooms answer to is linked to neither.
`POST /api/facilities/link-rooms` sets every row and answers `{"linked", "changed", "unmatched": [{"room", "rows"}]}`.

`/r/{code}` is public and shows no one's name: the room, its building, kind, capacity, floor and accessibility, the
lesson in progress and the next one within 14 days (course, kind, time), on teaching days of the current term that are
not holidays. It refreshes itself every 5 minutes, so a tablet on the door stays current.

Routes (Task 31). `/r/{code}?to={room}` adds the way from this room's door to another room (`&sf=1`: step-free, by
lift; a step-free way never passes a stairs node or a step edge), as numbered steps with the length in metres; a room
in another building first names that building. Without a way the page says why: the room has no node in the route map,
or no node joins the two. A building's graph is imported from two CSV files, all or nothing, with
`python backend/manage.py import-routes --building EK --nodes nodes.csv --edges edges.csv` (nodes:
`code,kind,floor,room,label`, kind one of entrance, corridor, stairs, lift, door, a door naming its room; edges:
`from,to,length_m,step_free`, a floor change joining two stairs or two lifts); it prints the rooms without a door node,
the doors no entrance reaches and the accessible rooms without a step-free way. The demo's graphs are synthetic
(`content/routes/`); the real ones are drawn from the university's floor plans.

### Timetable and lessons (Task 19)

A timetable row belongs to a teaching unit; its kind and teacher come from the unit, its term from the unit's course.
It repeats on its weekday every week, or in odd or even weeks (week 1 is the Monday-to-Sunday week of the term's first
teaching day). Saving a row checks the other active rows of the term on that weekday: the same room (by room id once
the text names a room, so "EK-220" and "Əsas korpus, 220" are one room), the same teacher, or a shared group, where a
whole group (unit without subgroup) meets each of its subgroups and subgroup 1 does not meet subgroup 2. A clash
answers `409 {"error", "conflicts": [{"what": "room" | "teacher" | "group", "groups", "id", "course", "kind", "start",
"end", "room", "teacher"}]}`.

Making lessons (`POST /api/timetable/generate`) creates one lesson per row per teaching day of the term (between
`teaching_start` and `teaching_end`, in the row's weeks, not on a `calendar.holidays` day) with the row's academic hours
and the unit's teacher. A lesson keeps the slot it was made for (`slot_day`, `slot_start`); a unit has one lesson per
slot (unique index), so making them again creates nothing, also after a lesson was moved. A lesson is `scheduled` or
`cancelled`; cancelling or moving it is refused once attendance is written, and notifies the students on the lesson's
list: an enrolment in force that day, the unit's groups (any, when it names none) and its subgroup.

The calendar feed is a secret address `/ical/<token>`; only the token's SHA-256 is stored. It holds a student's lessons
(as above) or a teacher's own, with `DTSTART;TZID=Asia/Baku` (the zone of `ZEKA_TZ`, with its `VTIMEZONE`), `LOCATION`,
and `STATUS:CANCELLED` for a cancelled lesson; a calendar that subscribes to it sees every change on its next fetch.

### Attendance journal (Task 20)

A lesson's list: the students with an enrolment in force on its day, in the unit's groups and subgroup. The lesson's
teacher writes it from the lesson's day until `journal.edit_hours` (setting, default 48) after it ends, in one request:
every student not named in `marks` is present, and saving the same marks again changes nothing. An excused absence
(an approved absence request) is never overwritten by a mark. After the window, before the cut-over date, or for an
imported row (`source='legacy'`), only a corrector (`journal.correct`: a department head, of the course's department
when the role is scoped to departments, or an administrator) changes it, with a reason that goes to the audit log
(`attendance_corrected`). A department head can name a substitute teacher for an upcoming lesson, with a reason
(`lesson_substitute`); the substitute then writes that lesson. Future and cancelled lessons are not written (`403`).

A student's standing per course: planned hours are the academic hours of the course's lessons in the term's teaching
period that are not cancelled and that the student is on the list of. Missed hours: up to the cut-over date (the
opening balance's `as_of`, else `journal.cutover_date`) the imported hours (an opening balance, or lesson rows with
`source='legacy'`), after it the absences recorded in Zəka; an excused absence counts when
`attendance.excused_counts_toward_limit` is on. The limit is the lower of the university's and the published syllabus's
(`courses.attendance_limit`). Status: `normal`, `warning` (past 80% of the limit), `not_admitted` (past the limit) or
`incomplete` (lessons before the cut-over date with nothing imported for them; never `not_admitted`).
`/api/attendance` and a course's page (`GET /api/courses/{id}`) carry `planned_hours`, `missed_hours`, `allowed_hours`,
`percent`, `limit_percent`, `status` and `as_of`. The course list (`GET /api/courses`) carries only the lesson counts and
`rate`: reading the journal for every course of the list made the busiest route twice as slow.

Opening balances are the import kind `attendance-opening` (`termSourcedId`, `courseSourcedId`, `userSourcedId`,
`heldHours`, `unexcusedHours`, `excusedHours`, `asOf`), resolved through the source system's links of those kinds. Their
source key is the three ids together; the same file again changes nothing, a balance changed in Zəka since is a
conflict, and a row whose held hours differ from what Zəka planned up to its date is listed in `warnings` with its row.

### Grade journal (Task 21)

The columns are the scheme's components and the exam (the published syllabus's scheme once Task 25 writes it, the
university's until then). A teacher writes the scores of the students on the lists of their own units of the course
(`403` for another unit's student); a corrector writes all. The attendance component is never typed (`400`): it is
`attendance.points_rule` applied to the share of the hours held so far that were missed (imported hours before the
cut-over date included), or the attended share when there is no rule. A cell takes a number or pasted text ("8,5");
out of range or not a number is refused cell by cell. A new score is a draft until published, and a student sees only
published scores. Changing a published score needs a reason and writes `grade_changes`. A final grade (`final_grades`,
one per student, course and term) is written from the published scores once the exam is in; below the exam minimum it
is F. The `grades` import kind (`courseSourcedId`, `userSourcedId`, `component`, `score`, `max`?, `asOf`?) writes through
the same table with `source='legacy'`, the importing account and the reason `import:<file name>:<SHA-256>`; a component
outside the scheme is a refused row; the same file again changes nothing.

A transcript is built only from final grades: the average is sum(score x credits) / sum(credits) over all of them, the
total credits count only passed courses. A `transcript` request is refused until the student's history is reconciled
(`history_reconciled_at`), unless the student was admitted in or after Zəka's first term.

### Assignments and material files (Task 22)

An assignment counts toward one grade component (not attendance, not the exam) with a maximum not above the
component's. A late submission is marked late or refused by the assignment's rule; a student replaces their submission
until it is graded. Only the student and the course's teachers read a submission, and a teacher of the course reads a
file attached to it. Grading writes the sum of the student's graded assignments of that component, capped at its
maximum, into the grade journal through the journal's own rules (a draft until published; a published score's change is
logged with the assignment's title as the reason).

`POST /api/courses/{id}/materials` keeps the uploaded file (`materials.file_id`; DOCX, PPTX, PDF, MD or TXT) besides
the extracted text; with `{"replaces": <material id>}` it is a new version (`replaces_id`): students and the tutor's
index see only the current version, the earlier one's file and text stay for the teacher.

### University settings (Task 17)

Sections: `university` (profile: name, short name, city, address, site, current period), `grading` (components with
their maximum points, one of them optionally the attendance component; the exam's maximum and minimum; the pass mark;
the letter scale from the top down, ending at the pass mark; components and exam add up to 100), `attendance`
(`limit_percent`, `excused_counts_toward_limit`, `points_rule` as `[missed % up to, points]` rows), `journal`
(`cutover_date`), `calendar` (`lesson_times`, `holidays`), `registry` (`prefix` of new document numbers), `sessions`
(idle minutes and absolute hours for staff and students), `sso` (Task 14; no secret), `activation` (`days`); `journal` also
holds `edit_hours` (Task 20). The rules
live in `backend/zeka/core/tenant.py`; `/api/grades` returns each course's `result` (`semester`, `exam`, `total`,
`letter`, `passed`, `reason`: `exam_min` below the exam minimum, `pass_mark` below the pass mark) from the scheme, and
`/api/attendance` the limit from the attendance rules and the weeks of the current term. Semester dates are
`academic_terms` rows, not settings.

Activation codes: 12 base32 characters (60 bits) shown as `XXXX-XXXX-XXXX`; only their SHA-256 is stored; a code works
once, only with its student number, until `activation_days` (setting, default 14), and only for an active student account
that has no way in yet: no password, no second factor and no linked provider identity (a temporary password, a role
change or a deactivation after the batch makes its code useless). The session after activation has the same `scope`
as after a password. A new batch for a faculty revokes the unused codes of the old one; CSV cells that start with
`= + - @`, a tab or a carriage return get a leading `'`, so a spreadsheet does not run them. Wrong codes count per (student number, address) like wrong passwords: 10 in 15 minutes
answer `429` for that address; a wrong attempt does not spend the code. `manage.py activation-codes --faculty CODE
--out FILE` writes the same CSV (mode 600) for the dean's office.

### `POST /api/auth/login`

Body `{"login": "<user name or e-mail>", "password": "<as typed>"}`. `200` with `{"user", "home"}` and the session cookie;
`user.must_change` is true after a temporary password, and that session reaches only `/api/auth/*` and `/api/bootstrap`
(other routes answer `403`). A wrong password, an unknown account and a disabled account all get the same `401`.
Failures are counted per account and client (IPv6: its /64): 10 in 15 minutes block that client for that account for
15 minutes, and 100 consecutive failures lock the account for 15 minutes; a name that matches no account is counted and
locked the same way, so the answer does not reveal whether it exists. Both answer `429` with `Retry-After`, are
checked before the password is hashed, and are written to the audit log. Hashing: scrypt (n=2^15, r=8, p=1); a hash
with older parameters is replaced at the next sign-in.

### Second factor (Task 12)

After the right password, `POST /api/auth/login` answers `user.scope`: `full`, `mfa` (a TOTP or recovery code comes
next; the session reaches only `/api/auth/mfa/verify`, `/api/auth/logout` and `/api/bootstrap`) or `mfa_enroll` (a staff
account without a second factor: only `/api/auth/mfa/*`, `/api/auth/password`, logout and bootstrap). TOTP follows RFC 6238
(HMAC-SHA1, 30 s, 6 digits, one step either side); a step is accepted once. Wrong codes count with wrong passwords for the
account and address (Task 10), and five wrong codes end the pending sign-in: the password step starts again. Passing the
second factor gives the session a new id. Recovery codes work once and are stored as SHA-256.

### Single sign-on (Task 14)

A generic OpenID Connect client: Authorization Code with PKCE (S256), `state` and `nonce`. The tenant setting `sso` holds
`enabled`, `issuer`, `client_id`, `label`, `scopes` (added to `openid email profile`), `student_claim` (the claim that
carries the student number), and `mfa_amr` / `mfa_acr` (the values of the provider's `amr` / `acr` the university trusts
as a second factor; empty by default). The client secret comes only from the environment variable
`ZEKA_OIDC_CLIENT_SECRET` (sent with HTTP Basic); without it the client is public and relies on PKCE. The discovery
document is read from `<issuer>/.well-known/openid-configuration`; its `issuer` must equal the setting, and the issuer
and every endpoint in it must be `https` (`http` only in demo mode for a loopback address). Calls follow no redirect and
keep the default certificate checks; no setting turns them off. `GET /api/bootstrap` reports `app.sso` as
`{"enabled", "label"}`.

The started sign-in lives in `sso_pending` for 10 minutes and is bound to the browser by the `HttpOnly` cookie
`zeka_sso` (path `/api/auth/sso`), so a callback link opened elsewhere, a changed `state` or a second use answers
`sso=expired`. The ID token comes straight from the token endpoint over TLS and is checked per OIDC Core 3.1.3.7: `iss`,
`aud` (exactly this client), `azp`, `exp` and `iat` with 60 s of leeway, `nonce`, and an `alg` other than `none`; the
userinfo `sub` must equal the ID token's (5.3.2); userinfo never adds `amr`/`acr`, and its `email_verified` counts only
together with its own `email`. A refusal is `sso=failed` and its reason is audited (`sso_refused`); a failed discovery is
remembered for 30 s, so a provider outage is not asked again on every start.

An account is bound to the provider's `(iss, sub)` in `sso_identities`; later sign-ins find the account only through
that row, so a changed e-mail at the provider never moves a sign-in. The first sign-in links a student account
automatically by the `student_claim` value (exactly one student with that number), or by `email` when `email_verified`
is JSON `true`; an account with a staff role, primary or granted, is never linked automatically. Staff accounts are
linked by their owner (`POST /api/auth/sso/link` from a session that passed the local second factor) or by an
administrator. No account is created: an unknown person gets `sso=not_found`. After the provider, a staff session still
needs the local second factor (`scope` `mfa` or `mfa_enroll`) unless the provider's `amr`/`acr` names a trusted value.
Redirect reasons: `not_found`, `failed`, `expired`, `cancelled`, `off`; for linking, `/#/profile?sso=linked|taken|expired`.

### Status orders (Task 15)

`POST /api/directory/students/{id}/status` with `{"kind", "order_no", "order_date", "effective_date", "to_group_id"?,
"note"?}`. `kind` is one of `admission`, `group_change`, `transfer_in`, `transfer_out`, `academic_leave`, `expulsion`,
`reinstatement`, `graduation`; the order number, the order date and the effective date (`YYYY-MM-DD`) are all required,
and `group_change` / `transfer_in` name the new group. Orders are only added (database triggers refuse a change or a
delete; only `reported_at` may be set later); a wrong order is corrected by a new one whose note gives the reason. The
status of a day comes from the orders in force on it: `active`, `on_leave`, `expelled`, `transferred`, `graduated`.
Leave, expulsion, transfer out and graduation end the student's open enrolments on the effective date, so the student
leaves the lesson lists from that day while earlier attendance and grades stay; the account itself stays active (a
student on leave signs in and sees their own documents). Only the academic office enters orders on this screen until
the owner decides (SPEC, Open Questions 17). Issuing an `academic_leave` request (`POST /api/requests/{id}/action`,
`"issue"`) needs `order_no`, `order_date` and `effective_date` too, writes the order, and the extract prints the order's
number and date.

### `POST /api/auth/password`

Body `{"current", "new"}`. The new password follows NIST SP 800-63B-4: at least 15 characters (64 and more allowed, at
most 128), no composition rules, not in `content/password-blocklist.txt`, not a repetition, a keyboard or alphabet
sequence, or mostly the user's own name. A refusal is `400` with the reason in the request's language; a wrong current
password is `403` and counts as a failed sign-in.

### `POST /api/auth/demo`

| Field | Type | Notes |
|---|---|---|
| `role` | `student`, `teacher`, `office`, `leader` or `admin` | Required; an unknown role returns `400` |
| `code` | string | The access code; required when the server has one and the request carries no valid session. A visitor with a valid session can switch roles without it. A wrong code returns `403` |
| `user` | string | Only with `role: "student"`: sign in as the student with this username instead of the demo student (`404` when there is none). Used by the Radar demo storyline |

Signing in deletes the session the request carried, if any.

```http
POST /api/auth/demo
Content-Type: application/json
X-Lang: en

{"role": "student"}
```

```json
{
 "user": {"id": 1, "username": "aysel", "full_name": "Aysel Məmmədova", "role": "student",
          "title": "Kompüter mühəndisliyi · 2-ci kurs", "color": "#2b5aa8", "consent_at": null, "prefs": {}},
 "home": "/student",
 "token": "lFV5P5bkDeFbbHsfx1ccUaahjeElasfTlk2tAKpS-FI"
}
```

Response header: `Set-Cookie: zeka_sid=<token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=43200` (the session lifetime in seconds), with `; Secure` added when the server runs with an `https://` public URL.

### `GET /demo/login?role=<role>&code=<code>&user=<username>&next=<path>`

Signs in like the call above (the role defaults to `student`) and answers `302` to `next`, or to the role's home page when `next` is absent. `next` must be a same-site relative path; anything else, such as `//host`, redirects to `/`.

### `GET /api/bootstrap`

Works with or without a session. Returns:

| Field | Content |
|---|---|
| `user` | The signed-in user (`id`, `username`, `full_name`, `role`, `title`, `color`, `consent_at`, `prefs`) or `null` |
| `app` | `university`, `faculty`, `specialty`, `semester`, `base_url`, `engine` (`mode` is `demo` or `llm`, plus a `label`), `news_kinds`, `version`, `mode` (`demo` or `prod`), `access_required`, `sso` (`enabled`, `label`), `langs`, `vendor`, `contact` |
| `home` | Home route of the user's role, or `null` |
| `unread` | Number of unread notifications |

### Privacy (Task 40)

The purposes, the legal bases and the decisions behind them are in `docs/privacy/data-inventory.md`.

**`GET /api/privacy`** (with or without a session) returns the following:

- `purposes`: `ai` (the AI tutor and the campus assistant inside the platform) and `external_ai` (masked questions sent to the external AI service). Each has `id`, `text`, `version` and the person's newest `consent`: `granted`, `version`, `at`, `method` and `current` (whether it was given to the current version). Without a session, `consent` is `null`.
- `retention`: the retention periods in days.
- `operator`: the university's name.
- `external_ai`: `enabled`, `vendor` and `country`, taken from the LLM settings. The notice names the service and its country from them; the key and the address are never returned.
- `requests`: the person's own deletion requests (with a session only).

A version is the first 12 hex digits of the SHA-256 of the text consented to. For `external_ai` that text includes the configured `vendor` and `country`, so another service is a new version.

**`POST /api/consent`** takes `{"ai": <bool>, "external": <bool>, "versions": {"ai": "...", "external_ai": "..."}}`:

- Each boolean that is present is one `consents` row with method `portal`, plus the text in `consent_texts` and an audit `consent` entry. A body with neither boolean records `ai: true`.
- `versions` names the version the page showed. Another version gives `409`, and so does an `external: true` without its version.
- `external: true` gives `400` while an external AI is enabled but its `vendor` or `country` is empty: the notice would name no recipient. In that state an earlier external AI consent does not count either, and the offline engine answers. `external: false` is always accepted.
- `ai: false` withdraws the AI study aids' consent and deletes the person's AI chats at once. The audit entry carries `chats_deleted`.

Response: `{"ok": true, "consent_at": ..., ...}` followed by the `GET /api/privacy` fields. `consent_at` mirrors the `ai` consent.

Without a current `ai` consent, the tutor (`POST /api/tutor/{cid}/ask`) and the campus assistant (`POST /api/campus/ask`) answer `403` with a translated message. They store nothing. Every role is covered. The rest of the portal does not depend on this consent.

**`GET /api/me/export`** returns the signed-in person's own rows as a JSON file (`Content-Disposition: attachment`). The format is `zeka-export/1` with these fields: `generated_at`, `user_id`, `tables` (table → rows), `not_exported` (the inventory's columns that are never exported) and `notice`. Each export writes `privacy_export` to the audit log.

The export leaves out the following:

- secrets;
- `audit.detail`, `files.path` and `exam_events.actor_id`;
- `teacher_questions.ai_draft` (the teacher's unsent AI draft);
- exam forms and questions;
- unreleased exam scores;
- draft grades;
- other people's rows.

The Zəka Radar support plan's `interventions.risk_before`, `interventions.level_before` and `interventions.drivers` **are** exported. This is the owner's decision of 2026-11-21: they are the student's own data. The student screens still leave them out (Zəka Radar, below).

**`POST /api/me/erase`** takes `{"reason"?}` and sends a deletion request. A second request while one is pending gives `409`. The academic office decides with `GET /api/privacy/requests` and `POST /api/privacy/requests/{id}/decide` (`privacy.decide`), as `docs/privacy/data-inventory.md` describes.

## Profile, notifications, search and files

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/me` | any | Full profile with group, student number, funding, department, university, faculty and programme |
| `PUT` | `/api/me/prefs` | any | Save interface preferences |
| `GET` | `/api/badges` | any | Counters for the navigation badges |
| `GET` | `/api/notifications` | any | Last 40 notifications and the unread count |
| `POST` | `/api/notifications/read` | any | Mark notifications as read |
| `GET` | `/api/guide` | any | Help articles, FAQ and keyboard shortcuts for the user's role |
| `GET` | `/api/search` | any | Global search |
| `POST` | `/api/files` | any | Upload a file for a request or a support ticket |
| `POST` | `/api/files/{id}/link` | owner, `office`, `admin` | One-time download link |
| `GET` | `/api/files/{id}` | owner, `office`, `admin` | Download the file |
| `GET` | `/api/files/{id}/preview` | owner, `office`, `admin` | Text preview for display inside the application |

**`PUT /api/me/prefs`.** Body fields, all optional: `theme` (`light` or `dark`), `lang` (`az`, `en`, `ru`), `sidebar` (`open` or `collapsed`), `tours` (list of completed tour keys, up to 120). Unknown or invalid values are ignored. Response: `{"prefs": {...}}`.

**`GET /api/badges`.** Always `notifications` and `news` (unread news for the user's audience). Students also get `requests` (open requests), `absences` (unexcused absences) and `plan` (open support plans); teachers get `questions` (open forwarded questions); `office`, `leader` and `admin` get `office` (submitted requests; a dean's office counts only its faculties). Teachers, `office` and `leader` get `radar` (high-risk students in their Radar scope). `support` is the number of open tickets for `office` and `admin`, and the number of the user's tickets waiting for their reply for everyone else.

```json
{"notifications": 3, "news": 7, "questions": 3, "radar": 2, "support": 1}
```

**`POST /api/notifications/read`.** Body `{"all": true}` or `{"ids": [1, 2, 3]}` (up to 100 ids). Response: `{"unread": <n>}`.

**`GET /api/search?q=<text>`.** Words shorter than two characters are dropped; a result must contain every remaining word. Matching ignores Azerbaijani diacritics and also checks the English and Russian translations of catalogue text. Searched, depending on the role: e-services, news, AzTU achievements, courses, course material sections (students and teachers, best 4 above a relevance threshold), AI Academy modules and teaching tools (teachers), and help articles. Up to 24 results:

```json
{"results": [
 {"group": "E-services", "title": "Academic transcript",
  "sub": "An official statement of completed courses, credits and grades — for an exchange programme, a master's programme and an employer.",
  "link": "/student/services?new=transcript", "icon": "list"},
 {"group": "News", "title": "Erasmus+ exchange programme: applications for the spring semester are open", "sub": "…", "link": "/news/3", "icon": "news"}
]}
```

**`POST /api/files`.** Body: `filename`, `content_b64`, and optionally `accept` (`doc` by default, or `image` to allow only PNG and JPEG). The file must be non-empty, at most 10 MB, and a PDF, PNG, JPEG or DOCX by its content; the extension, if any, must match. Response: `{"id", "filename", "mime", "size"}`. The returned id is then passed in the `files` list of a request or as `file_id` of a support ticket; a file can be attached once.

**`GET /api/files/{id}`.** Returns the file with its MIME type, `Content-Disposition: inline` (or `attachment` with `?download=1`) and `Cache-Control: private, no-store`. Every download is written to the audit log.

**`GET /api/files/{id}/preview`.** Returns `id`, `filename`, `mime`, `size`, `created_at`, `kind` (`pdf`, `image`, `docx` or `other`) and `pages`, a list of extracted text pages for PDF and DOCX. A PDF is parsed in a separate, time-limited process; pages are empty when the text cannot be extracted in time.

## Courses, schedule, attendance and grades

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/courses` | any | Course cards: the student's enrolments, the teacher's courses, all courses for staff |
| `GET` | `/api/courses/{id}` | any, with course access | Course page |
| `GET` | `/api/materials/{id}` | any, with course access | One material with its sections, glossary and further reading |
| `GET` | `/api/source/chunk/{id}` | any, with course access for students and teachers | One material section, used to open a citation |
| `GET` | `/api/source/kb/{id}` | any | One published knowledge base entry, used to open a campus assistant citation (a draft or archived one is `404`) |
| `GET` | `/api/schedule` | any | Current week's timetable and the user's registered events |
| `GET` | `/api/attendance` | `student` | Attendance per course and the list of absences, late arrivals and excused lessons |
| `GET` | `/api/me/absences` | `student` | Unexcused absences in a date range that are not already in an open excuse request |
| `GET` | `/api/grades` | `student` | Current semester components, past semesters and the weighted average |
| `GET` | `/api/courses/{id}/attendance` | `teacher`, `leader`, `admin` | Last 12 lessons with attendance counts and the last 20 excused absences |
| `GET` | `/api/student/home` | `student` | Data for the student home page |

Course access means: students must be enrolled, teachers must teach the course, staff may read any course.

**Course card fields:** `id`, `code`, `name`, `credits`, `color`, `description`, `tutor_locked`, `teacher`, `teacher_title`, `suggestions` (suggested tutor questions), `modes` (allowed tutor modes), `materials`, `students`, `next` (next lesson). For students also `progress` (best test results as a percentage) and `attendance` (see below).

**`GET /api/courses/{id}`** adds `tutor_rules`, `materials_list`, `schedule`, `tools`, published `quizzes`, `references` with `references_checked` (the date the links were last checked), and for teachers, leaders and administrators `insights`: `questions_total`, `weekly` (8 weeks), `this_week`, `top_topics`, `positive_rate`, `cited_rate`, `no_source_rate` and `gaps` (student questions the material could not answer).

**Attendance summary per course:** `total`, `present`, `late`, `absent`, `excused`, `planned` (weekly lessons × 15 weeks), `limit` (25% of planned) and `rate` (present and late as a percentage of recorded lessons).

**`GET /api/me/absences?from=YYYY-MM-DD&to=YYYY-MM-DD`** returns `[{lesson_id, day, start, end, kind, course, color}]`. The excuse request form uses it to list the lessons a student can select.

**`GET /api/grades`** returns `courses` (per course: `items` with `name`, `max`, `score`, `note`; the attendance component is computed from the current attendance), `past` (previous semesters with letter grades), `average` (credit-weighted over past semesters) and `credits`. Past-semester scores are deterministic synthetic values in the demo.

**`GET /api/schedule`** returns `days` (Monday to Friday of the current week with their lessons), `events` (up to 6 upcoming events the user registered for), `now` and `week_start`.

## AI tutor and campus assistant

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/tutor/{cid}/history` | any, with course access | Last 40 tutor messages for this course, usage counter and engine |
| `POST` | `/api/tutor/{cid}/ask` | `student`, `teacher` | Ask the course tutor |
| `POST` | `/api/tutor/{cid}/clear` | any, with course access | Delete the user's tutor history for this course |
| `POST` | `/api/tutor/{cid}/forward` | `student` | Forward a question to the course teacher |
| `POST` | `/api/messages/{id}/rate` | any | Rate one of the user's assistant answers |
| `GET` | `/api/campus/history` | any | Last 40 campus assistant messages |
| `POST` | `/api/campus/ask` | any | Ask the campus assistant |
| `POST` | `/api/campus/clear` | any | Delete the campus assistant history |

### `POST /api/tutor/{cid}/ask`

| Field | Type | Notes |
|---|---|---|
| `message` | string | Required, cut to 2,000 characters |
| `mode` | `socratic`, `explain` or `practice` | Must be one of the modes the teacher allows; otherwise the first allowed mode is used |

Errors: `400` empty message, `403` no current consent for the AI study aids (any role; nothing is stored, see Privacy above), `423` tutor locked by the teacher (students only), `429` daily limit reached (students only; default 50 messages per day across the tutor and the campus assistant) or more than 30 assistant calls in a minute.

The message is masked for personal data (unless the administrator turned masking off), then answered by the configured LLM when one is enabled and a relevant passage exists, and by the offline engine otherwise. A question goes to the LLM only after the person consented to the current external AI text and service (`POST /api/consent` with `external: true` and its version); otherwise the offline engine answers and `meta.note` says why. In practice mode the message is either an answer to the pending question or a request for a new one. The answer `meta` can contain `mode`, `topic`, `level` (Socratic step), `guardrail` (the user asked for a finished answer), `no_source`, `practice_qid`, `graded`, `correct`, `engine` and `note` (why the LLM was not used).

```http
POST /api/tutor/1/ask
Content-Type: application/json
X-Lang: en

{"message": "What is Ohm's law? Om qanunu nədir?", "mode": "explain"}
```

```json
{
 "user": {"id": 3681, "role": "user", "content": "What is Ohm's law? Om qanunu nədir?", "meta": {"mode": "explain", "pii": []}, "cites": []},
 "answer": {
  "id": 3682, "role": "assistant",
  "content": "**Om qanunu** — a brief explanation based on the materials:\n\n- Om qanunu dövrə hissəsində cərəyan şiddəti, gərginlik və müqavimət arasındakı əlaqəni ifadə edir. [1]\n- … [2]\n\nKey formula:\n\n> I = U / R\n\nSource: [1]\n\n**Check yourself:** If one of the quantities in the formula doubles, how does the result change?",
  "meta": {"mode": "explain", "topic": "Om qanunu"},
  "cites": [
   {"n": 1, "id": 3, "kind": "chunk", "material": "Mühazirə 1. Əsas anlayışlar və Om qanunu", "heading": "Om qanunu",
    "snippet": "Om qanunu dövrə hissəsində cərəyan şiddəti, gərginlik və müqavimət arasındakı əlaqəni ifadə edir. …"},
   {"n": 2, "id": 1, "kind": "chunk", "material": "Mühazirə 1. Əsas anlayışlar və Om qanunu", "heading": "Giriş", "snippet": "…"}
  ]
 },
 "usage": {"used": 1, "limit": 50}
}
```

The tutor's own phrasing follows `X-Lang`; sentences quoted from the material stay in the language of the material. Each `[n]` in `content` corresponds to `cites[n-1]`; `GET /api/source/chunk/{id}` returns the full passage.

### `POST /api/tutor/{cid}/forward`

Body: `question` (required, up to 2,000 characters), `anonymous` (boolean), `context` (up to 1,500 characters, for example the preceding tutor answer). The teacher is notified. Response: `{"ok": true}`.

### `POST /api/messages/{id}/rate`

Body: `{"rating": 1}` or `{"rating": -1}`; any other number clears the rating. Only the user's own messages are changed.

### `POST /api/campus/ask`

Body: `{"message": "..."}`, required, cut to 1,500 characters. The same consent (`403` without it), daily limit and per-minute limit apply. English and Russian keywords are expanded to the Azerbaijani terms used in the knowledge base. Before the knowledge base the assistant answers two questions from the university's own records (Task 31): where a room is (by its code, its name, or a number in a question about a place) with the way from the building's entrance, step-free when the question mentions a lift or a wheelchair; and the person's next lesson ("növbəti dərsim hardadır") from their timetable, with its room and the way. Such an answer has `meta.source` `rooms` or `timetable` and a link action (`{"type": "link", "href": "/r/{code}"}`). `answer.meta.actions` lists request forms the user can open from the answer:

```json
{
 "answer": {
  "id": 3684, "role": "assistant",
  "content": "**Təhsil aldığını təsdiq edən arayışı necə almaq olar?**\n\n- Təhsil aldığını təsdiq edən arayış E-xidmətlər bölməsindən onlayn sifariş olunur. [1]\n- … [1]\n\nYou can submit the request online here:",
  "meta": {"actions": [{"type": "request", "code": "enrollment_certificate", "label": "Order a certificate"}]},
  "cites": [{"n": 1, "id": 1, "kind": "kb", "material": "Tələbə bələdçisi (demo), 2.1", "heading": "Təhsil aldığını təsdiq edən arayışı necə almaq olar?", "snippet": "…"}]
 },
 "user": {"…": "…"},
 "usage": {"used": 2, "limit": 50}
}
```

### Knowledge base and handoff (Task 32)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/api/kb` | `kb.manage` (`academic_office`, `admin`) | The articles: heading, source and clause, review date (`overdue` once it has passed), status, version |
| `GET` | `/api/kb/{id}` | as above | An article and its versions (who, when, status) |
| `POST` | `/api/kb` | as above | A new article: `heading` (3–200), `text` (20–8000), `source` (required), `source_ref`, `request` (an e-service code) with `action_label`, `review_at` (YYYY-MM-DD), `status` (`published`, `draft`, `archived`) |
| `PUT` | `/api/kb/{id}` | as above | Change it: a new version (an article from the seed keeps its first state as version 1); audited |
| `POST` | `/api/campus/handoff` | the author of the answer | `{"message_id"}` of an assistant answer: a support ticket (category `university`) with that day's conversation up to it; once per answer, asking again gives the same `ticket_id` |

Only a published article is searched; a save reaches every worker's index on its next request (`index_changes`).
Every campus answer carries a source (`cites`, or `meta.source` for rooms and the timetable) or a `handoff` action;
an Azerbaijani question that shares a single word with the best article, a word under a third of the question's weight,
is answered with the handoff instead of that article. `python tools/eval_assistant.py tests/eval/assistant_az.jsonl`
asks 50 questions (rules, services, rooms, the next lesson, out of scope) on a fresh demo database: 48 right, no
answer without a source or a handoff.

### Course forum (Task 33)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/api/courses/{id}/qa` | the course's enrolled students and teachers (others `404`; other roles `403`) | Topics: title, tag, status, replies, FAQ, author (an anonymous one as "Anonim tələbə" to students; real to the course's teachers), `mine` |
| `POST` | `/api/courses/{id}/qa` | as above | A topic: `title` (5–140), `text` (10–4000), `tag` (≤ 40), `anonymous`; the course's teacher is told |
| `GET` | `/api/qa/topics/{id}` | as above | The topic and its replies; for the course's teachers also hidden replies and the `ai_draft` |
| `POST` | `/api/qa/topics/{id}/replies` | as above | A reply (2–4000); the teacher's reply tells the author |
| `POST` | `/api/qa/replies/{id}/accept` | the course's teachers | The accepted answer (one per topic): the topic is `answered`, the author is told; a FAQ entry follows it |
| `POST` | `/api/qa/topics/{id}/draft` | the course's teachers | An answer the offline tutor writes from the course's materials, cited; stored for the teacher only |
| `POST` | `/api/qa/topics/{id}/faq` | the course's teachers | `{"on": true}`: the question and the accepted answer become a section of the material "Fənnin FAQ-ı" that the tutor searches and cites (every worker); `false` takes it out |
| `POST` | `/api/qa/reports` | readers of the topic | `{"topic_id", "reply_id"?, "reason"}`; audited |
| `GET` | `/api/qa/reports` | `qa.moderate` (`office`: its faculties' students; `admin`) | Open reports with the reported text and its real author |
| `POST` | `/api/qa/reports/{id}/resolve` | as above | `{"action": "hide" | "keep"}`: hiding takes it from the students (and out of the FAQ); every open report on it is closed; audited |

`POST /api/tutor/{cid}/forward` (a question sent from the tutor) creates a **private** topic (`private: true`): only its
author and the course's teachers read it, and an anonymous one shows "Anonim tələbə" to the teacher too (Checkpoint E).
The teacher's answer through `/api/teacher/questions/{id}/answer` is its accepted reply (the FAQ follows it). An
anonymous author's own reply stays anonymous. Only a teacher's accepted answer can go to the FAQ. A draft with no
source is not saved (`no_source: true`).

### Office hours (Task 34)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` / `POST` | `/api/office-hours` | `teacher`, `dept_head` | The teacher's weekly ranges / a new one: `weekday` (1–6), `start`, `end` (HH:MM, ≤ 6 h), `slot_min` (10, 15, 20, 30, 45, 60), `place` or `online_url` (https) |
| `POST` | `/api/office-hours/{id}/end` | the range's teacher | End a range: its future bookings are cancelled and each student is told |
| `GET` | `/api/office-hours/teachers` | `student` | The teachers of the student's courses |
| `GET` | `/api/office-hours/teachers/{id}/free` | a student of that teacher's courses (others `404`) | Free slots from now to 14 days ahead |
| `POST` | `/api/office-hours/book` | as above | `{"hours_id", "day", "start", "topic"?}`: one free slot; a slot booked meanwhile is `409` (a partial unique index makes the second of two simultaneous bookings fail); at most two upcoming bookings with one teacher (`400`); the teacher is told |
| `GET` | `/api/office-hours/bookings` | `student`, `teacher`, `dept_head` | One's bookings, a week back to two weeks ahead |
| `POST` | `/api/office-hours/bookings/{id}/cancel` | either side | Cancel an upcoming booking; the other side is told |

A booking is an event of both people's iCal feeds (`UID:office-{id}`, `CANCELLED` once cancelled). The periodic
`reminders.sla` job tells both sides once when a booking starts within two hours. The campus assistant answers
"… müəllimin qəbul saatı" with the weekly ranges of the student's teachers (the one named, when a name is in the
question) and a link to `/office-hours`.

### Clubs and channels (Task 35)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` / `POST` | `/api/clubs` | any; proposing: `student`, `teacher`, `dept_head` | Approved clubs (and one's own proposals) with one's membership / propose a club (`name` 3–80, `description` 10–1000): its proposer leads it |
| `GET` | `/api/clubs/pending`, `POST /api/clubs/{id}/decide` | `clubs.approve` (`office`, `admin`) | Proposals; `{"approve": bool, "note"?}`: an approved club gets the channels "Ümumi" (chat) and "Elanlar" (announcements); audited |
| `GET` | `/api/clubs/{id}` | any (an unapproved club: its leader and approvers) | The club, one's membership and, for members, its channels |
| `POST` | `/api/clubs/{id}/join`, `/leave`, `/conduct` | members-to-be / members | Ask to join (a removed member cannot ask again; one who left asks the leader again and keeps a mute), leave (audited), accept the code of conduct (before the first post) |
| `GET` | `/api/clubs/{id}/members` | members, `community.moderate` | Members; the leader and moderators also see requests, removals and mutes |
| `POST` | `/api/clubs/{id}/members/{uid}/{approve,remove,mute}` | the club's leader, `community.moderate` | Let in, remove, or mute (`minutes` 5–43 200, `reason`); never the leader; audited |
| `GET` | `/api/channels/{id}/messages?since_id=` | the club's members | The last 100 messages, or those after `since_id` with `hidden`: the ids hidden among the channel's last 400; the page polls every 3 seconds while visible; moderators also see hidden ones |
| `POST` | `/api/channels/{id}/messages` | the club's members | `{"text"}` (≤ 2 000): 409 before the code of conduct; 403 in an announcements channel unless the leader, and while muted (with the end time); 20 a minute (429) |
| `POST` | `/api/club-messages/{id}/report`, `/hide` | members / the leader and `community.moderate` | Report (audited) / hide a message |
| `GET` | `/api/community/reports`, `POST /api/community/reports/{id}/resolve` | `community.moderate` (every club), a club's leader (its own, without the reporter's name and without reports on the leader's own messages) | Open reports with the message and its author / `{"action": "hide" \| "keep"}` (a leader cannot keep a report on their own message); audited; one open report per person and message; proposals, join requests and reports: 10 per user per 10 minutes |

Every channel route answers 403 to a non-member (`tests/security/test_community_access.py` walks the route table). The
daily `retention.purge` deletes club messages older than `limits.community_retention_days` (180) with their reports.
Club events use the existing news and registration flow.

## Tests and Test Studio

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/quizzes` | `student` | Published tests of the student's courses with attempts used, best score and whether a new attempt is allowed |
| `POST` | `/api/quizzes/{id}/start` | `student` | Start an attempt |
| `POST` | `/api/attempts/{id}/submit` | `student` | Submit answers and get the graded result |
| `GET` | `/api/attempts/{id}` | `student` | Result of one of the student's attempts |
| `POST` | `/api/studio/generate` | `teacher` | Generate draft questions from course material |
| `GET` | `/api/questions` | `teacher` | Question bank of a course |
| `PUT` | `/api/questions/{id}` | `teacher` | Edit, approve or return a question to draft |
| `DELETE` | `/api/questions/{id}` | `teacher` | Delete a question |
| `GET` | `/api/teacher/quizzes` | `teacher` | The teacher's tests with attempt counts and average score |
| `POST` | `/api/quizzes` | `teacher` | Publish a test |
| `GET` | `/api/quizzes/{id}/results` | `teacher` | Score distribution and per-question correct rate |

**`POST /api/quizzes/{id}/start`.** Returns `attempt_id`, `quiz`, `questions` without answers (`id`, `qtype`, `text`, `options`, `unit`, `topic`, `bloom`) and `deadline` (start time plus the time limit). `409` when the attempt limit is used up.

**`POST /api/attempts/{id}/submit`.** Body: `{"answers": {"<question id>": <answer>}}`. Answers are a letter, an option index or the option text for `mcq`; `true`/`false` or words such as "Doğru", "Yanlış", "true", "false" for `tf` (with "deyil" or "not" negating them); a number (comma or dot) for `numeric`, accepted within 2%. Missing answers count as wrong. The server enforces the time limit: a submission more than two minutes after the deadline is stored without its answers, so every question counts as wrong. Submitting an attempt again returns the stored result. Response:

```json
{
 "id": 769,
 "quiz": {"id": 10, "course_id": 6, "title": "Practice: Units 1–2", "kind": "practice", "time_limit": 10, "attempts": 3,
          "created_at": "2026-10-31T06:02:08", "show_explanations": 1, "questions": 5, "course": "Technical English", "color": "#db2777"},
 "score": 1.0, "max_score": 5.0, "percent": 20,
 "details": [
  {"qid": 39, "text": "Choose the correct sentence (Düzgün cümləni seçin):", "qtype": "mcq", "options": ["…"],
   "given": "B", "correct": true, "answer": "B) A resistor is used to limit current.",
   "explanation": "«is used to» quruluşundan sonra felin əsas forması gəlir: is used to limit.",
   "topic": "Describing function (Funksiyanı təsvir etmək)",
   "source": {"n": 1, "id": 85, "kind": "chunk", "material": "Unit 1. Describing components and functions",
              "heading": "Describing function (Funksiyanı təsvir etmək)", "snippet": "…"}},
  {"qid": 40, "given": "—", "correct": false, "…": "…"}
 ],
 "finished_at": "2026-11-05T06:02:08", "started_at": "2026-11-05T06:02:08"
}
```

**`POST /api/studio/generate`.**

| Field | Type | Notes |
|---|---|---|
| `course_id` | integer | Required; the teacher's own course |
| `material_id` | integer | Optional; limits generation to one material |
| `count` | integer | 1 to 15, default 6 |
| `types` | list of `mcq`, `tf`, `numeric` | Default all three |

Questions are saved as drafts with `origin: "ai"` and returned with `flags` (`source_ok`, plus `similar` when an approved question of the course is close) and the `source` passage. `400` when the course has no material; `422` when the material has no `Term — definition` lines and no section that matches a numeric template; `429` above 30 calls a minute. Response: `{"questions": [...], "engine": {...}}`.

**`GET /api/questions?course_id=<id>&status=draft|approved`.** Lists questions of the course, drafts first.

**`PUT /api/questions/{id}`.** Any of `text`, `explanation`, `topic`, `bloom`, `difficulty`, `unit`, `options` (up to 6), `answer` (option index for `mcq`, boolean for `tf`, number for `numeric`), `status` (`draft` or `approved`). The resulting answer must be gradable (an index within the options, at least two options for `mcq`), otherwise `400`. Returns the updated question.

**`POST /api/quizzes`.**

| Field | Type | Notes |
|---|---|---|
| `course_id` | integer | Required |
| `question_ids` | list of integers | Required; every question must be approved and belong to the course |
| `title` | string | Default "Yeni test" |
| `kind` | `practice` or `graded` | Default `practice` |
| `time_limit` | integer, minutes | 1 to 180, default 15 |
| `attempts` | integer | 1 to 10, default 3 for practice and 1 for graded |

Publishing notifies every enrolled student.

**`GET /api/quizzes/{id}/results`.** Returns `quiz`, `attempts`, `avg`, `buckets` (counts for the score bands in `labels`: 0–50, 51–60, 61–70, 71–80, 81–90, 91–100) and `questions` with `n` and `correct_rate` per question.

## Teacher tools

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/teacher/home` | `teacher` | Courses with insights, open student questions, today's lessons, recent excused absences, academy progress, draft count |
| `POST` | `/api/courses/{id}/materials` | `teacher` | Upload course material |
| `DELETE` | `/api/materials/{id}` | `teacher` | Delete a material and remove it from the index |
| `PUT` | `/api/courses/{id}/tutor` | `teacher` | Tutor settings for the course |
| `GET` | `/api/teacher/questions` | `teacher` | Questions forwarded from the tutor, open ones first |
| `POST` | `/api/teacher/questions/{id}/answer` | `teacher` | Answer a forwarded question |

**`POST /api/courses/{id}/materials`.** Body: `filename` (the extension selects the parser: `.md`, `.txt`, `.docx`, `.pptx`), `content_b64`, optional `title` (default: the file name without extension). The file may be at most 10 MB (`413`), and at least 40 characters of text must be extracted. Response: `ok`, `id`, `chunks`, `terms`, `chars`, `headings`, `glossary` (first 12 terms), `title`. The material is searchable by the tutor immediately.

**`PUT /api/courses/{id}/tutor`.** Body: `modes` (subset of `socratic`, `explain`, `practice`; defaults to `socratic` if empty), `rules` (free text up to 2,000 characters, passed to the LLM as the teacher's rules), `locked` (boolean). Returns the course page as in `GET /api/courses/{id}`.

**`POST /api/teacher/questions/{id}/answer`.** Body: `{"answer": "..."}`, required. The student is notified. Anonymous questions are listed with the student name replaced.

## E-services and documents

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/services` | any | Service categories and the request types on offer (`enabled`), with their form schemas |
| `GET` | `/api/requests` | `student`, staff, step roles | The student's requests, or the queue |
| `POST` | `/api/requests` | `student` | Submit a request |
| `GET` | `/api/requests/{id}` | owner, staff, step roles | Request with form data for display, timeline, message thread and attachments |
| `POST` | `/api/requests/{id}/messages` | owner, staff, step roles | Add a message to the request thread |
| `POST` | `/api/requests/{id}/resubmit` | `student` | Resubmit a request returned for correction |
| `POST` | `/api/requests/{id}/cancel` | `student` | Cancel a submitted or returned request |
| `POST` | `/api/requests/{id}/action` | the current step's role: `office`, `academic_office`, `dept_head` | Approve, return, reject or issue |
| `GET` | `/api/requests/{id}/preview` | `office`, `academic_office`, `admin` | HTML preview of the document before issue |
| `GET` | `/api/office/summary` | staff, `academic_office`, `dept_head` | Queue counters, documents issued this week, average processing hours |
| `GET` | `/api/admin/request-types` | `admin` | Every type with `enabled`, `effect` and `registered` (the effect is in code) |
| `PUT` | `/api/admin/request-types/{code}` | `admin` | `{"enabled": true\|false}`: open or close a type (audited) |
| `GET` | `/api/documents` | staff | Document registry search, up to 200 rows |
| `POST` | `/api/documents/{id}/revoke` | `office`, `admin` | Revoke a document |
| `POST` | `/api/documents/{id}/link` | holder, staff | One-time link to the document page |

Teachers cannot see requests; for them request endpoints answer `404` or `403`. "Staff" here is `office` (its faculties),
`leader` and `admin`; a "step role" is `academic_office` or `dept_head` on the types that have a step for it, within its
scope (Task 46).

### Request types and form schema

`GET /api/services` returns `categories` (`key`, `seq`, `name`, `icon`, `color`, `text`) and `types`. A type has `code`, `category`, `name`, `icon`, `sla_hours`, `document` and `document_en` (title of the issued document, or `null` when the outcome is an answer instead of a document), `prefix` (registry prefix), `description`, `needs`, `outcome`, `privacy`, `steps` (workflow stage names), `step_roles` (the role id that does each step, Task 46), `effect` (what the last step changes: `none`, `document.issue`, `attendance.excuse` or `student_status.leave`), `enabled`, `attachments` (`label`, `required`, `max`, `accept`, or `null`), `answer` (only a type with an effect and no document has one), `popular` and `fields`.

Offer (Task 46). Only a type with `enabled = 1` is in this list, in search (`GET /api/search`) and on the campus
assistant's action buttons; `POST /api/requests` for a closed type answers `404`. A prod database gets the 13 types from
`backend/migrations/0461_request_types.sql` (texts identical to `content/seed.json`) with every type closed; the
administrator opens them on the University settings page (`PUT /api/admin/request-types/{code}`, written to the audit
log as `request_type_open` / `request_type_close`). A type whose `effect` is not registered in code cannot be opened
(`400`). The demo opens every type.

A field has `name`, `label`, `type` and optionally `required`, `options`, `show_if`, `min`, `max`, `future`, `placeholder`, `hint` and `hint_if`. Expected values:

| Field type | Value to send |
|---|---|
| `text`, `textarea` | String, up to 3,000 characters |
| `number` | Number or numeric string within `min` and `max` |
| `radio`, `select` | One of `options` (Azerbaijani or translated label) |
| `date` | `YYYY-MM-DD` |
| `daterange` | `{"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}`, at most 60 days; must start in the future when `future` is set and must not end in the future otherwise |
| `course` | Id of a course the student is enrolled in |
| `courses` | List of such ids |
| `absences` | List of lesson ids that are unexcused absences of the student within the `period` field's range |

The 13 request types, who does each step and what the last step changes:

| Code | Step roles | Effect |
|---|---|---|
| `enrollment_certificate` | `academic_office`, `academic_office` | `document.issue` |
| `transcript` | `academic_office`, `academic_office` | `document.issue` |
| `student_card` | `office`, `office` | `none` |
| `absence_excuse` | `office`, `office` | `attendance.excuse` |
| `leave_permission` | `office`, `office` | `none` |
| `exam_reschedule` | `office`, `dept_head`, `office` | `none` |
| `academic_leave` | `office`, `academic_office`, `academic_office` | `student_status.leave` (the order, then its extract) |
| `grade_appeal` | `office`, `academic_office`, `office` | `none` |
| `individual_plan` | `office`, `office`, `office` | `none` |
| `tuition_installment` | `academic_office`, `academic_office` | `none` |
| `social_scholarship` | `office`, `academic_office` | `none` |
| `dormitory` | `office`, `office` | `none` |
| `free_application` | `office` | `none` |

There is no role for an appeal or scholarship commission, the finance department or student services: those steps go to
the closest existing role (`academic_office` for the commissions and finance, `office` for student services).

### `POST /api/requests`

Body: `type_code`, `data` (an object keyed by field name), `files` (ids from `POST /api/files`, up to 10, within the type's `max`). The deadline is the submission time plus `sla_hours`. The holders of the first step's role whose scope covers the request are notified.

```http
POST /api/requests
Content-Type: application/json
X-Lang: en

{"type_code": "enrollment_certificate",
 "data": {"purpose": "Bank", "org": "Kapital Bank", "lang": "İngilis dili", "copies": "1", "delivery": "Elektron (QR kodlu PDF)"}}
```

```json
{
 "id": 34, "type_code": "enrollment_certificate", "student_id": 1,
 "data": {"purpose": "Bank", "lang": "English", "copies": "1", "delivery": "Electronic (PDF with QR code)", "purpose_other": "", "org": "Kapital Bank"},
 "status": "submitted", "step": 0,
 "created_at": "2026-11-05T05:58:04", "updated_at": "2026-11-05T05:58:04", "due_at": "2026-11-06T05:58:04",
 "document_id": null, "answer": null,
 "type_name": "Enrolment certificate", "icon": "file", "category": "docs",
 "steps": ["Academic office reviews", "Document is prepared and approved"], "step_roles": ["academic_office", "academic_office"],
 "step_role": "academic_office",
 "has_document": true, "student": "Aysel Məmmədova", "group": "İT-25-1", "student_color": "#2b5aa8",
 "sla_hours": 24, "summary": "Bank", "overdue": false, "hours_left": 24.0, "files": 0, "messages": 0
}
```

The stored values are canonical Azerbaijani; the response shows them translated. A validation error looks like this:

```json
{"error": "“Purpose of the certificate” must be selected"}
```

### Request statuses

`submitted`, `in_progress`, `returned`, `ready`, `rejected`, `cancelled`. Open statuses are the first three. `overdue` is true for an open request (other than `returned`) past its `due_at`.

### `GET /api/requests`

For students: all of their requests, newest first. An academic office or a department head sees the requests of the
types it has a step in, within its scope. For staff and step roles, query parameters: `status` (`open` by default, `done`, or any other value for all), `type` (type code), `category`, `q` (matches student name, request id or type name). The queue is ordered by status and deadline.

### `GET /api/requests/{id}`

The request as above plus `type` (full type definition), `data_view` (label and display value for each filled field), `events` (timeline: actor name, `actor_role` (the role the act was done in), `action`, `note`, `created_at`), `thread` (messages with author, role and colour), `attachments` and, once issued, `document` (`id`, `reg_no`, `verify_code`, `status`).

### `POST /api/requests/{id}/resubmit` and `/cancel`

Resubmit takes `data` (merged over the stored data and validated again) and `files` (added to the existing attachments); it is allowed only in status `returned` and answers `409` otherwise. Cancel is allowed in `submitted` and `returned`.

### `POST /api/requests/{id}/action`

Only the role the current step is assigned to (`step_roles[step]`) acts, within its scope: a dean's office for its
faculty's students, an academic office university-wide (its primary role or an unscoped grant) or for its granted
faculties, a department head for the course the request names. Another role answers `403`; `admin` is never a step role
(`403`); a request outside the role's scope answers `404`. Each act is a `request_events` row with the actor and the role.

| `action` | Allowed when | Effect |
|---|---|---|
| `approve` | Not returned, not on the last step | Status `in_progress`, step + 1; the student and the next step's role (within its scope) are notified |
| `return` | Open | Status `returned`; `note` required; student notified |
| `reject` | Open | Status `rejected`; `note` required; student notified |
| `issue` | Not returned, on the last step (`409` earlier) | Status `ready`; the type's `effect` runs in the same transaction; student notified |

Effects of `issue`: `document.issue` issues the type's document through the stored-payload path (Task 45);
`attendance.excuse` marks the selected absences `excused` in the journal (`journal.service.excuse`) and stores the type's
answer; `student_status.leave` needs `order_no`, `order_date` and `effective_date`, writes the status order
(`directory.service.record_status`) and issues its extract. A type whose effect is `none` changes nothing else and gets
one factual answer: "Müraciətiniz qeydə alınıb. Baxan bölmə: {unit}. Qərar: təmin edilib. Zəka-da başqa heç bir qeyd
dəyişməyib." (`unit` is the last step's role); `note` stays in the history. For `absence_excuse`, `leave_permission`
and `exam_reschedule` the teachers concerned are notified. Closed requests answer `409`. The response is the full request.

After issue, the response includes the document:

```json
{"document": {"id": 13, "reg_no": "AzTU-ARY-2026-000012", "verify_code": "2LTH-4XLR", "status": "valid"}}
```

### Documents

`GET /api/documents?q=<text>` searches registry number, holder name and title and returns `id`, `kind` (`request` or `certificate`), `title`, `reg_no`, `verify_code`, `issued_at`, `status` (`valid` or `revoked`), `revoked_reason` and `holder`.

`POST /api/documents/{id}/revoke` takes `{"reason": "..."}` (required, up to 500 characters); `404` for an unknown document
and for a document of a student outside the dean's office's faculties. The document list, the request list, the office
summary and the `office` badge apply the same faculty scope in SQL, before their limit. A request is read only by its
student, by `office`, `leader` and `admin`, and by the role a step of its type is assigned to, within that role's scope
(Task 46; with the request's attachments and issued document); posting a message or an action on someone else's request, and opening a
document preview, is an audited read.

An issued document is stored as it was at issue (Task 45). `documents.payload` is canonical JSON (sorted keys, no
spaces) with the title, registry number, verification code, issue time, the request's fields and a snapshot of the
holder (name, group, course, faculty, specialty), the issuer, the university and, for a transcript, its final grades;
`documents.hash` is its SHA-256. `/doc/{id}` and `/verify/{code}` render only from the payload, never from live rows, so
a later change of name, group or grade does not change an issued document. `/verify` recomputes the hash and compares it
in constant time: a mismatch shows "Sənəd dəyişdirilib" and no "SHA-256 ✓"; a document issued before payloads were
stored shows "Bu sənəd doğrulanmır" and `/doc` does not rebuild it. Limit: the hash has no key and lives in the same
database as the payload, so someone who can write to the database can change both. Registry numbers come from
`doc_sequences(prefix, year, last_no)`, incremented in the issuing transaction; a deleted or revoked document does not
give its number back.

`POST /api/documents/{id}/link` returns a one-time URL, valid for five minutes; `404` when the document does not exist or belongs to someone else:

```json
{"url": "/doc/13?k=kQFAz1cbzpw8vYrHxi6Ziu6x"}
```

## Exams (Tasks 26–27)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `POST` | `/api/courses/{id}/exams` | the course's teachers | Set an exam: `title`, `kind` (main, retake, individual), `day`, `start`, `end` (local time), `duration_min`, `plan` (`[{difficulty, topic, count}]` over the course's exam questions) |
| `GET` | `/api/courses/{id}/exams` | the course's teachers, those who read its journal (a department head whose grant covers the course, the registry offices, leadership); an enrolled student | The course's exams; a student sees the open and closed ones with `roster` and `attempt` status |
| `GET` | `/api/exams/{id}/manage` | the course's teachers, those who read its journal (as above; a dean's office: its faculties' students) | The exam, its roster and its attempts |
| `POST` | `/api/exams/{id}/open` | the course's teachers | Open the exam: the roster is drawn once from the course's students; one the journal does not admit is on it as `excluded` |
| `POST` | `/api/exams/{id}/close` | the course's teachers | Submit what is still running, grade every attempt with the engine, close |
| `POST` | `/api/exams/{id}/roster/{sid}/exception` | `office` (its faculties), `academic_office`, `admin` | Let a student sit the exam despite the roster, with `{"reason"}`; only while the exam is open (`409`); audited |
| `POST` | `/api/exams/{id}/enter` | an enrolled student | Enter the exam: every session of the student ends and a new one, scoped to this exam, is set in the cookie; `{"ok": true, "url": "/static/exam.html?exam={id}"}` |
| `POST` | `/api/exams/{id}/leave` | the exam's session | End the exam session and expire its cookie; `409` while the student's attempt is running (submit first) |
| `GET` | `/api/exams/{id}` | the exam's session | The exam, the student's roster status and, once started, the student's own form and saved answers and `remaining_s` |
| `POST` | `/api/exams/{id}/start` | the exam's session, a student on the roster | Start, or get back, the attempt; off the roster `403` with the reason (the refusal is in the exam log) |
| `PUT` | `/api/exams/{id}/answers/{qid}` | the exam's session | Save one answer (`{"value"}`); after the deadline by the server's clock `409` |
| `POST` | `/api/exams/{id}/submit` | the exam's session | Submit; the page's own submit at the deadline sends `{"auto": true}`, refused with `409` while time is left by the server's clock or the attempt is paused |

A question's `purpose` (`practice` or `exam`, `PUT /api/questions/{id}`) is chosen by the time it is first approved and
then fixed (`400`). An approved exam question does not go back to draft (`400`), and while an exam of its course is
open it is neither changed nor deleted (`409`); each change and deletion of an exam question is audited. An exam question is never in the tutor's or Radar's index, never in practice and never in a test
(`400`); a student sees it only in their own attempt, with the keys `id`, `qtype`, `text`, `options`, `unit` and
nothing else (`tests/security/test_exam_item_leak.py`). A form is drawn by the plan with a seed of the exam's secret
and the student: the same every time, different between students; a multiple-choice question's options are shuffled
and an answer is the index of the option as shown. Times are stored in UTC: 10:00–12:00 in Baku opens at
`06:00:00+00:00`. An attempt ends at its duration or at the window's end; the periodic job `exam.autosubmit` (every
minute) submits it without the student. Every step is a row in `exam_events` (Task 30 adds its hash chain). The roster
keeps the group each student was in when it was drawn: a later move to another group does not move the student's
result to another statement. A refusal (`session.refused`, `attempt.refused`, `seb.refused`) is logged at most 10 times
per student, exam and kind; the `403` itself is always given. Entering an exam that is not open is refused before
anything is logged; a student whose attempt was extended past the window may enter again until it ends.

The exam session (Task 27). The routes marked "the exam's session" are declared `@R(..., scope="exam")` and open
only to a session whose scope is `exam:{id}` of the same exam: an ordinary session, and the session of another exam,
get `403`. An exam session gets `403` on every other route (`tests/security/test_exam_scope.py` walks the route
table). Entering ends all of the student's sessions in the same request (event `session.entered`, or
`session.takeover` when an earlier exam session was ended). A sign-in during the attempt does not end the exam
session and cannot reach the exam (event `login.during_exam`). The page `/static/exam.html?exam={id}` has no
navigation; it saves each answer when it changes and every 20 seconds, keeps unsent answers in `localStorage` while
offline (in memory, with a warning not to close the page, when the browser refuses storage) and sends them when the
connection is back, goes on after a reload, and counts the timer from the server's
`remaining_s` on the browser's monotonic clock, so a wrong system clock does not move the deadline
(`tests/e2e/exam_offline.js`, run by `tests/integration/test_exam_page.py` when node with Playwright is installed).
An answer the server refuses as invalid (`400`, `404`) is dropped; one refused after the deadline is dropped and counted
on the final card; a `401`/`403` reloads the exam; any other failure keeps the answer queued. A manual submit waits for
the queue and is refused on the page while answers are still unsent.

The exam log is one hash chain per exam (Task 30): `seq` 1..N without a gap, `hash = sha256(prev_hash + canonical
event)`, the first `prev_hash` is 64 zeros; an append reads the head and writes the next link under the write lock
(`BEGIN IMMEDIATE`). A submission (by the student, the periodic job, the closing teacher or a proctor) is an
`attempt.submitted` event with `attempt_id`, `auto`, `form_seed` and `answers_sha256` (the SHA-256 of the canonical
JSON of the `(qid, stored value)` pairs ordered by `qid`); closing writes `attempt.graded` (`attempt_id`, `score`,
`max_score`) for each attempt and then `exam.closed`. `python backend/manage.py exam-verify <id> [--root <hex>]` checks
every link, each submitted attempt's answers against its last submission event, each graded score against its last
grading event and, given, the head against the root; it prints the first broken link and every changed attempt and
exits 1 (0 when all holds, 2 when there is no such exam). The problems it names: a broken `chain` link;
`submission_after_close` and `grading_after_close` events; per attempt `attempt_missing`, `student_changed`,
`status_changed`, `no_submission_event`, `answers_changed`, `form_changed` (the event carries `form_sha256`),
`no_grading_event`, `score_changed` (score or `max_score`); per anchor document `anchor_missing`, `anchor_unreadable`,
`root_differs` (read from the document's hashed payload); and `not_in_chain` for a `--root` that is no link of the chain.
`exam_events` is append-only in the database too (migration `0301`: an `UPDATE` or `DELETE` aborts); someone with the
database file can still drop the triggers, so the e-mailed root is the real guard.

### Protocol, release and statements (Task 30)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `POST` | `/api/exams/{id}/release` | the course's teachers | Release a closed exam: each graded attempt's raw score (clamped to its maximum), scaled to the exam component (`exam/domain.scale`, half up to one decimal), is published in the journal with `exam_id` and `attempt_no`; an earlier published score goes to the grade journal; a student without a graded attempt gets nothing; audited; the students are notified. Answer: `{"ok", "released": n, "skipped": [{"student_id", "reason": "statement_closed" or "newer_exam", "exam_id"}]}` |
| `GET` | `/api/exams/{id}/results` | the course's teachers, staff (a dean's office: its students) | Each roster student's `raw`, `points`, `semester`, `total`, `letter` and `status`: `passed`, `exam_min`, `pass_mark`, `not_admitted`, `absent` |
| `GET` | `/api/courses/{id}/exam-results` | as above | Every released exam of the course with its results: a retake next to the first attempt |
| `GET` | `/api/exams/{id}/statements` | as above | The groups of a released exam and whether each statement is closed (with its document) |
| `GET` | `/api/exam-statements` | `office`, `academic_office`, `admin` | Released exams with a group the user serves, and how many statements are closed |
| `POST` | `/api/exams/{id}/statements/{gid}/close` | `office` (its faculties), `academic_office`, `admin` | Close a group's statement: a QR document (`exam_statement`) with the results and the chain's head; once (`409`) |
| `PUT` | `/api/exams/{id}/scores/{sid}` | `office` | After the statement is closed: `score`, `reason` and `appeal_id` (a `grade_appeal` request of the student, not rejected or cancelled, used once) or `order_no` (with at least one digit); written to the journal and the grade journal, `score.changed` in the exam log; the attempt is not changed; answer `{"ok", "score"}`. Before the statement is closed `409`, and `409` when the journal's exam score of the student comes from another exam; from then on the journal refuses the teacher's change of that cell (`403`) |
| `GET` | `/api/exams/{id}/analysis` | the course's teachers only | Each question's share of correct answers and commonest wrong answers; pairs of students with the same wrong answers to at least two questions (a signal, not a verdict) |

Closing an exam issues the protocol (`exam_protocol`, a QR document through Task 45's stored payload: facts, counts,
incidents, the proctors' actions, `seq` and `root` of the chain at closing) and queues the root by e-mail
(`exam.root`) to the course's teacher and the dean's offices of the roster's groups; release, each closed statement and
each changed score mail the new root too, with the stage and `seq` (an audit row `exam_root_mailed`, or
`exam_root_not_mailed` when no recipient has an address). The verification page of the
protocol and of a statement shows the full root. `exam-verify` also checks that the event at each printed `seq` still
has the printed root, and `--root` passes when the given root is a link of the chain.

### Safe Exam Browser (Task 28)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/exam/{id}/config.seb?k={token}` | anyone with the exam's token (SEB fetches it itself) | The exam's `.seb` file (`application/seb`): start at the portal, only this host, keys sent, no VM, clipboard or screen capture, the quit password hashed |
| `POST` | `/api/exams/{id}/seb-verify?n={value}` | the exam's session | Marks the session verified when SEB's hash is right: the `X-SafeExamBrowser-ConfigKeyHash` header over `PUBLIC_URL` + this request's raw target, or `{"url", "config_key_hash"}` from the JS API over the page URL; both must carry the session's one-time value `n`. A refusal is `403` and a `seb.refused` event; a success ends the student's other exam sessions (`session.takeover`) |

An exam with `"protection": "seb"` hands out a launch link (`sebs://` for https, `seb://` for http) to its students
(`seb_link` in the course's exam list) and shows the teacher the link, the Config Key and the quit password
(`seb` in the manage view; all derived from the exam's secret, nothing stored). Entering such an exam adds the
session's one-time value to the page URL (`&n=`); until the session is verified, the exam's routes other than
`seb-verify` and `leave` answer `403`, so no question is shown and no attempt starts. The Config Key follows SEB's
rules (`exam/seb.py`); it was checked against two real SEB files with known keys. What it proves: the client knows the
configuration. It does not prove an unmodified SEB.

### Proctor panel (Task 29)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/api/proctor/exams` | `proctor`, `teacher`, `dept_head`, `academic_office`, `admin` | Exams to watch: assigned ones; for a teacher the open exams of the courses they head; for the academic office and the administrator every open exam |
| `PUT` | `/api/exams/{id}/proctors` | the course's teachers, `academic_office`, `admin` | Assign proctors with `{"usernames": [...]}` (active staff only, at most 20); replaces the list; in the exam log and audited |
| `GET` | `/api/exams/{id}/board?after={seq}` | the exam's proctors, the course's teachers, `academic_office`, `admin` | Every student on the roster: `attempt`, `answered`/`total`, `remaining_s`, `online`, `seen_s`, `ip`, `flags` (counts of `client.blur`, `client.fullscreen_exit`, `client.reconnect`, `net.changed`, `net.refused`, `login.during_exam`); `events` after `seq` (at most 100) and the new `seq`. The page polls it every 5 seconds |
| `POST` | `/api/exams/{id}/students/{sid}/{action}` | as the board | `extend` (`minutes` 1–240), `pause`, `resume`, `end`, `reopen` (`minutes` from now), `unlock` (the student's sign-in lock, only while the exam is open); `reason` (3–300 characters) is required; only for a student on this exam's roster (`404` otherwise); a wrong state is `409`. Each is a `proctor.{action}` event with the reason and an audit row; the answer is the board |
| `POST` | `/api/exams/{id}/signals` | the exam's session | `{"kind": "blur" | "fullscreen_exit" | "reconnect"}` from the exam page; at most 300 of each kind per student and exam (`{"kept": false}` beyond); none once the exam is closed |

A paused attempt takes no answers (`409`, the page keeps them queued) and its clock stands still: resuming moves the
deadline by the pause; the periodic submission skips it. The network list (`allowed_cidrs` of the exam, set when it
is created) is checked when a student enters and on every exam-session request: an address off the list gets `403`
and a `session.refused` or `net.refused` event; a change of address on the list is a `net.changed` event. The address
is `client_ip()`: with `ZEKA_PROXY_HOPS=1` the right-most `X-Forwarded-For` entry, with `0` the peer address.

## E-mail notifications (Task 36)

| Method | Path | Who | Purpose |
|---|---|---|---|
| `GET` | `/api/me/notifications` | everyone signed in | `address`, `relay` (whether the university has set a relay) and each notification `kind` with its `label` and `email` (on or off) |
| `PUT` | `/api/me/notifications` | everyone signed in | `{"email": {kind: bool}}` for known kinds (`400` otherwise); merged into the person's settings |

News, events, practice tests, the academy and Radar digests start off; every other kind starts on. A notification is
queued as an e-mail (table `outbox`) in the same transaction, in the recipient's language; the periodic job
`outbox.send` sends what is due, tries a failed message again after 1, 2, 4, ... minutes (at most six hours, eight
attempts) and stops a run after one attempt at a relay that is down or silent (15 s socket timeout).

## News and events

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/news` | any | Published news for the user's audience |
| `GET` | `/api/news/{id}` | any | One news item with body, author, read count and related items; marks it as read |
| `POST` | `/api/news/{id}/rsvp` | any | Register for an event, or cancel the registration |
| `POST` | `/api/news/{id}/save` | any | Bookmark, or remove the bookmark |
| `GET` | `/api/news/{id}/ics` | any | Event as an iCalendar file |
| `GET` | `/api/news/manage` | staff | All news including drafts |
| `POST` | `/api/news` | staff | Create a news item or event |
| `PUT` | `/api/news/{id}` | staff | Update a news item |
| `DELETE` | `/api/news/{id}` | `leader`, `admin` | Delete a news item with its registrations, bookmarks and read marks |

Audience: students see `all` and `students`, teachers see `all` and `teachers`, staff see everything. Kinds: `news`, `event`, `announcement`, `opportunity`, `career`, `campus`.

**`GET /api/news`** accepts `kind`, `q` (title, summary or tag), `saved=1`, `mine=1` (events the user registered for). Response: `items`, `upcoming` (next 6 events), `kinds` and `unread`. Each item has `id`, `kind`, `title`, `summary`, `audience`, `published_at`, `event_start`, `event_end`, `location`, `capacity`, `status`, `cover`, `tags`, `pinned`, `important`, `registration`, `registered_count`, `registered`, `saved`, `read` and `past`.

**`POST /api/news/{id}/rsvp`** toggles the registration. `400` when the item does not take registrations, `409` when the event has ended or is full.

**`GET /api/news/{id}/ics`** returns `text/calendar` with one event in the `Asia/Baku` time zone; `400` when the item is not an event.

**`POST /api/news` and `PUT /api/news/{id}`.**

| Field | Notes |
|---|---|
| `title` | Required, at least 5 characters |
| `summary` | Required, up to 400 characters |
| `body` | Up to 8,000 characters |
| `kind` | One of the kinds above, default `news` |
| `audience` | `all`, `students` or `teachers`, default `all` |
| `pinned`, `important`, `draft` | Booleans |
| `icon`, `tone` | Cover icon name and colour tone (`navy`, `blue`, `coral`, `green`, `amber`, `violet`, `teal`) |
| `tags` | Comma-separated string, up to 6 tags |
| `event_start` | ISO date-time; makes the item an event |
| `duration_h` | Event length in hours, 0.5 to 72, default 2 |
| `location`, `capacity`, `registration` | Event details; `capacity` 0 to 100,000, 0 means unlimited |

`PUT` takes the same body as `POST` and replaces every field, so send the complete item. Publishing an item marked `important` notifies every student or teacher in its audience; on update this happens only when the item was a draft before.

## AI Academy, tools and syllabus

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/academy` | `teacher` | Tracks with modules and progress, hours, certificates, self-assessment and recommended tracks |
| `PUT` | `/api/academy/assessment` | `teacher` | Save the self-assessment |
| `GET` | `/api/academy/module/{id}` | `teacher` | Module content and quiz questions without answers |
| `POST` | `/api/academy/module/{id}/complete` | `teacher` | Submit the module quiz |
| `GET` | `/api/tools` | `teacher`, `leader`, `admin` | Teaching tool catalogue, subject areas and the teacher's courses with their tools |
| `POST` | `/api/courses/{id}/tools` | `teacher` | Attach a tool to a course, or detach it |
| `GET` | `/api/syllabi/{id}` | staff who read the course | The structured syllabus: versions, the latest and the published one, Forma №3 hours, their difference (Task 23) |
| `POST` | `/api/syllabi/{id}/draft` | the course's head teacher | A first draft, not saved: from a syllabus saved before Task 23, else from the assistant, with Forma №3 hours |
| `PUT` | `/api/syllabi/{id}` | the course's head teacher | Save as a new draft version (`{"data": ..., "base": <version>}`; `409` when a newer version exists) |
| `GET` | `/api/syllabi/{id}/versions/{vid}` | staff who read the course | One version's data |
| `POST` | `/api/syllabi/{id}/versions/{vid}/submit` | the course's head teacher | draft → submitted (the latest version only) |
| `POST` | `/api/syllabi/{id}/versions/{vid}/approve` | `dept_head` whose grant covers the course | submitted → approved |
| `POST` | `/api/syllabi/{id}/versions/{vid}/publish` | `academic_office` | approved → published; configures the course (see below) |
| `POST` | `/api/syllabi/{id}/versions/{vid}/return` | `dept_head` (submitted), `academic_office` (approved) | → returned, with `{"note"}` (required) |
| `GET` | `/api/syllabi/queue` | `dept_head`, `academic_office`, `admin` | Versions waiting for this role, with their Forma №3 difference and the count of changes from the published version |
| `GET` | `/api/syllabi/{id}/diff?a=&b=` | staff who read the course | What changed from version `a` to `b`, by section |
| `GET` | `/api/courses/{id}/syllabus` | the course's students and readers | `{"published": <version or null>}` |
| `POST` | `/api/syllabus/{cid}/generate` | `teacher` | The syllabus assistant's output (the first draft's source) |
| `POST` | `/api/syllabus/{cid}/link` | `teacher` | One-time link to the printable syllabus |
| `GET` | `/api/frameworks` | staff | Every framework version (Task 24): built-in Bloom and EQF first, then each key's newest version first |
| `GET` | `/api/frameworks/{id}/items?q=&kind=&role=&page=&size=` | staff | One page of a framework's items, searched on the server |
| `GET` | `/api/syllabi/{id}/frameworks` | staff who read the course | The course's outcome map: `{"outcomes": {"N1": [<item>, ...]}, "can_map"}` |
| `PUT` | `/api/syllabi/{id}/outcomes/{oid}/items` | a teacher of the course | Replace one outcome's framework items: `{"items": [<item id>, ...]}` |
| `GET` | `/api/frameworks/programmes` | `dept_head`, `academic_office` (their scope), `leader`, `admin` | The programmes (specialties) the caller's report covers |
| `GET` | `/api/frameworks/coverage?programme=&framework=&role=` | `dept_head`, `academic_office` (their scope), `leader`, `admin` | A programme's coverage report; `&format=csv` for the spreadsheet |

**`PUT /api/academy/assessment`.** Body: `{"values": {"<track key>": 1..5}}`. Track keys: `ai`, `emi`, `syllabus`, `communication`, `pedagogy`, `research`, `edtech`. Recommended tracks are the three lowest-rated tracks that are not complete. Returns the same object as `GET /api/academy`.

**`POST /api/academy/module/{id}/complete`.** Body: `{"answers": [<option index>, ...]}` in question order. Response: `passed` (score of 50% or more), `score`, `correct` and `certificate`. After a pass, `correct` lists the correct option index of every question; after a fail, only the indices the teacher already answered correctly, and `null` for the others. When the last module of a track is passed, a certificate document is issued and returned as `{id, reg_no, verify_code}`; otherwise `certificate` is `null`.

**`POST /api/courses/{id}/tools`.** Body: `{"tool_key": "<key>"}`. Response: `{"on": <bool>, "tools": [<keys>]}`.

**`POST /api/syllabus/{cid}/generate`.** Body: `{"weeks": 10..18}`, default 15. Returns `course`, `description`, `workload`, `outcomes` (up to 6, derived from glossary terms of each material), `plan` (one row per week with colloquia in weeks 7 and 13 and revision in the last week), `assessment`, `materials`, `tools`, `policies` and `generated_at`. The structured syllabus (Task 23) is JSON with `description`, `outcomes` (`id` N1…N20, `text` 10–500 characters,
`bloom`: remember, understand, apply, analyze, evaluate, create), `plan` (`week` 1–30, `topic`, `outcomes` it serves,
`activity`), `assessment` (`name`, `kind`: component, attendance or exam, `weight`), `rules` (`attendance_limit` in
percent, `late_policy`, `ai_policy`: allowed, limited or forbidden, `ai_note`), `prerequisites`, `literature` (`title`,
`kind`: main or extra) and `workload` (`lecture`, `seminar`, `lab`, `independent` hours). A save is refused with `400`
when the weights do not add up to 100, when the exam does not weigh the university's exam maximum, or when the
attendance limit is above the university's (a syllabus may only lower it). Every save is a new version with status
`draft`; a version never changes afterwards. Forma №3 hours are the largest unit of each kind among the course's active
teaching units; `diff` lists the kinds whose syllabus hours differ from them.

The approval chain (Task 25): only the next role moves a version on (`actions` in `GET /api/syllabi/{id}` lists the steps
this user may take; a wrong role or status is `403`). Each step is a row in `syllabus_steps` and an audit entry; a
return notifies the author with the comment, and the teacher saves and submits a new version. Publication writes the
course's grading scheme (its components and exam; the pass mark, the scale and the exam minimum stay the university's),
`courses.attendance_limit` (the journal applies the lower of the university's and the syllabus's limit) and the tutor
modes from the AI policy (`allowed`: Socratic, explain, practice; `limited`: Socratic and practice; `forbidden`:
Socratic only, locked), and recomputes the course's final grades. A course that already has scores is published only
with `{"override": true, "note": "<reason>"}` from the academic office (`409` otherwise; an audit entry
`syllabus_publish_override`). Scores of components the new scheme no longer has stay in the database but are not
shown. A student reads only the published version (`GET /api/courses/{id}/syllabus`, `/syllabus/{id}`).

**Frameworks (Task 24).** A framework is a version of a published reference: `frameworks` (key, version, title, source,
SHA-256, items per kind), `framework_items` (code, kind, parent, title, text) and `framework_links` (the source's
relationships). NICE Framework Components come from the unchanged NIST file (`content/frameworks/README.md`) through
`python backend/manage.py import-framework --file <file>`: every element is an item of its own type (work_role, task,
knowledge, skill, competency_area, category, opm_code, sort) and every relationship a link; a work role's `parent` is its
category. The command prints the rows per kind beside the file's element counts and exits `1` when they differ. A second
run changes nothing; a version is never re-imported from a different file; a known version (2.2.0) whose SHA-256 differs
from the file NIST published is refused; a version not in `KNOWN` imports unverified (`verified: false`, no
`source_url`, listed after the verified versions of its key and never the default); a newer version is a new row, and the older one with its items and maps stays
readable. Bloom (revised, 2001: six levels) and EQF (2017: eight levels with their knowledge, skill and responsibility
descriptors) are built in and written at every start, prod included; their Azerbaijani and Russian texts are working
translations (`note`).

Each framework in `GET /api/frameworks` has `counts` and `kinds` (`kind`, `label`, `count`, `mappable`). An item is
`{id, code, kind, parent, title, text, label}`. `GET /api/frameworks/{id}/items`: `q` (up to 100 characters) is found in
the code, title or text (`%` and `_` are literal), `kind` filters, `role` (a work role's code) limits the page to the
items that role links to, `size` is 1–100 (default 20); the answer is `{framework, items, page, more}`; an unknown
framework or role is `404`.

The outcome map's key is the course and the outcome's code (`N1` …), which every new version of the syllabus keeps; each
row records who mapped it and when (`outcome_items`). A saved version without an outcome drops that outcome's items, so
a later outcome given the same code starts empty (the editor also never reuses a code that still has items). Submitting
a version copies the map into it (`syllabus_versions.tags`): the department head approves, the academic office publishes
and the printed page and the coverage report show that copy, and a later change of the map reaches only the next
submitted version. `PUT /api/syllabi/{id}/outcomes/{oid}/items` takes up to 50
different items of any frameworks, of a mappable kind (task, knowledge, skill, level, responsibility; `400` otherwise),
for an outcome of the latest saved version (`404` otherwise). Only the course's head teacher and the teachers of its
active units map; anyone else gets `404`. The printable syllabus lists each outcome's items read-only; a student sees
them on the published version.

`GET /api/frameworks/coverage`: a programme is a specialty; its courses are those with an active teaching unit for one
of its groups; an outcome counts in the published syllabus with the map it was submitted with, else, for a caller who
may read the course's syllabus, in the latest version with the current map. `framework` defaults to the newest
verified NICE version (an unverified one only when no verified one exists). The answer: `programme`, `framework`, `courses`, `outcomes`, `labels`, `roles` (per work role: `code`,
`title`, `category`, `kinds` with `total` and `covered` for task, knowledge and skill, `total`, `covered`) and, with
`role=<code>`, `role.statements` (`code`, `kind`, `text`, `covered_by`: the course and outcome of each covering
outcome; an empty list is an uncovered statement). `&format=csv`: one row per work role and statement (UTF-8 with a BOM),
headers in the caller's language. A department head and the academic office read the programmes of their grants (an
unscoped grant: all; a faculty or department grant: that faculty's or department's programmes); a programme, framework or
role outside that is `404`.

## Support desk and feedback

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/support/meta` | any | Categories, priorities with SLA hours, statuses, feedback areas, score labels, and whether the user works the desk |
| `GET` | `/api/support/tickets` | any | The user's tickets, or the whole queue for the desk |
| `POST` | `/api/support/tickets` | any | Open a ticket |
| `GET` | `/api/support/tickets/{id}` | owner, `office`, `admin`, `leader` | Ticket with thread and allowed actions |
| `POST` | `/api/support/tickets/{id}/messages` | owner, `office`, `admin` | Reply |
| `POST` | `/api/support/tickets/{id}/status` | `office`, `admin` | Change status or priority, assign to self |
| `POST` | `/api/support/tickets/{id}/rate` | owner | Rate a resolved or closed ticket |
| `POST` | `/api/support/tickets/{id}/reopen` | owner | Reopen a resolved or closed ticket |
| `GET` | `/api/support/summary` | staff | Ticket counts, overdue tickets, average first response time, CSAT, tickets per category |
| `POST` | `/api/feedback` | any | Submit feedback |
| `GET` | `/api/feedback/summary` | staff | Average, distribution, NPS, weekly trend, scores by area, recent comments |

Vocabularies:

| Kind | Values |
|---|---|
| Category | `account`, `learning`, `ai`, `services`, `technical`, `suggestion`, `university`, `other` |
| Priority and target first response | `urgent` 4 h, `high` 8 h, `normal` 24 h, `low` 72 h |
| Status | `open`, `in_progress`, `waiting` (waiting for the user), `resolved`, `closed` |
| Feedback area | `overall`, `tutor`, `services`, `schedule`, `quizzes`, `news`, `academy`, `design`, `mobile` |

**`GET /api/support/tickets`.** Query: `scope=all` (desk and leader only; otherwise the user's own tickets), `status` (`open` for the three open statuses, `done` for resolved and closed, or one status code), `category`, `mine=1` (assigned to the caller, desk only), `q` (subject, user name or exact id). Each ticket has `id`, `category`, `priority`, `subject`, `body`, `page`, `status`, `rating`, timestamps, `user`, `user_role`, `user_color`, `assignee`, `assignee_id`, `mine`, `due_at`, `first_response_at`, `overdue` and `messages`.

**`POST /api/support/tickets`.** Body: `category` and `priority` (invalid values fall back to `other` and `normal`), `subject` (4 to 140 characters), `body` (10 to 4,000 characters), `page` (where the problem happened), `file_id` (optional upload). The desk is notified. Returns the ticket as `GET /api/support/tickets/{id}` does.

**`GET /api/support/tickets/{id}`** adds `thread` (internal notes are included only for `office` and `admin`) and the flags `can_reply`, `can_manage`, `can_rate` and `can_reopen`.

**`POST /api/support/tickets/{id}/messages`.** Body: `text` (required), `internal` (desk only; the note is hidden from the user), `status` (desk only: `in_progress`, `waiting` or `resolved`). A desk reply without a status moves an `open` ticket to `in_progress` and assigns it to the replier; a user reply moves a `waiting` or `resolved` ticket back to `in_progress`. `409` on a closed ticket.

**`POST /api/support/tickets/{id}/status`.** Body: any of `status` (one of the status codes), `priority`, `assign: "me"`. Resolving, closing or setting `waiting` notifies the user.

**`POST /api/feedback`.** Body: `score` (1 to 5, required), `nps` (0 to 10, optional), `area` (default `overall`), `comment` (up to 2,000 characters), `page`. The interface language is stored with the feedback.

**`GET /api/feedback/summary`.** Returns `count`, `avg`, `distribution` (counts for scores 1 to 5), `nps` (percentage of 9–10 minus percentage of 0–6), `nps_responses`, `weekly` (8 weeks of `n` and `avg`), `by_area`, `recent` (last 12 comments with a `synthetic` flag) and `labels`.

## Analytics and administration

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/analytics` | `leader`, `admin` | Leadership dashboard data |
| `GET` | `/api/admin/status` | `admin` | Engine and LLM configuration (without the key), limits, row counts, data paths |
| `PUT` | `/api/admin/settings` | `admin` | Update platform limits |
| `POST` | `/api/admin/test-llm` | `admin` | Send a short prompt to the configured LLM |
| `GET` | `/api/admin/audit` | `admin`, `leader` | Last 200 audit log entries |
| `GET` | `/api/insight/evidence` | `leader`, `admin` | Accreditation evidence: live counts per indicator; `?format=csv` |
| `POST` | `/api/admin/reset` | `admin` | Delete all data and reseed the demo |
| `GET` | `/api/system/status` | any | Status of the platform components |

**`GET /api/analytics`** returns `labels` (8 week labels), `wau_students`, `wau_teachers`, `active_by_role` (distinct active users of the last 7 days per role), `tutor_questions`, `request_hours`, `kpis`, `courses` (per course: tutor questions, test average, no-source rate, positive rate, attendance), `insights` (the first one is the Zəka Radar summary, with a `link` to `/radar`), `office` (as `/api/office/summary`), `requests_by_type`, `news` (5 most read), `attendance`, `ai` (`cited_rate` is the `cited` tile, `positive_rate`, `messages`) and `totals`. `kpis` are the measured indicators of the insight module (Task 39), each with `key` (`wau_student`, `wau_teacher`, `journal`, `request_hours`, `request_sla`, `cited`, `exams`, `academy`), `label`, `definition`, `unit` (`pct`, `hours`, `count`), `value` (null when its period has nothing to measure), `series` (8 weekly values, oldest first), `target`, `lower` (a smaller value is better), `ok` and `range` (`from`, `to`; `from` is null for the running total of `academy`).

**`GET /api/insight/evidence`** (leader, admin) returns `range` (the last 30 days) and `indicators`: for each accreditation indicator (3.5.1, 3.5.3, 5.4.2–5.4.8) its `code`, `title`, `note`, `measures` (`key`, `label`, `value`, `range`; `range.from` is null for a count that is not limited to the period) and `links` (pages of the portal, only those the caller's role can open). `?format=csv` returns the same as a spreadsheet, one row per measure, in the language of `?lang=`.

**`PUT /api/admin/settings`.** Body: any of `daily_messages` (5 to 500), `pii_masking` (boolean), `socratic_default` (boolean), `retention_days` (30 to 3,650). Saving deletes chat messages older than `retention_days`. Returns the stored limits. `socratic_default` is stored but does not affect behaviour in this version.

**`POST /api/admin/test-llm`.** Response: `{"ok": <bool>, "message": "..."}`; when no LLM is configured, `ok` is false and the message says the demo engine is in use. An error message never contains the API key.

**`GET /api/system/status`** (any signed-in user) returns `components` (`portal`, `db`, `ai`, `notify`, `sso`, `lms`, each with `status` `operational`, `degraded`, `down` or `planned`, a `name` and a `note`), `checked_at`, `uptime_s` and `overall`. The `ai` component is `degraded` while the offline engine is in use, and `sso` and `lms` are `planned`.

**`POST /api/admin/reset`.** Demo mode only. Deletes every row except the schema migration log, including all sessions, reseeds the demo data and rebuilds the indexes. Response: `{"ok": true}` with an expired session cookie.

## Zəka Radar

Early warning: a risk score per student and course from attendance, grades, test attempts and tutor activity, the reasons behind it, and support plans that a teacher or the dean's office sends to the student.

Tutor activity (the counts and topics of tutor questions and practice answers, never their text) is read only for a student with a current `ai` consent (Privacy above). Without it that part is left out: no engagement points for "no tutor questions", the student is not counted in the course's median of tutor questions, and a plan has no `practice` or `tutor` step and its `read` steps link to the course page instead of the tutor. Refusing or withdrawing the consent never raises the score.

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/radar` | `teacher`, `office`, `leader`, `admin` | Dashboard for the courses in scope |
| `GET` | `/api/radar/student/{sid}` | `teacher`, `office`, `leader`, `admin`, with student access | Risk profile of one student in one course |
| `POST` | `/api/radar/student/{sid}/plan` | `teacher`, `office`, `admin`, with student access | Preview or send a support plan |
| `POST` | `/api/interventions/{id}/status` | `teacher`, `office`, `admin`, plan in scope | Close a plan as completed or cancelled |
| `GET` | `/api/student/plans` | `student` | The student's support plans |
| `GET` | `/api/student/plans/{id}` | `student`, own plan | One support plan |
| `POST` | `/api/student/plans/{id}/steps` | `student`, own plan | Mark a step done or not done |
| `GET` | `/api/demo/storyline` | public, demo mode only | Ids of the demo storyline students and their course |

Scope: a teacher sees the courses they teach (`403` when they teach none); `office`, `leader` and `admin` see all courses. Student access means the student exists (`404` otherwise) and is enrolled in a course in scope (`403` otherwise). Students never see a risk score on screen: the student endpoints leave out `risk_before`, `level_before` and `drivers`. The student's own data export (`GET /api/me/export`) does include them (the owner's decision of 2026-11-21, Privacy above).

Reading a plan (any endpoint that returns one) first ticks open steps that the student's activity since the plan was sent has completed, and closes the plan as `completed` when every step is done; the plan's author is then notified.

### `GET /api/radar?course=<id>`

`course` narrows the view to one course in scope; without it a teacher sees all their courses and staff see all courses.

| Field | Content |
|---|---|
| `scope` | `role`, `courses` (the courses in scope: `id`, `code`, `name`, `color`, `teacher_id`, `teacher`), `selected` (the course id when one course is shown, else `null`), `can_act` (may create and close plans) |
| `counts` | `high`, `watch`, `ok`, `students` |
| `course_counts` | Per course: `id`, `code`, `name`, `color`, `students`, `high`, `watch`, `ok` |
| `rows` | One row per student, highest score first (fields below) |
| `gaps` | Topics several at-risk students struggle with: `course_id`, `code`, `course`, `color`, `topic`, `students`, `chunk_id` and `material` of the best matching passage |
| `drivers` | How many at-risk students have each top driver: `key`, `label`, `n` |
| `trend` | Weekly `week_start`, `high`, `watch`, `ok`; past weeks from stored snapshots, the last entry is live |
| `impact` | `plans`, `open`, `completed`, `measured` (plans older than seven days), `improved`, `avg_delta` and up to 12 `items` (`risk_before`, `level_before`, `risk_now`, `level_now`, `delta`, `improved`, `progress`, …) |
| `model` | `weights` (`attendance` 30, `assessment` 30, `concept` 25, `engagement` 15) and `levels` (`high` from 50, `watch` from 30) |
| `generated_at` | Timestamp |

A row has `id`, `name`, `color`, `group`, `score` (0 to 100, the student's highest course score), `level` (`high`, `watch` or `ok`), `level_label`, `course_id`, `top_driver`, `top_driver_label`, `why` (the main evidence in one line, `null` for `ok`), `drivers` (`key`, `points`), `confidence` (`high`, `medium`, `low`), `recommendation`, `courses` (score and level per course), `at_risk_courses`, `gaps` and `intervention` (the open plan in scope: `id`, `course_id`, `kind`, `created_at`, `progress`, or `null`):

```json
{"id": 15, "name": "Murad Hüseynov", "color": "#0891b2", "group": "İT-25-1", "score": 71.6, "level": "high", "level_label": "High risk",
 "course_id": 1, "top_driver": "attendance", "top_driver_label": "Attendance",
 "why": "5 unexcused absences / 27 lessons (19%) · Test results: average 46% (2 attempts), latest 25%",
 "drivers": [{"key": "attendance", "points": 25.3}, {"key": "assessment", "points": 25.3}, {"key": "concept", "points": 21.0}, {"key": "engagement", "points": 0.0}],
 "confidence": "high",
 "recommendation": {"kind": "plan", "text": "Personal support plan: material, practice and a consultation on the topics with gaps", "cc_office": true},
 "courses": [{"id": 1, "code": "ELM-2105", "name": "Theory of electric circuits", "color": "#2b5aa8", "score": 71.6, "level": "high", "top_driver": "attendance"}],
 "at_risk_courses": 1,
 "gaps": [{"topic": "Kirxhofun birinci qanunu", "course_id": 1, "code": "ELM-2105", "color": "#2b5aa8", "score": 4.8}, "…"],
 "intervention": null}
```

### `GET /api/radar/student/{sid}?course=<id>`

`course` must be one of the student's courses in scope; otherwise the course with the student's highest score is shown. Returns:

| Field | Content |
|---|---|
| `student` | `id`, `name`, `patronymic`, `group`, `student_no`, `color` |
| `course` | The course shown, as in `scope.courses` |
| `profile` | `score`, `level`, `level_label`, `drivers`, `top_driver`, `gaps`, `confidence`, `recommendation`, `stats` |
| `history` | Weekly `as_of`, `score`, `level` for up to eight weeks |
| `lessons` | The last 14 lessons: `day`, `start`, `status`, `topic` |
| `courses` | The student's courses in scope with score and level |
| `cohort` | `students`, `rank` (by score), average `attendance` and `grades` of the course |
| `interventions` | The student's plans in these courses, newest first, cancelled ones left out |
| `can_act` | Whether the caller may send a plan |

Each driver has `key`, `label`, `weight`, `value` (0 to 1), `points` (weight × value), `confidence` and `evidence` (sentences). A gap has `topic`, `asks`, `wrong` and `score`. `recommendation` is `null` or has `kind` (`plan`, `consult`, `nudge`, `office`), `text` and `cc_office`. `stats` holds `attendance` (`total`, `absent`, `excused`, `late`, `streak`, `recent`, `rate`, `missed_topics`), `assessment` (`attempts`, `avg`, `first`, `last`, `trend`, `grade_pct`, `series`) and `engagement` (`asks_14d`, `asks_before`, `median_asks`, `attempts`).

### `POST /api/radar/student/{sid}/plan`

| Field | Type | Notes |
|---|---|---|
| `course_id` | integer | Required; one of the student's courses in scope, otherwise `400` |
| `kind` | `plan`, `consult`, `nudge` or `office` | Default: the recommendation's kind, else `plan` |
| `note` | string | Note to the student; whitespace is collapsed, up to 600 characters |
| `preview` | boolean | `true` returns the plan without saving it |

With `preview`, the response is `{"plan", "score", "level", "kind"}`. Otherwise the plan is stored, the student is notified (and the dean's office when the plan's `cc_office` is set), and the response is `{"id", "intervention"}`. Errors: `409` when the student already has an open plan in this course, `422` when no step can be built from the data.

A plan has `kind`, `title`, `topics`, `topics_source` (`gaps` or `missed`), `steps`, `due_at` (14 days for `plan` and `consult`, 7 for the others), `note` and `cc_office`. A step has `kind` (`read`, `practice`, `attend`, `consult`, `tutor` or `quiz`), `title`, `text`, `link` (an application route) and `done`, plus `topic` and `cites` (`id`, `material`, `heading`, `snippet`) for `read`, `topic` and `question_ids` for `practice`, `when` (`date`, `start`, `room`, `kind`, or `null`) for `consult`, and `done_at` and `auto` once done.

An intervention has `id`, `student_id`, `kind`, `status` (`open`, `completed`, `cancelled`), `created_at`, `updated_at`, `due_at`, `closed_at`, `note`, `plan`, `progress` (`done`, `total`, `percent`), `course`, `author` and `author_title`; for staff and teachers also `risk_before`, `level_before` and `drivers`.

### `POST /api/interventions/{id}/status`

Body: `{"status": "completed"}` or `{"status": "cancelled"}`. `400` for another value, `403` when the plan's course is not in scope, `404` for an unknown plan, `409` when the plan is not open. Returns the intervention.

### Student plan endpoints

`GET /api/student/plans` returns `{"items": [...]}`: up to 10 of the student's plans, open ones first, cancelled ones left out. `GET /api/student/plans/{id}` returns one; a plan of another student or a cancelled plan is `404`.

`POST /api/student/plans/{id}/steps` takes `{"index": <step index>, "done": <bool>}` (`done` defaults to `true`) and returns the plan. `400` when there is no such step, `409` when the plan is no longer open.

### `GET /api/demo/storyline`

Public, demo mode only; returns ids only, for the three-minute presenter script:

```json
{"students": {"elnur": 22, "fidan": 38, "kamran": 46, "lale": 55, "murad": 15, "nermin": 29}, "course_id": 1}
```

The keys are usernames: `POST /api/auth/demo {"role": "student", "user": "murad"}` signs in as that student.

## Public endpoints

These need no session.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/bootstrap` | See [Authentication and session](#authentication-and-session) |
| `GET` | `/api/achievements` | 18 AzTU achievements with categories, headline statistics, the date the sources were checked and the source sites |
| `GET` | `/api/contact` | Official contact details, map links, university systems, pages and social accounts |
| `GET` | `/api/demo/storyline` | Demo mode only; see [Zəka Radar](#zəka-radar) |
| `GET` | `/verify/{code}` | Document verification page (HTML) |

Every achievement item has `id`, `category`, `date` (or `null`), `icon`, `tone`, `featured`, `highlight`, `title`, `summary` and `sources` (each with an `https://` URL).

## Server-rendered pages

| Method | Path | Access | Purpose |
|---|---|---|---|
| `GET` | `/` and `/static/*` | public | Application shell and static assets from `frontend/` |
| `GET` | `/doc/{id}` | holder, staff, or a one-time key `?k=` | Printable document page; `?embed=1` hides the toolbar for display inside the application |
| `GET` | `/verify/{code}` | public | Verification result: valid or revoked, title, registry number, issue date, holder initials, issuing unit, hash prefix; 60 lookups per minute per client address |
| `GET` | `/syllabus/{cid}` | staff who read the course, or a one-time key `?k=` | Printable syllabus: `?v=<version id>`, else the latest version, else an unsaved first draft; `?embed=1` hides the toolbar |
| `GET` | `/api/requests/{id}/preview` | `office`, `admin` | Document preview with placeholder registry number and code |
| `GET` | `/demo/login` | public | Login by link, see above |

The verification code in the URL is case-insensitive. Pages accept `?lang=` like the API; issued documents render in the language chosen in the request (Azerbaijani or English), independent of the page language. Errors on these paths are returned as a small HTML page instead of JSON.

## Endpoint index

158 routes, in the order the router matches them, except that the Task 10–17 routes and `/healthz` are listed next to the other sign-in routes. The four marked "demo" do not exist in prod mode.

| Method | Path | Access |
|---|---|---|
| GET | `/api/bootstrap` | public |
| POST | `/api/auth/demo` | public (demo) |
| GET | `/demo/login` | public (demo) |
| POST | `/api/auth/logout` | any |
| POST | `/api/auth/login` | public |
| POST | `/api/auth/password` | any |
| POST | `/api/admin/users/{id}/temp-password` | admin |
| POST | `/api/admin/users/{id}/unlock` | admin |
| POST | `/api/auth/mfa/verify` | pending |
| POST | `/api/auth/mfa/enroll` | any |
| POST | `/api/auth/mfa/confirm` | any |
| POST | `/api/auth/mfa/disable` | student |
| POST | `/api/admin/users/{id}/mfa-reset` | admin |
| GET | `/api/auth/sso/start` | public |
| GET | `/api/auth/sso/callback` | public |
| POST | `/api/auth/sso/link` | any |
| GET | `/api/me/sso` | any |
| GET | `/api/admin/users/{id}/sso` | admin |
| POST | `/api/admin/users/{id}/sso` | admin |
| DELETE | `/api/admin/users/{id}/sso/{iid}` | admin |
| GET | `/api/me/sessions` | any |
| GET | `/api/me/roles` | any |
| POST | `/api/me/role` | any |
| GET | `/api/admin/users/{id}/roles` | admin |
| POST | `/api/admin/users/{id}/roles` | admin |
| DELETE | `/api/admin/users/{id}/roles/{gid}` | admin |
| GET | `/api/directory/{entity}` | staff |
| POST | `/api/directory/{entity}` | admin, academic_office |
| PUT | `/api/directory/{entity}/{id}` | admin, academic_office |
| POST | `/api/directory/{entity}/{id}/deactivate` | admin, academic_office |
| POST | `/api/directory/{entity}/{id}/activate` | admin, academic_office |
| GET | `/api/directory/units/{id}/groups` | staff |
| PUT | `/api/directory/units/{id}/groups` | admin, academic_office |
| GET | `/api/directory/courses/{id}/enrollments` | admin, academic_office |
| POST | `/api/directory/courses/{id}/enrollments` | admin, academic_office |
| POST | `/api/directory/courses/{id}/enrollments/{uid}/end` | admin, academic_office |
| GET | `/api/courses/{id}/roster` | teacher, admin, academic_office |
| GET | `/api/directory/students/{id}/status` | academic_office, admin, office, leader |
| POST | `/api/directory/students/{id}/status` | academic_office |
| DELETE | `/api/me/sessions/{id}` | any |
| POST | `/api/me/sessions/end-others` | any |
| POST | `/api/admin/import` | admin |
| POST | `/api/admin/activation-codes` | admin |
| POST | `/api/auth/activate` | public |
| GET | `/api/integration/export/{kind}` | admin |
| GET | `/api/integration/status-changes` | academic_office, admin, office, leader |
| POST | `/api/integration/status-changes/{id}/reported` | academic_office |
| GET | `/api/admin/settings` | admin |
| PUT | `/api/admin/settings/{section}` | admin |
| GET | `/healthz` | public |
| POST | `/api/consent` | any |
| GET | `/api/me` | any |
| PUT | `/api/me/prefs` | any |
| GET | `/api/badges` | any |
| GET | `/api/notifications` | any |
| POST | `/api/notifications/read` | any |
| GET | `/api/guide` | any |
| GET | `/api/search` | any |
| POST | `/api/files` | any |
| POST | `/api/files/{id}/link` | any (owner, office, admin) |
| GET | `/api/files/{id}` | any (owner, office, admin) |
| GET | `/api/files/{id}/preview` | any (owner, office, admin) |
| GET | `/api/courses` | any |
| GET | `/api/courses/{id}` | any (course access) |
| GET | `/api/materials/{id}` | any (course access) |
| GET | `/api/source/chunk/{id}` | any (course access) |
| GET | `/api/source/kb/{id}` | any |
| GET | `/api/schedule` | any |
| GET | `/api/attendance` | student |
| GET | `/api/me/absences` | student |
| GET | `/api/grades` | student |
| GET | `/api/courses/{id}/attendance` | teacher, admin, leader |
| GET | `/api/student/home` | student |
| GET | `/api/tutor/{cid}/history` | any (course access) |
| POST | `/api/tutor/{cid}/ask` | student, teacher |
| POST | `/api/tutor/{cid}/clear` | any (course access) |
| POST | `/api/messages/{id}/rate` | any |
| POST | `/api/tutor/{cid}/forward` | student |
| GET | `/api/campus/history` | any |
| POST | `/api/campus/ask` | any |
| POST | `/api/campus/clear` | any |
| GET | `/api/quizzes` | student |
| POST | `/api/quizzes/{id}/start` | student |
| POST | `/api/attempts/{id}/submit` | student |
| GET | `/api/attempts/{id}` | student |
| GET | `/api/teacher/home` | teacher |
| POST | `/api/courses/{id}/materials` | teacher |
| DELETE | `/api/materials/{id}` | teacher |
| PUT | `/api/courses/{id}/tutor` | teacher |
| GET | `/api/teacher/questions` | teacher |
| POST | `/api/teacher/questions/{id}/answer` | teacher |
| POST | `/api/studio/generate` | teacher |
| GET | `/api/questions` | teacher |
| PUT | `/api/questions/{id}` | teacher |
| DELETE | `/api/questions/{id}` | teacher |
| GET | `/api/teacher/quizzes` | teacher |
| POST | `/api/quizzes` | teacher |
| GET | `/api/quizzes/{id}/results` | teacher |
| GET | `/api/services` | any |
| GET | `/api/requests` | student, staff |
| POST | `/api/requests` | student |
| GET | `/api/requests/{id}` | owner, staff |
| POST | `/api/requests/{id}/messages` | owner, staff |
| POST | `/api/requests/{id}/resubmit` | student |
| POST | `/api/requests/{id}/cancel` | student |
| POST | `/api/requests/{id}/action` | office, admin |
| GET | `/api/requests/{id}/preview` | office, admin |
| GET | `/api/office/summary` | office, admin, leader |
| GET | `/api/documents` | office, admin, leader |
| POST | `/api/documents/{id}/revoke` | office, admin |
| POST | `/api/documents/{id}/link` | holder, staff |
| GET | `/doc/{id}` | holder, staff, one-time key |
| GET | `/verify/{code}` | public |
| GET | `/api/news` | any |
| GET | `/api/news/{id}` | any |
| POST | `/api/news/{id}/rsvp` | any |
| POST | `/api/news/{id}/save` | any |
| GET | `/api/news/{id}/ics` | any |
| GET | `/api/news/manage` | office, admin, leader |
| POST | `/api/news` | office, admin, leader |
| PUT | `/api/news/{id}` | office, admin, leader |
| DELETE | `/api/news/{id}` | leader, admin |
| GET | `/api/academy` | teacher |
| PUT | `/api/academy/assessment` | teacher |
| GET | `/api/academy/module/{id}` | teacher |
| POST | `/api/academy/module/{id}/complete` | teacher |
| GET | `/api/tools` | teacher, admin, leader |
| POST | `/api/courses/{id}/tools` | teacher |
| GET | `/api/syllabi/{id}` | staff (course readers) |
| POST | `/api/syllabi/{id}/draft` | teacher (head) |
| PUT | `/api/syllabi/{id}` | teacher (head) |
| GET | `/api/syllabi/{id}/versions/{vid}` | staff (course readers) |
| POST | `/api/syllabus/{cid}/generate` | teacher |
| POST | `/api/syllabus/{cid}/link` | teacher |
| GET | `/syllabus/{cid}` | staff (course readers), one-time key |
| GET | `/api/analytics` | leader, admin |
| GET | `/api/admin/status` | admin |
| PUT | `/api/admin/settings` | admin |
| POST | `/api/admin/test-llm` | admin |
| GET | `/api/admin/audit` | admin, leader |
| GET | `/api/insight/evidence` | leader, admin |
| POST | `/api/admin/reset` | admin (demo) |
| GET | `/api/support/meta` | any |
| GET | `/api/support/tickets` | any |
| POST | `/api/support/tickets` | any |
| GET | `/api/support/tickets/{id}` | owner, office, admin, leader |
| POST | `/api/support/tickets/{id}/messages` | owner, office, admin |
| POST | `/api/support/tickets/{id}/status` | office, admin |
| POST | `/api/support/tickets/{id}/rate` | owner |
| POST | `/api/support/tickets/{id}/reopen` | owner |
| GET | `/api/support/summary` | office, admin, leader |
| POST | `/api/feedback` | any |
| GET | `/api/feedback/summary` | office, admin, leader |
| GET | `/api/system/status` | any |
| GET | `/api/achievements` | public |
| GET | `/api/contact` | public |
| GET | `/api/radar` | teacher, office, leader, admin |
| GET | `/api/radar/student/{sid}` | teacher, office, leader, admin (student access) |
| POST | `/api/radar/student/{sid}/plan` | teacher, office, admin (student access) |
| POST | `/api/interventions/{id}/status` | teacher, office, admin (plan in scope) |
| GET | `/api/student/plans` | student |
| GET | `/api/student/plans/{id}` | student (own plan) |
| POST | `/api/student/plans/{id}/steps` | student (own plan) |
| GET | `/api/demo/storyline` | public (demo) |
