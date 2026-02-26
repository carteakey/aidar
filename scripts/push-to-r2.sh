#!/usr/bin/env bash
cd "$(dirname "$0")/.." || exit 1
export AIDAR_DB=aidar.db
export LITESTREAM_BUCKET=aidar-db
export LITESTREAM_ENDPOINT=https://4a509e96f29569f0970864f38d86563d.r2.cloudflarestorage.com
export LITESTREAM_ACCESS_KEY_ID=bc14b601f64caf7c3af752b8087a06b7
export LITESTREAM_SECRET_ACCESS_KEY=7fd881196764f660be7e4059a6692eea22aab7728c618da41e6990af0d7b2b6f
litestream replicate -config litestream.yml
