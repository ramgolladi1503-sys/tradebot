#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

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
  echo "Python not found. Set PYTHON_BIN or install python." >&2
  exit 1
fi

PORT="${DASH_PORT:-8501}"
ADDR="${DASH_ADDR:-0.0.0.0}"

start_bg() {
  local name="$1"; shift
  local pidfile="$LOG_DIR/${name}.pid"
  if [[ -f "$pidfile" ]]; then
    if kill -0 "$(cat "$pidfile")" 2>/dev/null; then
      echo "$name already running (pid $(cat "$pidfile"))"
      return 0
    fi
  fi
  echo "Starting $name..."
  if [[ $DRY_RUN -eq 1 ]]; then
    echo "DRY RUN: $*"
    return 0
  fi
  nohup "$@" >>"$LOG_DIR/${name}.log" 2>&1 &
  echo $! > "$pidfile"
  echo "$name started (pid $!)"
}

start_bg "depth_ws" "$PYTHON_BIN" "$ROOT/scripts/start_depth_ws.py"
start_bg "main" "$PYTHON_BIN" "$ROOT/main.py"

if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Set DASH_PORT to a free port and re-run." >&2
  exit 1
fi

start_bg "streamlit" "$PYTHON_BIN" -m streamlit run "$ROOT/dashboard/streamlit_app.py" \
  --server.address "$ADDR" --server.port "$PORT" --server.headless true
start_bg "watchdog" "$ROOT/scripts/watchdog.sh"

echo "Open http://<tailscale-ip>:${PORT}"
