#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

stop_one() {
  local name="$1"
  local pidfile="$LOG_DIR/${name}.pid"
  if [[ -f "$pidfile" ]]; then
    local pid
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $name (pid $pid)"
      if [[ $DRY_RUN -eq 0 ]]; then
        kill "$pid" || true
      fi
    fi
    if [[ $DRY_RUN -eq 0 ]]; then
      rm -f "$pidfile"
    fi
  else
    echo "$name not running"
  fi
}

stop_one "streamlit"
stop_one "main"
stop_one "depth_ws"
stop_one "watchdog"
