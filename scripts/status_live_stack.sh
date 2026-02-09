#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"

show_one() {
  local name="$1"
  local pidfile="$LOG_DIR/${name}.pid"
  local logfile="$LOG_DIR/${name}.log"
  echo "== $name =="
  if [[ -f "$pidfile" ]]; then
    local pid
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      echo "PID: $pid (running)"
    else
      echo "PID: $pid (stale)"
    fi
  else
    echo "PID: (none)"
  fi
  if [[ -f "$logfile" ]]; then
    echo "--- last 20 log lines ---"
    tail -n 20 "$logfile" || true
  else
    echo "--- no log file ---"
  fi
  echo
}

show_one "depth_ws"
show_one "main"
show_one "streamlit"
show_one "watchdog"

if [[ -x "$ROOT/scripts/feed_health_status.py" ]]; then
  echo "== feed health =="
  python "$ROOT/scripts/feed_health_status.py" || true
fi
