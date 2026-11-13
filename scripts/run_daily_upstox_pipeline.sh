#!/bin/bash
# ==============================================================================
# Upstox Daily Live Market Capture & Automatic Post-Close Stitching Runner
# Scheduled for: 08:58 AM IST (Monday - Friday)
# ==============================================================================

set -euo pipefail

REPO_DIR="/Users/madhuram/tradebot"
cd "$REPO_DIR"

# Ensure logs directory exists
mkdir -p "$REPO_DIR/logs"
LOG_FILE="$REPO_DIR/logs/upstox_daily_pipeline_$(date +%Y%m%d).log"

echo "=================================================================" >> "$LOG_FILE"
echo "Starting Upstox Daily Market Capture Pipeline at $(date)" >> "$LOG_FILE"
echo "=================================================================" >> "$LOG_FILE"

# 1. Skip weekends (Saturday=6, Sunday=7)
DOW=$(date +%u)
if [ "$DOW" -gt 5 ]; then
    echo "[!] Today is weekend (DOW: $DOW). Skipping execution." >> "$LOG_FILE"
    exit 0
fi

# 2. Check NSE Trading Holidays
TODAY=$(date +%Y-%m-%d)
HOLIDAYS="2026-09-14"
if [[ " $HOLIDAYS " =~ " $TODAY " ]]; then
    echo "[!] Today ($TODAY) is an exchange trading holiday. Skipping execution." >> "$LOG_FILE"
    exit 0
fi

# 2. Check Python Environment
PYTHON_BIN="/opt/anaconda3/bin/python3"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="$(which python3)"
fi

# 3. Verify .env exists and token is set
if [ ! -f "$REPO_DIR/.env" ]; then
    echo "[!] Error: .env file missing in $REPO_DIR" >> "$LOG_FILE"
    exit 1
fi

# 3A. BOD APM WAL Reset Preflight (08:55 AM IST)
echo "[*] Executing BOD APM WAL reset preflight..." >> "$LOG_FILE"
"$PYTHON_BIN" "$REPO_DIR/scripts/ops/reset_sentinel_wal_for_session.py" --force >> "$LOG_FILE" 2>&1 || true

# 3B. Upstox Token Preflight Auth Guard (09:00 AM IST)
echo "[*] Validating Upstox Access Token preflight authorization..." >> "$LOG_FILE"
set +e
"$PYTHON_BIN" -c '
import os, sys, urllib.request, json
from pathlib import Path
env_path = Path(".env")
token = ""
if env_path.exists():
    for line in env_path.read_text().splitlines():
        if line.startswith("UPSTOX_ACCESS_TOKEN="):
            token = line.split("=", 1)[1].strip().strip(""'''")
            break
if not token:
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
if not token:
    print("[!] CRITICAL PREFLIGHT: UPSTOX_ACCESS_TOKEN is empty!")
    sys.exit(1)

req = urllib.request.Request(
    "https://api.upstox.com/v2/user/profile",
    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
)
try:
    with urllib.request.urlopen(req, timeout=5) as resp:
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            user_name = data.get("data", {}).get("user_name", "Authorized User")
            print(f"[✓] Upstox Access Token Preflight Validated ({user_name})")
            sys.exit(0)
        else:
            print(f"[!] Preflight HTTP status: {resp.status}")
            sys.exit(2)
except urllib.error.HTTPError as he:
    print(f"[!] CRITICAL AUTH FAILURE: Upstox Access Token Expired (HTTP {he.code}): {he.reason}")
    sys.exit(2)
except Exception as e:
    print(f"[*] Network check skipped or unreachable: {e}")
    sys.exit(0)
' >> "$LOG_FILE" 2>&1
AUTH_CODE=$?
set -e

if [ "$AUTH_CODE" -eq 2 ]; then
    echo "[!] CRITICAL: Halting daily pipeline due to expired Upstox Access Token (HTTP 401/403)." >> "$LOG_FILE"
    echo "[!] Please renew token in .env or run authentication helper before market open." >> "$LOG_FILE"
    exit 2
fi

# 4. Lock file management: Do NOT remove /tmp/upstox_daily_pipeline.lock.
# flock uses kernel file locks atomically; removing the lock file breaks mutex isolation
# for concurrently starting or running instances. Preserving the lock file ensures safe atomic mutual exclusion.

# 5. Launch Sentinel Dashboard on port 8503 if not already running
STREAMLIT_BIN="/opt/anaconda3/bin/streamlit"
if [ ! -f "$STREAMLIT_BIN" ]; then
    STREAMLIT_BIN="$(which streamlit)"
fi
DASHBOARD_LOG="$REPO_DIR/logs/sentinel_dashboard_$(date +%Y%m%d).log"

if ! lsof -i :8503 > /dev/null 2>&1; then
    echo "[*] Starting Sentinel Dashboard on http://localhost:8503..." >> "$LOG_FILE"
    nohup "$STREAMLIT_BIN" run "$REPO_DIR/scripts/run_sentinel_dashboard.py" \
        --server.headless true \
        --server.port 8503 > "$DASHBOARD_LOG" 2>&1 &
    echo "[✓] Dashboard started in background with PID: $!" >> "$LOG_FILE"
else
    echo "[✓] Dashboard is already active on port 8503." >> "$LOG_FILE"
fi

# 6. Execute unified capture and post-market stitching pipeline
echo "[*] Launching scripts/upstox_daily_live_capture_and_stitch.py..." >> "$LOG_FILE"
"$PYTHON_BIN" "$REPO_DIR/scripts/upstox_daily_live_capture_and_stitch.py" >> "$LOG_FILE" 2>&1

echo "=================================================================" >> "$LOG_FILE"
echo "Daily Pipeline completed successfully at $(date)" >> "$LOG_FILE"
echo "=================================================================" >> "$LOG_FILE"
