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
