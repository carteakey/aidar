#!/usr/bin/env bash
# scripts/force-push-to-r2.sh
#
# Use when local aidar.db has data that R2 doesn't have (e.g., after a
# big batch scan). Makes local the SINGLE source of truth by:
#   1. Checkpointing WAL into main DB
#   2. Clearing local litestream shadow WAL cache (stale cache = wrong snapshots)
#   3. Wiping R2 (removes conflicting generations from Heroku + prior pushes)
#   4. Pushing local DB fresh via litestream replicate
#   5. Verifying L1 compaction happened before Heroku can overwrite
#
# IMPORTANT: after this script, verify locally then restart Heroku quickly:
#   sqlite3 /tmp/test_restore.db "SELECT COUNT(*) FROM scans;" (should match local)
#   heroku restart --app aidar
#
# If you wait too long after this, Heroku's existing litestream daemon will
# write its stale state as new L0 frames on top of your snapshot.
#
# Requires: awscli, litestream 0.5.9, sqlite3

set -euo pipefail
cd "$(dirname "$0")/.."

# shellcheck source=/dev/null
source scripts/lib/env.sh

export AIDAR_DB="${AIDAR_DB:-aidar.db}"
require_env LITESTREAM_BUCKET
require_env LITESTREAM_ENDPOINT
require_env LITESTREAM_ACCESS_KEY_ID
require_env LITESTREAM_SECRET_ACCESS_KEY

export AWS_ACCESS_KEY_ID=$LITESTREAM_ACCESS_KEY_ID
export AWS_SECRET_ACCESS_KEY=$LITESTREAM_SECRET_ACCESS_KEY
export AWS_DEFAULT_REGION=auto

echo "=== Local DB stats ==="
sqlite3 "$AIDAR_DB" "SELECT COUNT(*) as pages, COUNT(DISTINCT domain) as domains FROM scans;"

echo ""
echo "=== Step 1: Checkpoint WAL ==="
sqlite3 "$AIDAR_DB" "PRAGMA wal_checkpoint(TRUNCATE);"
echo "WAL checkpointed. DB size: $(du -sh "$AIDAR_DB" | cut -f1)"

echo ""
echo "=== Step 2: Clear local litestream shadow WAL cache ==="
SHADOW_DIR=".${AIDAR_DB}-litestream"
if [ -d "$SHADOW_DIR" ]; then
  rm -rf "$SHADOW_DIR"
  echo "Cleared $SHADOW_DIR"
else
  echo "No local cache found (ok)"
fi

echo ""
echo "=== Step 3: Wipe R2 (removes conflicting generations) ==="
aws s3 rm "s3://${LITESTREAM_BUCKET}/aidar.db/" \
  --recursive --endpoint-url "$LITESTREAM_ENDPOINT" --quiet
echo "R2 wiped."

echo ""
echo "=== Step 4: Start litestream replicate (fresh state) ==="
litestream replicate -config litestream.yml &
REPLIC_PID=$!

# Wait for daemon to initialize
sleep 8

# Trigger a WAL write — litestream needs WAL activity to create the initial
# LTX snapshot. Without a write, it just monitors and uploads nothing.
echo "Triggering WAL write for initial snapshot..."
sqlite3 "$AIDAR_DB" "
  CREATE TABLE IF NOT EXISTS _sync_marker(ts TEXT);
  INSERT INTO _sync_marker VALUES(datetime('now'));
" 2>/dev/null || true

echo ""
echo "=== Step 5: Waiting for L1 compaction (~45s) ==="
echo "(L1 compacts 30s after first write. The compaction uploads the full DB.)"
sleep 50

echo ""
echo "=== R2 contents after push ==="
aws s3 ls "s3://${LITESTREAM_BUCKET}/aidar.db/" \
  --endpoint-url "$LITESTREAM_ENDPOINT" --recursive 2>&1 | head -10

kill $REPLIC_PID 2>/dev/null
wait $REPLIC_PID 2>/dev/null

echo ""
echo "=== Verify restore locally ==="
rm -f /tmp/aidar_verify.db
export AIDAR_DB=/tmp/aidar_verify.db
litestream restore -config litestream.yml /tmp/aidar_verify.db 2>/dev/null
sqlite3 /tmp/aidar_verify.db "SELECT COUNT(*) as pages, COUNT(DISTINCT domain) as domains FROM scans;" 2>/dev/null || echo "Restore verify failed"
rm -f /tmp/aidar_verify.db

echo ""
echo "=== Done! ==="
echo "Now run: heroku restart --app aidar"
echo "Wait 30s then check: curl https://aidar-808e7d56632e.herokuapp.com/api/leaderboard | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d),\"domains live\")'"
