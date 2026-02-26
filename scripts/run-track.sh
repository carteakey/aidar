#!/usr/bin/env bash
# Run aidar track for a domain inside a Heroku one-off dyno.
# The one-off dyno shares the same S3 replica, so:
#   1. Restore the DB from S3
#   2. Run the track command
#   3. Upload is handled by litestream replicate on the web dyno
#      (the one-off dyno writes directly to S3 via litestream replicate)
#
# Usage: heroku run bash scripts/run-track.sh <domain>

set -euo pipefail

DOMAIN="${1:?Usage: run-track.sh <domain>}"
LITESTREAM_VERSION="${LITESTREAM_VERSION:-0.3.13}"
LITESTREAM_BIN="/tmp/litestream"
DB_PATH="${AIDAR_DB:-aidar.db}"

# Download litestream
if [ ! -x "$LITESTREAM_BIN" ]; then
  curl -fsSL \
    "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-amd64.tar.gz" \
    | tar xz -C /tmp
  chmod +x "$LITESTREAM_BIN"
fi

if [ -n "${LITESTREAM_BUCKET:-}" ]; then
  REPLICA_URL="s3://${LITESTREAM_BUCKET}/aidar.db"
  [ -n "${LITESTREAM_ENDPOINT:-}" ] && REPLICA_URL="${REPLICA_URL}?endpoint=${LITESTREAM_ENDPOINT}"
  export AWS_ACCESS_KEY_ID="${LITESTREAM_ACCESS_KEY_ID}"
  export AWS_SECRET_ACCESS_KEY="${LITESTREAM_SECRET_ACCESS_KEY}"

  echo "[litestream] Restoring DB before track..."
  "$LITESTREAM_BIN" restore -if-no-db -o "$DB_PATH" "$REPLICA_URL" || true

  # Run track with replication so writes go back to S3
  exec "$LITESTREAM_BIN" replicate "$DB_PATH" "$REPLICA_URL" -- \
    python -m aidar track "$DOMAIN" \
      --db "$DB_PATH" \
      --skip-pattern /tag/ \
      --skip-pattern /page/ \
      --skip-pattern /author/ \
      --skip-pattern /category/ \
      --limit 100 \
      --rescan-stale
else
  # No S3 — just run locally (dev/testing)
  exec python -m aidar track "$DOMAIN" --db "$DB_PATH" \
    --skip-pattern /tag/ --skip-pattern /page/ \
    --skip-pattern /author/ --skip-pattern /category/ \
    --limit 100
fi
