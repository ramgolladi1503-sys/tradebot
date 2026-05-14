#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${DATA_ROOT:-${ROOT_DIR}/.runtime}"

if [[ -z "${RUNTIME_DIR}" || "${RUNTIME_DIR}" == "/" ]]; then
  echo "Refusing to clean unsafe runtime directory: ${RUNTIME_DIR}" >&2
  exit 1
fi

mkdir -p "${RUNTIME_DIR}"
find "${RUNTIME_DIR}" -mindepth 1 -maxdepth 1 -type f -delete
