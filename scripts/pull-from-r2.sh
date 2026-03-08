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

echo "► restoring ${AIDAR_DB} from R2..."
litestream restore -config litestream.yml -if-replica-exists "${AIDAR_DB}" \
  && echo "✓ restore complete" \
  || echo "⚠ no replica found (or restore skipped)"

if [ -f "${AIDAR_DB}" ]; then
  echo "► local DB stats:"
  sqlite3 "${AIDAR_DB}" "SELECT COUNT(*) as pages, COUNT(DISTINCT domain) as domains FROM scans;" 2>/dev/null || true
fi
