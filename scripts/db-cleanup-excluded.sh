#!/usr/bin/env bash
# Remove scans for domains listed in domain_exclude.txt from the local SQLite DB.
#
# Usage:
#   ./scripts/db-cleanup-excluded.sh
#   EXCLUDE_FILE=my_list.txt AIDAR_DB=aidar.db ./scripts/db-cleanup-excluded.sh
#
# pattern_scores rows are removed automatically via ON DELETE CASCADE.
# Run this after editing domain_exclude.txt to keep the DB lean.

set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

# shellcheck source=/dev/null
source scripts/lib/env.sh

AIDAR_DB="${AIDAR_DB:-aidar.db}"
EXCLUDE_FILE="${EXCLUDE_FILE:-domain_exclude.txt}"

if [ ! -f "${AIDAR_DB}" ]; then
  echo "ERROR: database not found: ${AIDAR_DB}"
  exit 1
fi

if [ ! -f "${EXCLUDE_FILE}" ]; then
  echo "ERROR: exclude file not found: ${EXCLUDE_FILE}"
  exit 1
fi

# Parse exclude file: strip comments, inline comments, www. prefix, lowercase
mapfile -t DOMAINS < <(
  grep -v '^\s*#' "${EXCLUDE_FILE}" \
  | sed 's/#.*//' \
  | tr '[:upper:]' '[:lower:]' \
  | sed 's/^www\.//' \
  | awk '{$1=$1; print}' \
  | grep -v '^$'
)

if [ "${#DOMAINS[@]}" -eq 0 ]; then
  echo "No domains to clean up in ${EXCLUDE_FILE}."
  exit 0
fi

echo "=== DB Cleanup: excluded domains ==="
echo "DB:           ${AIDAR_DB}"
echo "Exclude file: ${EXCLUDE_FILE} (${#DOMAINS[@]} domains)"
echo ""

# Build SQL IN list
IN_LIST=$(printf "'%s'," "${DOMAINS[@]}")
IN_LIST="${IN_LIST%,}"   # strip trailing comma

BEFORE=$(sqlite3 "${AIDAR_DB}" "SELECT COUNT(*) FROM scans WHERE domain IN (${IN_LIST});")

if [ "${BEFORE}" -eq 0 ]; then
  echo "Nothing to delete — no scans found for excluded domains."
  exit 0
fi

echo "Scans to delete: ${BEFORE}"
echo "Domains:"
for d in "${DOMAINS[@]}"; do
  CNT=$(sqlite3 "${AIDAR_DB}" "SELECT COUNT(*) FROM scans WHERE domain = '${d}';")
  if [ "${CNT}" -gt 0 ]; then
    printf "  %-40s %d scans\n" "${d}" "${CNT}"
  fi
done
echo ""

read -r -p "Proceed with deletion? [y/N] " CONFIRM
if [[ ! "${CONFIRM}" =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 0
fi

sqlite3 "${AIDAR_DB}" "DELETE FROM scans WHERE domain IN (${IN_LIST});"
sqlite3 "${AIDAR_DB}" "PRAGMA wal_checkpoint(TRUNCATE);"

AFTER=$(sqlite3 "${AIDAR_DB}" "SELECT COUNT(*) FROM scans;")
echo ""
echo "✓ Deleted ${BEFORE} scans. Remaining total: ${AFTER}."
