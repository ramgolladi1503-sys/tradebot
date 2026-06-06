#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMMAND_CENTER_SCRIPT="$ROOT_DIR/scripts/run_tradebot_agent_command_center.py"
REPORTS_DIR="${AGENT_COMMAND_CENTER_REPORTS_DIR:-$ROOT_DIR/.runtime/agent_reports}"
RUN_DIR="${AGENT_COMMAND_CENTER_RUN_DIR:-$REPORTS_DIR/runs}"
RUN_ID="${AGENT_COMMAND_CENTER_RUN_ID:-agent_command_center_$(date -u +%Y%m%dT%H%M%SZ)}"
INTERVAL_SEC="${AGENT_COMMAND_CENTER_INTERVAL_SEC:-10}"
WATCHER_PID=""
CLEANED_UP=0

cleanup() {
  local exit_code="${1:-0}"
  if [[ "$CLEANED_UP" -eq 1 ]]; then
    return 0
  fi
  CLEANED_UP=1

  if [[ -n "$WATCHER_PID" ]] && kill -0 "$WATCHER_PID" 2>/dev/null; then
    kill "$WATCHER_PID" || true
    wait "$WATCHER_PID" 2>/dev/null || true
  fi

  python "$COMMAND_CENTER_SCRIPT" \
    --once \
    --run-id "$RUN_ID" \
    --run-dir "$RUN_DIR" \
    --out-dir "$REPORTS_DIR" \
    --copy-latest true \
    || true

  return "$exit_code"
}

trap 'cleanup 130; exit 130' INT
trap 'cleanup 143; exit 143' TERM
trap 'cleanup $?' EXIT

python "$COMMAND_CENTER_SCRIPT" \
  --watch \
  --run-id "$RUN_ID" \
  --run-dir "$RUN_DIR" \
  --out-dir "$REPORTS_DIR" \
  --interval-sec "$INTERVAL_SEC" \
  --copy-latest true \
  &
WATCHER_PID=$!

bash "$ROOT_DIR/run_live.sh" "$@"
