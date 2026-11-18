#!/usr/bin/env bash
# Check a backup set (manifest HMAC, SHA-256, PRAGMA integrity_check, row counts) and restore it into a new directory:
#   infra/restore.sh backups/latest.enc /tmp/restore-test
# The running data directory is never touched: stop the app, then move the restored campus.db and uploads/ into place.
set -euo pipefail
if [ "$#" -ne 2 ]; then
  echo "usage: infra/restore.sh <zeka-YYYYMMDD-HHMMSS.enc | latest.enc> <new-directory>" >&2
  exit 2
fi
exec "${PYTHON:-python3}" "$(dirname "$0")/../backend/manage.py" restore "$1" --to "$2"
