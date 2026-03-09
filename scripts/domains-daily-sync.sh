#!/usr/bin/env bash
# Pull latest DB from R2, scan existing domains from a file, push DB back to R2.
#
# Usage:
#   ./scripts/domains-daily-sync.sh
#   DOMAINS_FILE=domains.txt ./scripts/domains-daily-sync.sh
#   HEROKU_APP=aidar RESTART_HEROKU=1 ./scripts/domains-daily-sync.sh

set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

# shellcheck source=/dev/null
source scripts/lib/env.sh

export AIDAR_DB="${AIDAR_DB:-aidar.db}"
DOMAINS_FILE="${DOMAINS_FILE:-domains.txt}"
FAILED_LOG="${FAILED_LOG:-failed-discovery.log}"
INTERVAL_MINUTES="${INTERVAL_MINUTES:-1440}"
LIMIT="${LIMIT:-200}"
CONCURRENCY="${CONCURRENCY:-10}"
MAX_CYCLES="${MAX_CYCLES:-1}"  # 1 = one daily run
RESTART_HEROKU="${RESTART_HEROKU:-0}"
HEROKU_APP="${HEROKU_APP:-aidar}"

if [ ! -f "${DOMAINS_FILE}" ]; then
  echo "ERROR: domains file not found: ${DOMAINS_FILE}"
  exit 1
fi

echo "=== Step 1: pull latest DB from R2 ==="
bash scripts/pull-from-r2.sh

echo ""
echo "=== Step 2: scan existing domains from ${DOMAINS_FILE} ==="
aidar worker \
  --domains-file "${DOMAINS_FILE}" \
  --interval-minutes "${INTERVAL_MINUTES}" \
  --limit "${LIMIT}" \
  --concurrency "${CONCURRENCY}" \
  --max-cycles "${MAX_CYCLES}" \
  --db "${AIDAR_DB}" \
  ${FAILED_LOG:+--failed-log "${FAILED_LOG}"}

echo ""
echo "=== Step 3: checkpoint WAL ==="
sqlite3 "${AIDAR_DB}" "PRAGMA wal_checkpoint(TRUNCATE);"

echo ""
echo "=== Step 4: push updated DB to R2 ==="
bash scripts/push-to-r2.sh

if [ "${RESTART_HEROKU}" = "1" ]; then
  if command -v heroku >/dev/null 2>&1; then
    echo ""
    echo "=== Step 5: restart Heroku app (${HEROKU_APP}) ==="
    heroku restart --app "${HEROKU_APP}"
  else
    echo "⚠ heroku CLI not found; skipping restart."
  fi
fi

echo ""
echo "✓ Domain daily sync complete."

