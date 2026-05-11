#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"
RUNTIME_DIR="${ROOT}/.runtime"

if [[ -d "${RUNTIME_DIR}" ]]; then
  find "${RUNTIME_DIR}" -type f -name "*.tmp" -delete
  find "${RUNTIME_DIR}" -type f -name "*.lock" -delete
fi
