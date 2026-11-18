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
| `GET` | `/api/me/sessions` | any | One's own sessions: created, last active, address, browser, current |
| `DELETE` | `/api/me/sessions/{id}` | any | End one of one's own sessions (`404` for another person's) |
| `POST` | `/api/me/sessions/end-others` | any | End every session but the current one |
| `POST` | `/api/consent` | any | Record consent to AI processing |

### `POST /api/auth/login`

Body `{"login": "<user name or e-mail>", "password": "<as typed>"}`. `200` with `{"user", "home"}` and the session cookie;
`user.must_change` is true after a temporary password, and that session reaches only `/api/auth/*` and `/api/bootstrap`
(other routes answer `403`). A wrong password, an unknown account and a disabled account all get the same `401`.
Failures are counted per account and client (IPv6: its /64): 10 in 15 minutes block that client for that account for
15 minutes, and 100 consecutive failures lock the account for 15 minutes. Both answer `429` with `Retry-After`, are
checked before the password is hashed, and are written to the audit log. Hashing: scrypt (n=2^15, r=8, p=1); a hash
with older parameters is replaced at the next sign-in.

### Second factor (Task 12)

After the right password, `POST /api/auth/login` answers `user.scope`: `full`, `mfa` (a TOTP or recovery code comes
next; the session reaches only `/api/auth/mfa/verify`, `/api/auth/logout` and `/api/bootstrap`) or `mfa_enroll` (a staff
account without a second factor: only `/api/auth/mfa/*`, `/api/auth/password`, logout and bootstrap). TOTP follows RFC 6238
(HMAC-SHA1, 30 s, 6 digits, one step either side); a step is accepted once. Wrong codes count with wrong passwords for the
account and address (Task 10), and five wrong codes end the pending sign-in: the password step starts again. Passing the
second factor gives the session a new id. Recovery codes work once and are stored as SHA-256.

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
| `app` | `university`, `faculty`, `specialty`, `semester`, `base_url`, `engine` (`mode` is `demo` or `llm`, plus a `label`), `news_kinds`, `version`, `mode` (`demo` or `prod`), `access_required`, `langs`, `vendor`, `contact` |
| `home` | Home route of the user's role, or `null` |
| `unread` | Number of unread notifications |

### `POST /api/consent`

Body: `{"ai": <bool>, "external": <bool>}`. `ai` counts as given unless it is `false`; `external` (consent to send questions to an external AI service) only when it is `true`. The choice is stored in the user's preferences and in the audit log. A student's tutor questions go to a configured LLM only when `external` was given. Response: `{"ok": true, "consent_at": "<timestamp>"}`.

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

**`GET /api/badges`.** Always `notifications` and `news` (unread news for the user's audience). Students also get `requests` (open requests), `absences` (unexcused absences) and `plan` (open support plans); teachers get `questions` (open forwarded questions); `office`, `leader` and `admin` get `office` (submitted requests). Teachers, `office` and `leader` get `radar` (high-risk students in their Radar scope). `support` is the number of open tickets for `office` and `admin`, and the number of the user's tickets waiting for their reply for everyone else.

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
| `GET` | `/api/source/kb/{id}` | any | One knowledge base entry, used to open a campus assistant citation |
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

Errors: `400` empty message, `423` tutor locked by the teacher (students only), `429` daily limit reached (students only; default 50 messages per day across the tutor and the campus assistant) or more than 30 assistant calls in a minute.

The message is masked for personal data (unless the administrator turned masking off), then answered by the configured LLM when one is enabled and a relevant passage exists, and by the offline engine otherwise. A student's question goes to the LLM only after the student consented to external AI processing (`POST /api/consent` with `external: true`). In practice mode the message is either an answer to the pending question or a request for a new one. The answer `meta` can contain `mode`, `topic`, `level` (Socratic step), `guardrail` (the user asked for a finished answer), `no_source`, `practice_qid`, `graded`, `correct`, `engine` and `note` (why the LLM was not used).

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

Body: `{"message": "..."}`, required, cut to 1,500 characters. The same daily limit and per-minute limit apply. English and Russian keywords are expanded to the Azerbaijani terms used in the knowledge base. `answer.meta.actions` lists request forms the user can open from the answer:

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
   "explanation": "“is used to” quruluşundan sonra felin əsas forması gəlir: is used to limit.",
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
| `GET` | `/api/services` | any | Service categories and request types with their form schemas |
| `GET` | `/api/requests` | `student`, staff | The student's requests, or the office queue |
| `POST` | `/api/requests` | `student` | Submit a request |
| `GET` | `/api/requests/{id}` | owner, staff | Request with form data for display, timeline, message thread and attachments |
| `POST` | `/api/requests/{id}/messages` | owner, staff | Add a message to the request thread |
| `POST` | `/api/requests/{id}/resubmit` | `student` | Resubmit a request returned for correction |
| `POST` | `/api/requests/{id}/cancel` | `student` | Cancel a submitted or returned request |
| `POST` | `/api/requests/{id}/action` | `office`, `admin` | Approve, return, reject or issue |
| `GET` | `/api/requests/{id}/preview` | `office`, `admin` | HTML preview of the document before issue |
| `GET` | `/api/office/summary` | staff | Queue counters, documents issued this week, average processing hours |
| `GET` | `/api/documents` | staff | Document registry search, up to 200 rows |
| `POST` | `/api/documents/{id}/revoke` | `office`, `admin` | Revoke a document |
| `POST` | `/api/documents/{id}/link` | holder, staff | One-time link to the document page |

Teachers cannot see requests; for them request endpoints answer `404` or `403`.

### Request types and form schema

`GET /api/services` returns `categories` (`key`, `seq`, `name`, `icon`, `color`, `text`) and `types`. A type has `code`, `category`, `name`, `icon`, `sla_hours`, `document` and `document_en` (title of the issued document, or `null` when the outcome is an answer instead of a document), `prefix` (registry prefix), `description`, `needs`, `outcome`, `privacy`, `steps` (workflow stage names), `attachments` (`label`, `required`, `max`, `accept`, or `null`), `answer`, `popular` and `fields`.

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

The 13 request type codes: `enrollment_certificate`, `transcript`, `student_card`, `absence_excuse`, `leave_permission`, `exam_reschedule`, `academic_leave`, `grade_appeal`, `individual_plan`, `tuition_installment`, `social_scholarship`, `dormitory`, `free_application`. Three of them produce a document: `enrollment_certificate`, `transcript` and `academic_leave`.

### `POST /api/requests`

Body: `type_code`, `data` (an object keyed by field name), `files` (ids from `POST /api/files`, up to 10, within the type's `max`). The deadline is the submission time plus `sla_hours`. The dean's office is notified.

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
 "steps": ["Academic office reviews", "Document is prepared and approved"],
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

For students: all of their requests, newest first. For staff, query parameters: `status` (`open` by default, `done`, or any other value for all), `type` (type code), `category`, `q` (matches student name, request id or type name). The queue is ordered by status and deadline.

### `GET /api/requests/{id}`

The request as above plus `type` (full type definition), `data_view` (label and display value for each filled field), `events` (timeline with actor name and role), `thread` (messages with author, role and colour), `attachments` and, once issued, `document` (`id`, `reg_no`, `verify_code`, `status`).

### `POST /api/requests/{id}/resubmit` and `/cancel`

Resubmit takes `data` (merged over the stored data and validated again) and `files` (added to the existing attachments); it is allowed only in status `returned` and answers `409` otherwise. Cancel is allowed in `submitted` and `returned`.

### `POST /api/requests/{id}/action`

| `action` | Allowed when | Effect |
|---|---|---|
| `approve` | Not returned, not on the last step | Status `in_progress`, step + 1, student notified |
| `return` | Open | Status `returned`; `note` required; student notified |
| `reject` | Open | Status `rejected`; `note` required; student notified |
| `issue` | Not returned | Status `ready`; a document is issued if the type defines one, otherwise `note` or the type's standard answer is stored; outcome side effects applied; student notified |

Side effects of `issue`: for `absence_excuse` the selected lessons become `excused` and their teachers are notified; for `leave_permission` and `exam_reschedule` the teachers concerned are notified. Closed requests answer `409`. The response is the full request.

After issue, the response includes the document:

```json
{"document": {"id": 13, "reg_no": "AzTU-ARY-2026-000012", "verify_code": "2LTH-4XLR", "status": "valid"}}
```

### Documents

`GET /api/documents?q=<text>` searches registry number, holder name and title and returns `id`, `kind` (`request` or `certificate`), `title`, `reg_no`, `verify_code`, `issued_at`, `status` (`valid` or `revoked`), `revoked_reason` and `holder`.

`POST /api/documents/{id}/revoke` takes `{"reason": "..."}` (required, up to 500 characters); `404` for an unknown document.

`POST /api/documents/{id}/link` returns a one-time URL, valid for five minutes; `404` when the document does not exist or belongs to someone else:

```json
{"url": "/doc/13?k=kQFAz1cbzpw8vYrHxi6Ziu6x"}
```

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
| `GET` | `/api/syllabus/{cid}` | `teacher` | Saved syllabus of the course |
| `POST` | `/api/syllabus/{cid}/generate` | `teacher` | Draft a syllabus from the course data |
| `PUT` | `/api/syllabus/{cid}` | `teacher` | Save the edited syllabus |
| `POST` | `/api/syllabus/{cid}/link` | `teacher` | One-time link to the printable syllabus |

**`PUT /api/academy/assessment`.** Body: `{"values": {"<track key>": 1..5}}`. Track keys: `ai`, `emi`, `syllabus`, `communication`, `pedagogy`, `research`, `edtech`. Recommended tracks are the three lowest-rated tracks that are not complete. Returns the same object as `GET /api/academy`.

**`POST /api/academy/module/{id}/complete`.** Body: `{"answers": [<option index>, ...]}` in question order. Response: `passed` (score of 50% or more), `score`, `correct` and `certificate`. After a pass, `correct` lists the correct option index of every question; after a fail, only the indices the teacher already answered correctly, and `null` for the others. When the last module of a track is passed, a certificate document is issued and returned as `{id, reg_no, verify_code}`; otherwise `certificate` is `null`.

**`POST /api/courses/{id}/tools`.** Body: `{"tool_key": "<key>"}`. Response: `{"on": <bool>, "tools": [<keys>]}`.

**`POST /api/syllabus/{cid}/generate`.** Body: `{"weeks": 10..18}`, default 15. Returns `course`, `description`, `workload`, `outcomes` (up to 6, derived from glossary terms of each material), `plan` (one row per week with colloquia in weeks 7 and 13 and revision in the last week), `assessment`, `materials`, `tools`, `policies` and `generated_at`. `PUT /api/syllabus/{cid}` stores `{"data": <that object>}` and returns `{"ok": true, "updated_at": ...}`. The object must keep every part of a generated syllabus (`course` with its fields, `workload`, `description`, the lists, plan rows with `week`, `topic` and `activity`, assessment rows as `[name, weight]`), otherwise `400`; only these fields are stored, and more than 200,000 characters is a `413`.

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
| `POST` | `/api/admin/reset` | `admin` | Delete all data and reseed the demo |
| `GET` | `/api/system/status` | any | Status of the platform components |

**`GET /api/analytics`** returns `labels` (8 week labels), `wau_students`, `wau_teachers`, `tutor_questions`, `request_hours`, `kpis` (8 indicators with `key`, `label`, `value`, `target`, `ok`, `series`), `courses` (per course: tutor questions, test average, no-source rate, positive rate, attendance), `insights` (the first one is the Zəka Radar summary, with a `link` to `/radar`), `office` (as `/api/office/summary`), `requests_by_type`, `news` (5 most read), `attendance`, `ai` and `totals`. Several series and values are fixed illustrative numbers in this version: weekly active students and teachers, the test preparation time reduction, the satisfaction score and trend, the learning gain, the cost per student, and all but the last point of the request time, citation and academy series. See section 16 of [ARCHITECTURE.md](ARCHITECTURE.md) for the full breakdown.

**`PUT /api/admin/settings`.** Body: any of `daily_messages` (5 to 500), `pii_masking` (boolean), `socratic_default` (boolean), `retention_days` (30 to 3,650). Saving deletes chat messages older than `retention_days`. Returns the stored limits. `socratic_default` is stored but does not affect behaviour in this version.

**`POST /api/admin/test-llm`.** Response: `{"ok": <bool>, "message": "..."}`; when no LLM is configured, `ok` is false and the message says the demo engine is in use. An error message never contains the API key.

**`GET /api/system/status`** (any signed-in user) returns `components` (`portal`, `db`, `ai`, `notify`, `sso`, `lms`, each with `status` `operational`, `degraded`, `down` or `planned`, a `name` and a `note`), `checked_at`, `uptime_s` and `overall`. The `ai` component is `degraded` while the offline engine is in use, and `sso` and `lms` are `planned`.

**`POST /api/admin/reset`.** Demo mode only. Deletes every row except the schema migration log, including all sessions, reseeds the demo data and rebuilds the indexes. Response: `{"ok": true}` with an expired session cookie.

## Zəka Radar

Early warning: a risk score per student and course from attendance, grades, test attempts and tutor activity, the reasons behind it, and support plans that a teacher or the dean's office sends to the student.

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

Scope: a teacher sees the courses they teach (`403` when they teach none); `office`, `leader` and `admin` see all courses. Student access means the student exists (`404` otherwise) and is enrolled in a course in scope (`403` otherwise). Students never see a risk score: the student endpoints leave out `risk_before`, `level_before` and `drivers`.

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
| `GET` | `/syllabus/{cid}` | `teacher`, `leader`, `admin`, or a one-time key `?k=` | Printable syllabus; `?embed=1` hides the toolbar |
| `GET` | `/api/requests/{id}/preview` | `office`, `admin` | Document preview with placeholder registry number and code |
| `GET` | `/demo/login` | public | Login by link, see above |

The verification code in the URL is case-insensitive. Pages accept `?lang=` like the API; issued documents render in the language chosen in the request (Azerbaijani or English), independent of the page language. Errors on these paths are returned as a small HTML page instead of JSON.

## Endpoint index

128 routes, in the order the router matches them, except that the Task 10–12 routes and `/healthz` are listed next to the other sign-in routes. The four marked "demo" do not exist in prod mode.

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
| GET | `/api/me/sessions` | any |
| DELETE | `/api/me/sessions/{id}` | any |
| POST | `/api/me/sessions/end-others` | any |
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
| GET | `/api/syllabus/{cid}` | teacher |
| POST | `/api/syllabus/{cid}/generate` | teacher |
| PUT | `/api/syllabus/{cid}` | teacher |
| POST | `/api/syllabus/{cid}/link` | teacher |
| GET | `/syllabus/{cid}` | teacher, admin, leader, one-time key |
| GET | `/api/analytics` | leader, admin |
| GET | `/api/admin/status` | admin |
| PUT | `/api/admin/settings` | admin |
| POST | `/api/admin/test-llm` | admin |
| GET | `/api/admin/audit` | admin, leader |
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
