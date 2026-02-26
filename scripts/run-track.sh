#!/usr/bin/env bash
# Run aidar track for a domain inside a Heroku one-off dyno.
# Usage: heroku run bash scripts/run-track.sh <domain>

set -euo pipefail

DOMAIN="${1:?Usage: run-track.sh <domain>}"
LITESTREAM_VERSION="${LITESTREAM_VERSION:-0.5.9}"
LITESTREAM_BIN="/tmp/litestream"
export AIDAR_DB="${AIDAR_DB:-aidar.db}"

# Download litestream
if [ ! -x "$LITESTREAM_BIN" ]; then
  curl -fsSL \
    "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-x86_64.tar.gz" \
    | tar xz -C /tmp
  chmod +x "$LITESTREAM_BIN"
fi

if [ -n "${LITESTREAM_BUCKET:-}" ]; then
  echo "[litestream] Restoring DB before track..."
  "$LITESTREAM_BIN" restore -config litestream.yml -if-replica-exists "$AIDAR_DB" || true

  # Run track with replication so writes sync back to S3
  exec "$LITESTREAM_BIN" replicate -config litestream.yml \
    -exec "python -m aidar track $DOMAIN \
      --db $AIDAR_DB \
      --skip-pattern /tag/ \
      --skip-pattern /page/ \
      --skip-pattern /author/ \
      --skip-pattern /category/ \
      --limit 100 \
      --rescan-stale"
else
  exec python -m aidar track "$DOMAIN" --db "$AIDAR_DB" \
    --skip-pattern /tag/ --skip-pattern /page/ \
    --skip-pattern /author/ --skip-pattern /category/ \
    --limit 100
fi
