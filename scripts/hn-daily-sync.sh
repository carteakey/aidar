#!/usr/bin/env bash
# Pull latest DB from R2, scan HN trending domains, push updated DB back to R2.
#
# Usage:
#   ./scripts/hn-daily-sync.sh
#   HN_DOMAINS=40 HN_STORY_LIMIT=300 ./scripts/hn-daily-sync.sh
#   HEROKU_APP=aidar RESTART_HEROKU=1 ./scripts/hn-daily-sync.sh

set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

# shellcheck source=/dev/null
source scripts/lib/env.sh

export AIDAR_DB="${AIDAR_DB:-aidar.db}"

HN_DOMAINS="${HN_DOMAINS:-25}"
HN_STORY_LIMIT="${HN_STORY_LIMIT:-250}"
HN_MIN_STORY_COUNT="${HN_MIN_STORY_COUNT:-2}"
DOMAIN_PAGE_LIMIT="${DOMAIN_PAGE_LIMIT:-200}"
CONCURRENCY="${CONCURRENCY:-10}"
MAX_CYCLES="${MAX_CYCLES:-1}"  # 1 = one daily run
RESTART_HEROKU="${RESTART_HEROKU:-0}"
HEROKU_APP="${HEROKU_APP:-aidar}"

echo "=== Step 1: pull latest DB from R2 ==="
bash scripts/pull-from-r2.sh

echo ""
echo "=== Step 2: scan HN trending domains ==="
aidar worker \
  --hn-domains "${HN_DOMAINS}" \
  --hn-story-limit "${HN_STORY_LIMIT}" \
  --hn-min-story-count "${HN_MIN_STORY_COUNT}" \
  --limit "${DOMAIN_PAGE_LIMIT}" \
  --concurrency "${CONCURRENCY}" \
  --max-cycles "${MAX_CYCLES}" \
  --db "${AIDAR_DB}"

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
echo "✓ HN daily sync complete."
