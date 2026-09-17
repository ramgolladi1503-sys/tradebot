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

# 4. Remove any stale lock files
rm -f /tmp/upstox_daily_pipeline.lock

# 5. Execute unified capture and post-market stitching pipeline
echo "[*] Launching scripts/upstox_daily_live_capture_and_stitch.py..." >> "$LOG_FILE"
"$PYTHON_BIN" "$REPO_DIR/scripts/upstox_daily_live_capture_and_stitch.py" >> "$LOG_FILE" 2>&1

echo "=================================================================" >> "$LOG_FILE"
echo "Daily Pipeline completed successfully at $(date)" >> "$LOG_FILE"
echo "=================================================================" >> "$LOG_FILE"
