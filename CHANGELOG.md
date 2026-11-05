# Changelog

All notable changes to the Zəka demo are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Automated test suite (pytest): unit tests for the engine, QR encoder, i18n, storage, PDF text extraction,
  tutor, documents and HTTP layer, plus integration tests that drive every main flow through the real HTTP server
  against an isolated, freshly seeded database. Run with `python -m pytest`.
- GitHub Actions CI (`.github/workflows/ci.yml`): ruff lint, mypy type check, JavaScript syntax check, the i18n
  catalogue check and the test suite on every push and pull request.

### Fixed
- **Practice/quiz grading: negated true/false answers were graded as the opposite.** Typing “doğru deyil”
  (“not true”) or “düz deyil” counted as *true* because the positive word was matched first; “yanlış deyil”
  (“not false”) counted as *false*. Negation now flips the word it follows (`engine.grade`).
- **Keep-alive connections broke after a rejected request.** When a POST/PUT was refused before its body was read
  (401 expired session, 403, 404, 405, 415), the body stayed in the socket and the browser's *next* request on the
  same connection failed with “400 Bad request syntax”. Unread bodies up to 1 MB are now discarded; larger ones close
  the connection (`Connection: close`).
- **`HEAD` requests answered 501.** The response writer already left out the body for `HEAD`, but no `do_HEAD`
  existed, so uptime monitors and health checks using `HEAD` saw the portal as down.
- **Invalid `Content-Length` crashed or hung a server thread.** A non-numeric value answered 500; a negative value
  reached `rfile.read(-1)` and blocked the thread until the client disconnected. Both are now a 400. Connections also
  time out after 120 s of inactivity instead of holding a thread forever.
- **Database connections leaked on 401/403.** The connection opened for the request was not closed when
  authentication or the role check failed (Python 3.13 reports this as a `ResourceWarning`).
- **Non-standard JSON constants were accepted.** `NaN` / `Infinity` in a request body reached handlers as floats and
  could crash them (`int(float("inf"))`); they are now rejected as “Invalid JSON”.
- **Route parameters were percent-decoded twice** (`/verify/%2541` matched code `A`), and a non-ASCII digit such as
  `/verify/²` crashed the router with a 500.
- **English enrolment certificates printed wrong ordinals** (“1th-year”, “3th-year”); they now read 1st, 2nd, 3rd, 4th.
- **Multiple-choice grading accepted a negative option index** (−1 was graded and shown as option D).
- **28 API endpoints crashed with HTTP 500 on wrongly typed input** — a text where a number belongs (event capacity
  “50 nəfər”, quiz time limit, syllabus weeks, admin limits, ratings), a list or object where text belongs (tutor
  message, ticket subject, comment, document revocation reason), non-numeric ids (notifications, attachments, quiz
  questions) or an unknown vocabulary value (ticket category/priority/status, feedback area). Handlers now read the
  body through typed accessors and answer a translated 400 (“Invalid value: …”). Nested e-service form data with the
  wrong shape (e.g. a date range sent as a string) is handled the same way.
- **Open redirect and response-header injection in `/demo/login?next=`.** A path such as `/\t/evil.example` passed
  the “starts with one slash” check but browsers drop the TAB and follow `//evil.example`; CR/LF in `next` was
  written into the `Location` header (header injection), and a non-Latin-1 character crashed the response.
  Only printable-ASCII same-site paths are accepted now.
- **Syllabus page: stored HTML injection.** Week numbers, credits, workload hours and assessment points from the
  teacher-edited syllabus were inserted into the printable page without escaping. All values are escaped now.
- **Syllabus save accepted incomplete data.** Only the `course` key was checked, so a partial object was stored and
  then broke both the editor and the printable page. The full structure is validated; an invalid saved syllabus is
  regenerated for display.
- **Printable syllabus of an unknown course answered 500** for leaders and administrators (no course-access check
  for those roles, then `None["id"]`); it is a 404 now.
- **Editing a question could break every quiz that used it.** An updated multiple-choice answer outside the option
  list (or a non-boolean true/false answer) was stored, and every student's quiz submission then crashed in
  `answer_display`. Question updates now validate the answer against the question type and options.
- **Revoking a non-existent document reported success** and wrote an audit entry; it is a 404 now.
- **Quiz creation stored duplicate question ids** when the same question was selected twice; duplicates are dropped.

