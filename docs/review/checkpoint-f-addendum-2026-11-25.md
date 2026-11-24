# Checkpoint F addendum (2026-11-25)

## Scope

Work on top of `42f8bcb` (the owner's decisions of 2026-11-24; `main` equals the working branch). It was built in four
branches and merged in the order 1, 2, 3, 4 into `integrate-wf-27f`. The range is `42f8bcb..HEAD`; nothing is pushed.

- **Branch 1: the Windows CI job** (`173ff92`):
  - Without a tz database `clock.ZONE` was None, `local()` read the OS time (UTC on the runner) and missed the suite's
    patched `clock.now`: about 80 of the 92 Windows failures. `clock.FIXED` now serves `Asia/Baku`, `UTC` and
    `Etc/UTC`; another unknown zone raises, and `run.py` refuses it in demo mode too. `tzdata` is a dev requirement.
  - A pipe write after openssl exits gives EINVAL on Windows, not `BrokenPipeError`: it is a `BackupError` now.
  - Test helpers that wrote CRLF (ETL hashes), printed `\` paths (`tools/i18n.py rename`), or reset a socket (webhooks).
    `tools/loadtest.py` retries `ConnectionAbortedError` too.
  - The Windows job's limit is 45 minutes. Actions moved to v7 (Dependabot PR #6).
- **Branch 2: the screens of 2026-11-23/24 measured at university scale** (`56ad482`):
  - The hours report was quadratic (every unit walked the term's meetings): page p50/p95 479/632 → 101/205 ms.
  - The coverage report made 310 statements for a 300-course programme; now 10–11 (`published_of`).
  - The prerequisite lookup used `/api/directory/courses` (a scan, and the full course row to any staff member). It has
    its own route, `GET /api/syllabi/{id}/prerequisites?q=`, for the course's head teacher: code and name, at most 10,
    by the start of a code or a name through index ranges (migration `0232`).
- **Branch 3: the built-in framework texts** (`078bcc2`): the 24 EQF descriptors equal Annex II of the Council
  Recommendation of 22 May 2017 word for word; Bloom's six names and definitions were checked against Anderson &
  Krathwohl (2001) as cited; one comma restored.
- **Branch 4: the single server's risks** (`479219a`): backup and restore under live load, hourly backups (RPO one hour,
  `backup.keep`), `core/ops.py` (backup age, free disk, failing jobs, the runner's lease), the hourly job `ops.check`,
  `manage.py jobs check` for the host's cron, the admin page's server card and the external monitor runbook.
- **Integration** (`27dd177`): a blank line had split the deploy runbook's settings table.

## Method

The same as the addendum of 2026-11-24:
- Three lenses ran on the merged branch (`27dd177`): security, correctness of business rules, and test strength
  (single mutants of every new rule).
- A separate agent tried to refute each finding on a clean copy of the branch, with probes and temporary tests.
- Only confirmed findings were fixed, each with a test:
  - code fixes: the new test ran red on `27dd177` before the fix;
  - test gaps: the review's mutant was re-applied and the new test killed it.

## Findings

16 findings were confirmed and all are fixed (`bec4cf9`). None was refuted; several were narrowed (below).

| Id | Severity | Finding | Fix |
|---|---|---|---|
| SEC-27F-1 | Medium | `manage.py jobs check`, run every hour by the host's cron inside the app container, ran a full `store.init()`: migrations, the built-in frameworks and the whole search index. At university scale 21.2 s real, 19.9 s CPU and 790 MB, for a check that takes 0 s | The check reads the database as it is: no `store.init()`, no migration, no index, no new database (exit 2 when there is none, or the schema is older than the code). Measured on the same dataset: 0.16 s, 39 MB. Tests: `test_manage_jobs_check_never_creates_migrates_or_indexes_a_database`, `test_manage_jobs_check_exits_0_when_nothing_is_wrong_and_reads_no_index` |
| WF27F-1 | Medium | One `LIMIT 200` covered every arm of the prerequisite lookup. 250 names starting «Ma» filled it before the code arm «MA» was read, so `MA-101` was lost, and the ten shown were not the first ten by code | Each arm is a subquery read in code order with its own limit; the name arms pin `idx_courses_name`, so the plan stays an index range. Test: `test_a_code_match_is_never_crowded_out_by_names_and_the_first_ten_are_in_code_order` |
| WF27F-2 | Low | The prefix lookup no longer finds a word inside a name (`nəzəriyyəsi`) or a code's number alone (`2105`), which the old `LIKE '%q%'` found. Deliberate, but the docs did not say rows were lost | Documented in `docs/API.md` and `docs/perf/baseline.md`. The field already says «Fənnin kodunun və ya adının əvvəlini yazın». Word search inside names is left for later (below) |
| WF27F-3 | Low | `ops.check` marked a day per check, not per problem: a second job that began to fail the same day (`outbox.send`) was not told; «no backup» and «backup too old» shared one mark | `periodic.ops_marks`: each failing job, no backup and an old backup, a runner that never ran and one that stopped are separate marks. Tests: `test_a_second_failing_job_the_same_day_is_told_too`, `test_no_backup_and_an_old_backup_are_two_problems` |
| WF27F-4 | Low | Without a tz database the fixed `+04` put Baku's summers of 1996–2015 an hour early (an old `export --since`). `export._wall` fell back to the OS time, and its comment said `clock.local` did the same, which is no longer true | `clock.BAKU` equals the tz database's Asia/Baku from 1993 on (EU 01:00 UTC rule in 1996, 00:00 UTC in 1997–2015), PEP 495 folds included. `clock.zone()` raises instead of the host's time, used by `local()` and `export._wall`. Tests: `tests/unit/test_clock_fallback.py` (hourly comparison with zoneinfo, 1993–2045) |
| SEC-27F-2 | Low | `ci.yml` used movable tags (`@v7`), while `security.yml` pins the same actions by SHA | All four actions pinned to the v7 tags' commits (checked with `git ls-remote`; lightweight tags), with the version beside them. Test: `tests/unit/test_workflow_pins.py` checks every workflow |
| MUT-P1 | Test gap | «Once a day» was untested: removing the day from the mark passed | `test_a_lasting_problem_is_told_again_the_next_day` |
| MUT-P5P6 | Test gap | `jobs check`'s exit 0 was untested: `return 1` always, or `ok=None` counted as a problem, passed | `test_manage_jobs_check_exits_0_when_nothing_is_wrong_and_reads_no_index` |
| MUT-O3O4 | Test gap | The backup disk was untested (the fixture gave every path one usage on one device) | `test_the_backup_disk_counts_too` (another device, 5 % free) |
| MUT-S8 | Test gap | `active=1` in the lookup was untested | `test_the_lookup_s_forms_offerings_and_limits` |
| MUT-S3S4 | Test gap | The English capitals (`INF-101`) and the Azerbaijani capital İ were untested | the same test, and `test_prefixes_are_the_typed_forms_of_a_code_and_a_name` |
| MUT-P2 | Test gap (new code, not pre-existing) | A blocked administrator would be told | `test_a_blocked_administrator_is_not_told` |
| MUT-S7S9S5 | Nit | The latest offering's name, the limit of 10 and the space normalisation | `test_the_lookup_s_forms_offerings_and_limits` |
| MUT-E2 | Nit (old code) | A correction of a built-in title alone | `test_a_correction_of_a_builtin_title_alone_is_applied_and_a_programme_over_500_courses_is_read_whole` |
| MUT-O10O11 | Nit | `ops.backup_dir()`'s default and a zero or negative limit falling back | `test_the_default_backup_folder_is_manage_py_s_and_a_zero_limit_falls_back` |
| MUT-MINOR | Nit | `UTC` without a tz database (C4), the limits' boundaries (O1, O7), a set exactly 24 hours old (B1), a programme over 500 courses (E5) | `test_utc_needs_no_tz_database`, `test_a_value_at_its_limit_is_still_fine`, `test_hourly_backups_keep_one_set_per_hour_of_the_last_day`, the E2 test above |

Red before the fix, on `27dd177`: `test_ops_alerts.py` 4 failed, 13 passed (SEC-27F-1 twice, WF27F-3 twice); the
registry test 1 failed (WF27F-1); `test_clock_fallback.py` 3 failed, 3 passed (WF27F-4); `test_workflow_pins.py`
1 failed (SEC-27F-2). After the fixes all 22 mutants of the review (P1, P2, P5, P6, O1, O3, O4, O7, O10, O11, S3, S4,
S5, S7, S8, S9, E2, E5, B1, C4, and the two fixes WF1 and WF3 reverted) are killed.

Narrowed by the refuter, not refuted:
- **SEC-27F-1:** `store.init()` in `jobs status|run` is older; what was new is the hourly cron of `check`. A pending
  migration applied by cron does not happen in Docker in practice (the exec runs the same image the app started
  with); it was a risk of a host install without an image.
- **SEC-27F-2:** not new (the tags were `@v4`/`@v5` before); `ci.yml` uses no secret and reads only.
- **WF27F-1:** happens only when the earlier arms of one prefix hold more than 200 active rows; shown with synthetic
  data, not on the university dataset.
- **WF27F-2:** `həndəsə` found nothing with the old search either; the other examples were confirmed.
- **WF27F-4:** reachable only on a host without a tz database, with a `--since` before 2016; no row differed.
- **MUT-P2** was labelled pre-existing; `admins()` is new in this range.
- **MUT-MINOR:** the boundary mutants differ only at exact equality.

## Measured

**`manage.py jobs check`** on the `university` dataset (124 MB `campus.db`): 0.16 s real, 0.13–0.15 s CPU, 39 MB peak
RSS, exit 1 (the dataset has no runner lease). Before: 21.2 s real, 19.9 s CPU, 790 MB.

**Prerequisite lookup** (`tools/queryplan.py --dataset university --repeat 20`, the four lookups of the `screens`
scenario): p50 2.7–3.6 ms, p95 3.0–7.8 ms (before the fix 3.9 / 9.8 ms); 5 statements; no scan. The only scans are in
the leader scenario, as before.

**Suite** (`python -m pytest -q -p no:cacheprovider -rfE`, with the browser wrappers; axe-core and Playwright
installed): see the last line in "Gate" below.

### Gate

- `ruff check .`: All checks passed!
- `mypy`: Success: no issues found in 139 source files
- `node --check` on `frontend/js/*.js`: no failure
- i18n `stats`: 100 % (en/ru ui 2 943, server 1 365, content 1 489); `lint`: 72
- `python -m pytest tests/unit tests/security -q`: part of the full run below
- full suite, browser and axe wrappers included: `2175 passed, 2 skipped, 4 warnings in 771.99s (0:12:51)` (the 2 skipped are the SEB vectors, which wait for the owner's reference `.seb` file)

No new route and no migration in the fix commit (`tests/security/matrix.json` unchanged, 333 routes).

## Not verified

- No run on a real Windows runner or in GitHub Actions: the Windows job's 45 minutes, the v7 actions by SHA, the
  EINVAL backup path with a real openssl pipe, and the socket fixes are confirmed only by a CI run.
- `jobs check` was not run inside the Docker container or by the host's cron; the cron line, the `zeka-backups`
  volume and the e-mail of the `|| mail` line need the target server.
- `clock.BAKU` before 1993 is +04 (the tz database has +03/+04 under the Soviet rules); no record of this system is
  that old.
- The prerequisite lookup's name arms sort their whole range: a two-letter prefix that starts thousands of names reads
  them all (an index range, not a scan). Measured only on the synthetic `university` names.
- No real e-mail was sent; only the outbox rows were checked.

## Remaining risk

- **WF27F-2:** a teacher who types a word from the middle of a name, or a number alone, finds nothing. A word index
  (SQLite FTS5) would bring it back, but FTS5 in the Python builds on Windows and older Linux was not checked, and a
  migration that fails stops the server.
- A host install without Docker still gets its migrations only from `run.py` or `manage.py migrate`; `jobs check`
  reports an older schema as exit 2.
- A lasting failure of one job is told once a day; a job that fails, recovers and fails again the same day is not told
  a second time.
- Checkpoint F's release recommendation is unchanged: not ready for production; ready for the owner's review and a
  pilot on a test server with synthetic data.

## Owner-dependent items

- **A private repository (the owner's decision of 2026-11-25).** Nothing in the code depends on it. GitHub's usage
  rules change, though (as of this writing; check the account's billing page):
  - Actions minutes are free only for public repositories. A private one gets the plan's monthly minutes (2 000 on
    Free), and Windows minutes count double. One push runs lint, five Linux test jobs, the Windows job (20–45 min),
    the browser job and the security scans: roughly 130–170 billed minutes, so about 12–15 pushes a month on Free.
    CI runs on every push to every branch.
  - The gitleaks action needs a licence key for a repository owned by an organisation (the workflow already says so).
  - Secret scanning and code scanning of private repositories are paid GitHub features; Dependabot alerts stay free.
  - Recommended, as common practice: run the Windows job on pull requests, `main` and by hand only, or move to a plan
    with more minutes. Not changed here: it is the owner's choice.
- The server-side steps of branch 4: the hourly backup cron, the `jobs check` cron and an external `/healthz` monitor.
- SPEC open question 20 (RPO): branch 4 proposes one hour; the SPEC is not edited.
- An official Azerbaijani qualifications framework (AzMKÇ, Cabinet decision 311 of 18.07.2018) as a built-in framework:
  proposed in `content/frameworks/README.md`, not built.
- Task 44 (release) and Checkpoint F's gate: the target server, the restore test and the `university` load test there,
  the first faculty's T0 export and its reconciliation, the SEB reference files, and the owner's written release
  decision.
