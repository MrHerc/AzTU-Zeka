# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: **Security → Report a vulnerability** on this repository
(private vulnerability reporting). Do not open a public issue for a security problem.

Include what is affected (URL or file), the steps to reproduce, and the impact you observed. We aim to acknowledge a
report within 3 working days and to agree a fix and disclosure date with you.

## Supported versions

Only the latest commit on `main` (the deployed demo) receives security fixes.

## Scope and deployment notes

Zəka is a **demo**: the login is password-less by design (SSO arrives in the pilot) and all data is synthetic.
On any host reachable from a network the server must run with `ZEKA_ACCESS_CODE` set; `run.py` refuses to start
without it. See [docs/SECURITY_REVIEW.md](docs/SECURITY_REVIEW.md) for the current review, the configuration
reference and the open items.

Never commit `config.json`, `.env` files, the `data/` folder or archives of the project folder: they can contain API
keys, session tokens and personal data. Secret scanning runs in `.github/workflows/security.yml`.
