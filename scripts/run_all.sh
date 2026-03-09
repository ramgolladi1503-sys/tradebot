#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------------------------
# tradebot/scripts/run_all.sh
#
# Launches: main, scheduler, streamlit dashboard, watchdog
# Designed to be run under launchd with KeepAlive=true:
#   - starts services in background
#   - DOES NOT exit immediately (waits on child PIDs)
# ------------------------------------------------------------------------------

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Operational convention:
# - run_all/watchdog own pidfiles and process stdout/stderr under repo-local logs/
# - runtime heartbeat/feed/suggestion artifacts live under core.paths.logs_dir() (typically .runtime/logs/)
# - watchdog is the long-lived restart owner; run_all should not duplicate already-running services
PID_DIR="$ROOT/logs"
LOG_DIR="$PID_DIR"
mkdir -p "$LOG_DIR"

PORT="${DASH_PORT:-8501}"
ADDR="${DASH_ADDR:-0.0.0.0}"

resolve_python() {
  # Prefer explicit PYTHON_BIN if provided
  if [[ -n "${PYTHON_BIN:-}" ]] && command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "$PYTHON_BIN"
    return
  fi

  # Prefer python3 over python when available
  if command -v python3 >/dev/null 2>&1; then
    echo "python3"
    return
  fi
  if command -v python >/dev/null 2>&1; then
    echo "python"
    return
  fi

  # Common macOS installs
  if [[ -x "/opt/anaconda3/bin/python" ]]; then
    echo "/opt/anaconda3/bin/python"
    return
  fi
  if [[ -x "/usr/local/bin/python3" ]]; then
    echo "/usr/local/bin/python3"
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

# Track started processes so the script can "stay alive" (important for launchd)
PIDS=()

start_bg() {
  local name="$1"; shift
  local pidfile="$LOG_DIR/${name}.pid"
  local logfile="$LOG_DIR/${name}.log"

  # If pidfile exists and process is alive, don't start another
  if [[ -f "$pidfile" ]]; then
    local oldpid
    oldpid="$(cat "$pidfile" 2>/dev/null || true)"
    if [[ -n "${oldpid:-}" ]] && kill -0 "$oldpid" 2>/dev/null; then
      echo "$name already running (pid $oldpid)"
      return 0
    fi
  fi

  echo "Starting $name..."
  nohup "$@" >>"$logfile" 2>&1 &
  local pid=$!
  echo "$pid" > "$pidfile"
  PIDS+=("$pid")
  echo "$name started (pid $pid)"
}

cleanup() {
  # If launchd stops the job, try to stop children we started.
  # (nohup'd processes won't die automatically when this script is terminated)
  echo "Caught signal; stopping child processes..."
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done

  # Give a moment, then hard kill if needed
  sleep 1 || true
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  done

  echo "Cleanup complete."
}
trap cleanup INT TERM HUP

# --- Start core services ------------------------------------------------------

start_bg "main"      "$PYTHON_BIN" "$ROOT/main.py"
start_bg "scheduler" "$PYTHON_BIN" "$ROOT/scripts/scheduler.py"

# Streamlit: don't crash-loop if port is already taken; just skip starting it.
if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "Port $PORT already in use; skipping streamlit start. (Set DASH_PORT to change.)" >&2
else
  start_bg "streamlit" "$PYTHON_BIN" -m streamlit run "$ROOT/dashboard/streamlit_app.py" \
    --server.address "$ADDR" \
    --server.port "$PORT" \
    --server.headless true
fi

# Watchdog (shell script)
start_bg "watchdog" "$ROOT/scripts/watchdog.sh"

echo "Open http://<tailscale-ip>:${PORT}"
echo "Started PIDs: ${PIDS[*]:-none}"

# Keep this wrapper alive so launchd doesn't repeatedly respawn it
if [[ ${#PIDS[@]} -gt 0 ]]; then
  wait "${PIDS[@]}"
else
  echo "No new processes started."
  while true; do
    sleep 60
  done
fi
