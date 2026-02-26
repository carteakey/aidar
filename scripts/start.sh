#!/usr/bin/env bash
# Heroku startup script: restore SQLite from S3 via Litestream, then run app
# with continuous replication wrapping uvicorn.
#
# Required env vars (set via: heroku config:set ...):
#   LITESTREAM_BUCKET            S3 bucket name
#   LITESTREAM_ACCESS_KEY_ID     Access key (AWS/R2/B2)
#   LITESTREAM_SECRET_ACCESS_KEY Secret key
#   LITESTREAM_ENDPOINT          S3-compatible endpoint URL
#                                  Cloudflare R2: https://<account>.r2.cloudflarestorage.com
#
# Optional:
#   LITESTREAM_VERSION           Binary version to download (default: 0.3.13)
#   AIDAR_DB                     DB file path (default: aidar.db)

set -euo pipefail

LITESTREAM_VERSION="${LITESTREAM_VERSION:-0.5.9}"
LITESTREAM_BIN="/tmp/litestream"
export AIDAR_DB="${AIDAR_DB:-aidar.db}"

# ── Download litestream binary ────────────────────────────────────────────────
if [ ! -x "$LITESTREAM_BIN" ]; then
  echo "[litestream] Downloading v${LITESTREAM_VERSION}..."
  curl -fsSL \
    "https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-${LITESTREAM_VERSION}-linux-x86_64.tar.gz" \
    | tar xz -C /tmp
  chmod +x "$LITESTREAM_BIN"
fi

# ── If no bucket configured, run plain uvicorn (local dev) ────────────────────
if [ -z "${LITESTREAM_BUCKET:-}" ]; then
  echo "[litestream] LITESTREAM_BUCKET not set — running without replication."
  exec uvicorn web.main:app --host 0.0.0.0 --port "$PORT"
fi

# ── Restore DB on cold start (-if-replica-exists = skip silently if no remote) ──
echo "[litestream] Restoring ${AIDAR_DB} from replica..."
"$LITESTREAM_BIN" restore -config litestream.yml -if-replica-exists "$AIDAR_DB" \
  && echo "[litestream] Restore complete." \
  || echo "[litestream] No existing replica — starting fresh."

# ── Run app with continuous replication via -exec ─────────────────────────────
echo "[litestream] Starting with continuous replication..."
exec "$LITESTREAM_BIN" replicate -config litestream.yml \
  -exec "uvicorn web.main:app --host 0.0.0.0 --port $PORT"

