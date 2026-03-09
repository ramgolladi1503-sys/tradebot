#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Operational convention:
# - process pidfiles and watchdog process logs stay under repo-local logs/
# - runtime feed/suggestion/status artifacts live under core.paths.logs_dir() (typically .runtime/logs/)
PID_DIR="$ROOT/logs"
LOG_DIR="$PID_DIR"
WATCHDOG_LOG_PATH="$LOG_DIR/watchdog.log"
mkdir -p "$LOG_DIR"

INTERVAL="${WATCHDOG_INTERVAL:-30}"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]] && command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "$PYTHON_BIN"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return
  fi
  if [[ -x "/opt/anaconda3/bin/python" ]]; then
    echo "/opt/anaconda3/bin/python"
    return
  fi
  if [[ -x "/usr/bin/python3" ]]; then
    echo "/usr/bin/python3"
    return
  fi
  echo ""
}

PYTHON_BIN="$(resolve_python)"
if [[ -z "$PYTHON_BIN" ]]; then
  echo "[watchdog] Python not found. Set PYTHON_BIN or install python." >> "$WATCHDOG_LOG_PATH"
  exit 1
fi

is_running() {
  local pidfile="$1"
  [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

start_if_down() {
  local name="$1"; shift
  local pidfile="$LOG_DIR/${name}.pid"
  if is_running "$pidfile"; then
    return 0
  fi
  echo "[watchdog] Restarting $name at $(date '+%Y-%m-%d %H:%M:%S')" >> "$WATCHDOG_LOG_PATH"
  nohup "$@" >>"$LOG_DIR/${name}.log" 2>&1 &
  echo $! > "$pidfile"
}

while true; do
  start_if_down "main" "$PYTHON_BIN" "$ROOT/main.py" || true
  start_if_down "scheduler" env PYTHONPATH="$ROOT:${PYTHONPATH:-}" "$PYTHON_BIN" "$ROOT/scripts/scheduler.py" || true
  start_if_down "streamlit" "$PYTHON_BIN" -m streamlit run "$ROOT/dashboard/streamlit_app.py" \
    --server.address "${DASH_ADDR:-0.0.0.0}" --server.port "${DASH_PORT:-8501}" --server.headless true || true
  sleep "$INTERVAL"
done
