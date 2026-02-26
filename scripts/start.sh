#!/usr/bin/env bash
# Heroku startup script: restore SQLite from S3 via Litestream, then run app
# with continuous replication wrapping uvicorn.
#
# Required env vars (set via: heroku config:set ...):
#   LITESTREAM_BUCKET            S3 bucket name
#   LITESTREAM_ACCESS_KEY_ID     Access key (AWS/R2/B2)
#   LITESTREAM_SECRET_ACCESS_KEY Secret key
#
# Optional:
#   LITESTREAM_ENDPOINT          S3-compatible endpoint URL
#                                  Cloudflare R2: https://<account>.r2.cloudflarestorage.com
#                                  Backblaze B2:  https://s3.<region>.backblazeb2.com
#   LITESTREAM_VERSION           Binary version to download (default: 0.3.13)
#   AIDAR_DB                     DB file path (default: aidar.db)

set -euo pipefail

LITESTREAM_VERSION="${LITESTREAM_VERSION:-0.3.13}"
LITESTREAM_BIN="/tmp/litestream"
DB_PATH="${AIDAR_DB:-aidar.db}"

# ── Download litestream binary (cached in /tmp across warm restarts) ──────────
if [ ! -x "$LITESTREAM_BIN" ]; then
  echo "[litestream] Downloading v${LITESTREAM_VERSION}..."
  curl -fsSL \
    "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-amd64.tar.gz" \
    | tar xz -C /tmp
  chmod +x "$LITESTREAM_BIN"
fi

# ── If no bucket configured, run plain uvicorn (local / CI) ──────────────────
if [ -z "${LITESTREAM_BUCKET:-}" ]; then
  echo "[litestream] LITESTREAM_BUCKET not set — running without replication (ephemeral DB)."
  exec uvicorn web.main:app --host 0.0.0.0 --port "$PORT"
fi

# Build replica URL  (s3://bucket/path  or  s3://bucket/path?endpoint=...)
REPLICA_URL="s3://${LITESTREAM_BUCKET}/aidar.db"
if [ -n "${LITESTREAM_ENDPOINT:-}" ]; then
  REPLICA_URL="${REPLICA_URL}?endpoint=${LITESTREAM_ENDPOINT}"
fi

export AWS_ACCESS_KEY_ID="${LITESTREAM_ACCESS_KEY_ID}"
export AWS_SECRET_ACCESS_KEY="${LITESTREAM_SECRET_ACCESS_KEY}"

# ── Restore DB on cold start ──────────────────────────────────────────────────
echo "[litestream] Restoring ${DB_PATH} from ${REPLICA_URL} ..."
"$LITESTREAM_BIN" restore -if-no-db -o "$DB_PATH" "$REPLICA_URL" \
  && echo "[litestream] Restore complete." \
  || echo "[litestream] No existing replica found — starting fresh."

# ── Run app with continuous replication ───────────────────────────────────────
echo "[litestream] Starting with continuous replication → ${REPLICA_URL}"
exec "$LITESTREAM_BIN" replicate "$DB_PATH" "$REPLICA_URL" -- \
  uvicorn web.main:app --host 0.0.0.0 --port "$PORT"
