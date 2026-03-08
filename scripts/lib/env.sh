#!/usr/bin/env bash

# Shared env loading and validation helpers for local scripts.

set -euo pipefail

SCRIPT_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${REPO_ROOT:-$(cd "${SCRIPT_LIB_DIR}/../.." && pwd)}"

# Auto-load .env if present.
if [ -f "${REPO_ROOT}/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "${REPO_ROOT}/.env"
  set +a
fi

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "ERROR: required env var '${name}' is not set."
    return 1
  fi
}
