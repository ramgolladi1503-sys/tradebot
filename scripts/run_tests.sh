#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

STAMP="$(date +'%Y-%m-%d %H:%M:%S')"
echo "[$STAMP] Running tests..." | tee -a "$LOG_DIR/test_runs.log"

python -m pytest -q | tee -a "$LOG_DIR/test_runs.log"
