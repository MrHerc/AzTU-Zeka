#!/usr/bin/env bash
# Daily encrypted backup (cron or a systemd timer). Settings from the environment, see docs/runbooks/backup.md:
#   BACKUP_KEY_FILE  file with one random line (openssl rand -base64 48 > key; chmod 600 key)
#   BACKUP_REMOTE    second host in the country: user@host:/path (ssh) or a mounted directory; required in prod
#   BACKUP_DIR       local directory (default: backups/ in the repository)
# Exit codes: 0 done, 2 the backup failed (nothing unencrypted is left), 3 the second host failed, 4 prod without
# BACKUP_REMOTE, 5 done but some uploads in the data directory are damaged (named on stderr, not in the set).
set -euo pipefail
exec "${PYTHON:-python3}" "$(dirname "$0")/../backend/manage.py" backup "$@"
