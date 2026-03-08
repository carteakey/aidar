#!/usr/bin/env bash
cd "$(dirname "$0")/.." || exit 1

# shellcheck source=/dev/null
source scripts/lib/env.sh

export AIDAR_DB="${AIDAR_DB:-aidar.db}"
require_env LITESTREAM_BUCKET
require_env LITESTREAM_ENDPOINT
require_env LITESTREAM_ACCESS_KEY_ID
require_env LITESTREAM_SECRET_ACCESS_KEY

litestream replicate -config litestream.yml
