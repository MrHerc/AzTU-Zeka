# Checkpoint F addendum (2026-11-23)

## Scope

Work on top of Checkpoint F (`e02f1d6`, `docs/review/checkpoint-f-2026-11-22.md`), built in three branches, merged in
the order 1, 2, 3 and reviewed together:

- **Task 24, the framework map and the NICE import** (`cf261ee`, `44da579`, merge `ff59433`). Task 24 was blocked at
  Checkpoint F because the proxy refused the NICE file's host. The file was found at NIST's own address and stored
  unchanged:
  - source: `https://csrc.nist.gov/csrc/media/Projects/cprt/documents/nice/v2-2-0_nf_components.json`;
  - `Last-Modified: Mon, 18 May 2026 14:35:22 GMT`, downloaded 2026-11-23, 2 674 252 bytes;
  - SHA-256 `3ad1d9d7e0d6b32895cb569f86c3bc05af2937a68e96eab4d1c9b3d9fa6e575e`, document `SP_800_181_2_2_0`;
  - a work of the United States Government (17 U.S.C. §105); provenance in `content/frameworks/README.md`.
  Migration `0240` (frameworks, items, links, outcome map), `manage.py import-framework`, Bloom and EQF built in, the
  picker in the syllabus editor, the read-only tags in the printed and published syllabus, and the coverage report
  (`/frameworks/coverage`, CSV with a BOM). Six new routes.
- **Gaps Checkpoint F left open:**
  - Task 48's hours-report page (`GET /api/timetable/versions/{id}/hours`, `/timetable/hours/:id`) and the timetable
    export (`manage.py export --kind timetable [--term T] [--version V]`, the same `export.run` on screen) (`ab25a49`,
    merge `58f4656`);
  - the CORR-F1 re-measure and the import count of Task 48's acceptance (outside the repository, counts only);
  - axe-core run in the browser (14 checks that were skipped), the browser language pass of L1–L20 and M1, TE-F11
    shown failing on a real 500, and M1's leftovers (`0465_language_rows.sql`, the seeded test questions with «»)
    (`6b6eede`, `e3b2d83`, merge `0bc8eda`).

## Method

The same as Checkpoint F's round 2:
- Four lenses ran on the merged branch: security, correctness of business rules, test strength (single mutants of
  every new rule, test order forward, reversed and shuffled) and the earlier claims.
- A separate agent tried to refute each finding on a scratch copy of the branch, with probes and temporary tests.
- Only confirmed findings were fixed. Each fix has a test that fails without it: the code fixes were shown failing
  with `git stash`, the test gaps by re-applying the review's mutant (27 mutants, all killed after the fixes).

## Measured

**Suite.** 2 056 tests are collected. The last full run on the fixed branch: 2 040 passed, 16 skipped, 0 failed in
12 min 52 s. `ruff check .` and `mypy` (138 files) are clean, `node --check` passes on every `frontend/js` file,
i18n `stats` is 100 % for en and ru and `lint` stays at 72. 328 routes are in `tests/security/matrix.json` (7 new, no
other change).

**The NICE import** (`manage.py import-framework --file content/frameworks/nice-components-2.2.0.json` on a fresh
database, run for this report):

| Kind | In the file | In the database |
|---|---|---|
| task | 962 | 962 |
| knowledge | 693 | 693 |
| skill | 556 | 556 |
| work_role | 42 | 42 |
| competency_area | 11 | 11 |
| category | 5 | 5 |
| opm_code | 40 | 40 |
| sort | 47 | 47 |
| links | 5 950 | 5 950 |

A second run prints "already imported, nothing changed" with the same counts; both exit 0.
`tests/integration/test_frameworks.py`: 29 passed. Its sample is cut from the real file by
`tests/fixtures/make_nice_sample.py`, and a test checks every sample element against the real file.

**CORR-F1 re-measured on the two departments' real files.** The same end-to-end acceptance ran twice on fresh
databases: before the fix (`4aebb25`) and after it (`e02f1d6`). Both used one yardstick, the current
`domain.hours_report`, with a 2 h tolerance.

| | Before | After |
|---|---|---|
| Spring (670 units, 701 meetings): units outside the tolerance | 183 | 12 |
| Spring: planned − Forma №3 hours | −1 062 h | −534 h (15 622 h in the form) |
| Autumn (860 units, 924 meetings): units outside the tolerance | 4 | 2 |
| Autumn: planned − Forma №3 hours | −261.5 h | −257.5 h (20 543.5 h in the form) |
| Placed / unplaced, both terms | all / 0 | all / 0 |
| Hard violations (builder check and a separate SQL check) | 0 | 0 |
| Solve, 50 000 iterations, wall | 5.0–5.5 s | 5.3–5.6 s |
| Server tracebacks | 0 | 0 |

- The hours from the spring's published lessons equal the hours from its placements, unit by unit.
- The −534 h left are mostly the 8 spring holidays; whether they are made up is the owner's question Q1.
- The 12 units (13 meetings) outside the tolerance each have a free slot on a better weekday:
  - for 11 of them, the move costs more than it saves under the current weights (the order of the soft rules is an
    open question of the timetable office);
  - for 2, the search stops before a move that would lower the soft total by 4. The search stalls at about 2.5 s CPU
    whatever the budget.
- The solver's cost equals the scorecard; the solver was not changed.

**The import count.** The reader reads 1 600 units (RT 355, MR 1 245). 1 530 are written (RT 335, MR 1 195). 70 are
held back (RT 20, MR 50): academic-year conflict 22, subject name missing 31, group missing 5, the hidden sheet 12.
- The 63 that Checkpoint F reported (13 + 38 + 12) came from the import report's `count`.
- That count leaves out RT's 7 units of a post on a sheet outside the department total (cell `#1!A4`).
- Checkpoint F's "RT 348 units" is the same 355 without those 7.
- `tasks/todo.md`'s 70 was right; its sentence now gives the whole breakdown.

**Accessibility and language in the browser.**
- `tests/e2e/test_a11y.py` with axe-core installed (`npm ci --prefix tests/e2e`): 14 passed, 0 skipped. 14 pages, on
  desktop and on a phone, had no violation of any impact.
- The other e2e checks passed (29 in all).
- The 36 screens behind L1–L20 and M1 were opened in az, en and ru at 1 280 and 390 px (en and ru with
  `?i18n=debug`), 204 captures in all. They showed no ⟦⟧ marker, no 5xx and no horizontal scroll.
- One English label was left: "New news item", the same repetition L20 removed in Russian. Fixed in `e3b2d83`.
- TE-F11: a 500 put into a scratch copy made `test_e2e_smoke` fail with "the server logged an exception during the
  browser run" and the traceback.

## Findings

28 findings were confirmed and all are fixed. One side claim (OK-1) was confirmed in code and is left open, as low.

| Id | Severity | Finding | Fix |
|---|---|---|---|
| SEC-FW-1, BR-F1 | Important | Outcome tags were keyed by course and outcome code, not by version. A teacher of any section of the course could change the tags of an approved and published syllabus, and the student's published page showed the change at once, with no submit, approval or publication. | `1b8d7a3`: submitting a version copies the course's tags into `syllabus_versions.tags` (`0241` fills the versions submitted before). The print view, the student's published syllabus and the coverage report read that copy. |
| BR-F2 | Low | A deleted outcome's tags stayed, and the editor gave its code to the next new outcome, which inherited them | `1b8d7a3`: saving drops the tags of codes the version no longer has; `nextId` in `syllabus.js` never reuses a code that still has tags |
| SEC-FW-2 | Low | The coverage report showed draft outcome texts of another department's course to a department head who gets 404 on that syllabus | `1b8d7a3`: a draft is read only for a caller who may read the course's syllabus; others get the published version only |
| SEC-FW-3, BR-F3 | Low | A NICE file with a changed `version` label skipped the SHA-256 check, took NIST's address from its own `website` field and became the default framework | `c5437f4`: a version without a hash in `KNOWN` is imported as **unverified**: no source address, `verified: false`, listed after the verified ones, never the default; the UI and the CLI say so |
| SEC-FW-4 | Nit | A deeply nested JSON file crashed `import-framework` with a `RecursionError` traceback; the size limit was checked after reading the whole file | `c5437f4`: refused as "not JSON"; the CLI checks the size before reading |
| BR-T1 | Low | The version's scorecard counted only placed units, the hours report every unit, so they disagreed for one version (0 / 345 h against 1 / 360 h) | `4dd8f6a`: the scorecard's hours cover every unit of the problem; the cost (`hours_miss`) is unchanged |
| ORD-1 | Test hygiene | `test_frameworks.py` passed only in file order (3 failures reversed) | `1b8d7a3`: tests that publish a syllabus or delete an outcome make their own course |
| ORD-2 | Low | The hours and export tests failed when selected alone (`-k "hours or export"`) | `4dd8f6a`: a `chain` fixture runs the tests they build on |
| MUT-c02, c05, c15, MUT-csv (c10) | Test gap | Untested: the department grant in the coverage scope, the published version before a draft, the formula guard of the coverage CSV, active units only | `1b8d7a3` |
| MUT-parse (n01, n02, n05, n06), c08, n10, n11, m07, p02, p04 | Test gap | Untested: one document per file, the element's `doc_identifier`, the version's length, the file limit, numeric version order, parents only for work roles, built-in updates, `can_map` for teachers only, a real non-role code, the last page's `more` | `c5437f4` |
| MUT-hours-page (h04–h06), h03, h09-h10, csv (h08), x02-x10, x06, x08 | Test gap | Untested: the hours report's paging and totals, the department list under a filter, the tolerance and the translated reason, the hours CSV formula guard, canonical weeks and a version's own term in the export, `?term=`/`?version=` over HTTP, the export's audit scope | `4dd8f6a` |
| MUT-l03 | Test gap | `0465`'s `synthetic = 1` guard (a person's real tutor history) was untested | `1161c6b` |
| OK-1 (side claim) | Low, **open** | `builder.hours` does not pass the version's lessons to `domain.hours_report`, so a published version's hours report never counts cancelled lessons (the `cancelled` reason never appears) | Not fixed; recorded here and in `tasks/todo.md` |

Refuted: none. Narrowed by the refuters:
- BR-F2 and BR-T1 were lowered from medium to low, and ORD-1 from important to test hygiene.
- SEC-FW-3 and BR-F3 keep the import of an unknown version, which is by design, and fix only how it is marked.
- MUT-csv is one finding with two mutants (c10 in the coverage CSV, h08 in the hours CSV), fixed in two commits.

## Not verified

- The "unverified copy" badge and the editor's `nextId` were not opened in a browser. The `nextId` test runs under
  node and is skipped without it.
- The framework picker and the coverage page were not covered by an axe run.
- `tools/queryplan.py --dataset university` was not re-run after the fixes. Only the suite's query-plan tests ran.
- The hours report reads the term's snapshot inside the request. It was not timed at university scale
  (16 700 units).
- The coverage report now calls `may_read` per course. It was not timed on a large programme.
- The English EQF text was written without comparing it to EUR-Lex (the proxy refuses europa.eu). The Azerbaijani
  and Russian Bloom and EQF texts are working translations.
- `0241` fills the tags of versions submitted before it from today's working map. Tags changed after an earlier
  publication are not restored.
- `0240` comes after `0465` in number order. `migrate.py` applies it on an older database, but this was checked only
  by reading `migrate.py`, not on a real old database.
- The full e2e timetable script (`tests/e2e/timetable.js`) and the load test were not re-run after the merge.

## Remaining risk

- OK-1: a published version's hours report overstates delivered hours when lessons are cancelled.
- The coverage report is empty for a specialty whose Forma №3 is not imported, because a programme's courses come
  from its teaching units.
- The search of the built-in frameworks matches only Azerbaijani text.
- Residual “ ” quotes remain in `campus_kb.md` and `content/materials/eng-*.md` (indexed content, outside M1's scope).
- The audit detail "demo rol: student" shows in Azerbaijani in en and ru; the audit is append-only.
- Checkpoint F's release recommendation is unchanged: not ready for production; ready for the owner's review and a
  pilot on a test server with synthetic data.
