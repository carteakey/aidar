#!/usr/bin/env bash
# Pull latest SQLite snapshot from R2 to local aidar.db.
#
# Usage:
#   ./scripts/pull-from-r2.sh
#   AIDAR_DB=/path/to/aidar.db ./scripts/pull-from-r2.sh

set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

# shellcheck source=/dev/null
source scripts/lib/env.sh

export AIDAR_DB="${AIDAR_DB:-aidar.db}"
require_env LITESTREAM_BUCKET
require_env LITESTREAM_ENDPOINT
require_env LITESTREAM_ACCESS_KEY_ID
require_env LITESTREAM_SECRET_ACCESS_KEY

TMP_RESTORE="${AIDAR_DB}.restore.$$"
BACKUP_DIR="${BACKUP_DIR:-.db-backups}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

echo "► restoring latest DB from R2 to temp file..."
if litestream restore -config litestream.yml -if-replica-exists -o "${TMP_RESTORE}" "${AIDAR_DB}"; then
  if [ -f "${TMP_RESTORE}" ]; then
    mkdir -p "${BACKUP_DIR}"
    if [ -f "${AIDAR_DB}" ]; then
      cp "${AIDAR_DB}" "${BACKUP_DIR}/aidar-pre-pull-${TIMESTAMP}.db" || true
      echo "► backup saved: ${BACKUP_DIR}/aidar-pre-pull-${TIMESTAMP}.db"
    fi
    rm -f "${AIDAR_DB}" "${AIDAR_DB}-shm" "${AIDAR_DB}-wal"
    mv "${TMP_RESTORE}" "${AIDAR_DB}"
    echo "✓ restore complete"
  else
    echo "⚠ no replica found (kept existing local DB)"
  fi
else
  echo "⚠ restore failed (kept existing local DB)"
  rm -f "${TMP_RESTORE}" || true
fi

if [ -f "${AIDAR_DB}" ]; then
  echo "► local DB stats:"
  sqlite3 "${AIDAR_DB}" "SELECT COUNT(*) as pages, COUNT(DISTINCT domain) as domains FROM scans;" 2>/dev/null || true
fi
