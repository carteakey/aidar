#!/usr/bin/env bash
# Pull latest DB from R2 (what Heroku has), scan a domain, push back.
# This keeps local and production in sync — always work from the latest state.
#
# Usage: ./scripts/track-and-sync.sh <domain> [--limit N]
#   e.g. ./scripts/track-and-sync.sh medium.com
#        ./scripts/track-and-sync.sh substack.com --limit 300
#
# Requires: aidar (local install), litestream, sqlite3
# Env vars: AIDAR_DB, LITESTREAM_BUCKET, LITESTREAM_ENDPOINT,
#           LITESTREAM_ACCESS_KEY_ID, LITESTREAM_SECRET_ACCESS_KEY
#           (source from .env or set in shell before running)

set -euo pipefail

DOMAIN="${1:?Usage: track-and-sync.sh <domain> [--limit N]}"
shift
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AIDAR_DB="${AIDAR_DB:-$REPO_ROOT/aidar.db}"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/.db-backups}"
CONFIG="$REPO_ROOT/litestream.yml"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

if [ -z "${LITESTREAM_BUCKET:-}" ]; then
  echo "⚠ LITESTREAM_BUCKET not set — running scan locally only (no R2 sync)"
  aidar track "$DOMAIN" --db "$AIDAR_DB" \
    --skip-pattern /tag/ --skip-pattern /page/ \
    --skip-pattern /author/ --skip-pattern /category/ "$@"
  exit 0
fi

# ── 1. Backup current local DB before overwriting ────────────────────────────
mkdir -p "$BACKUP_DIR"
if [ -f "$AIDAR_DB" ]; then
  cp "$AIDAR_DB" "$BACKUP_DIR/aidar-pre-restore-${TIMESTAMP}.db"
  echo "► local backup saved to $BACKUP_DIR/aidar-pre-restore-${TIMESTAMP}.db"
fi

# ── 2. Pull latest from R2 ───────────────────────────────────────────────────
echo "► restoring latest DB from R2..."
litestream restore -config "$CONFIG" -if-replica-exists "$AIDAR_DB" \
  && echo "  ✓ restored from R2" \
  || echo "  ⚠ no replica found, using existing local DB"

# ── 3. Scan ──────────────────────────────────────────────────────────────────
echo "► scanning $DOMAIN..."
aidar track "$DOMAIN" \
  --db "$AIDAR_DB" \
  --skip-pattern /tag/ \
  --skip-pattern /page/ \
  --skip-pattern /author/ \
  --skip-pattern /category/ \
  "$@"

# ── 4. Checkpoint WAL ────────────────────────────────────────────────────────
echo "► checkpointing WAL..."
sqlite3 "$AIDAR_DB" "PRAGMA wal_checkpoint(TRUNCATE);"

# ── 5. Backup post-scan ───────────────────────────────────────────────────────
cp "$AIDAR_DB" "$BACKUP_DIR/aidar-post-scan-${TIMESTAMP}-${DOMAIN/\//-}.db"
echo "► post-scan backup saved"

# Prune backups older than 30 days
find "$BACKUP_DIR" -name "aidar-*.db" -mtime +30 -delete 2>/dev/null || true

# ── 6. Push back to R2 ───────────────────────────────────────────────────────
echo "► replicating updated DB back to R2..."
timeout 45 litestream replicate -config "$CONFIG" || true

echo ""
echo "✓ done — $DOMAIN scanned and synced to R2"
echo "  Heroku will see the new data on next dyno restart (or run):"
echo "  heroku restart --app aidar"
