#!/usr/bin/env bash
# ==============================================================================
# Sentinel Friday October 16, 2026 Morning Operational Launch Harness
# Scheduled for: 09:00:00 IST (03:30:00 UTC)
# Components:
#   1. NIFTY Sentinel Engine (PR #968 in /private/tmp/tradebot-nifty-engine)
#   2. NIFTY Dashboard (Streamlit on port 8501)
#   3. SENSEX Sentinel Engine (PR #980 in /private/tmp/tradebot-sensex-engine)
#   4. SENSEX Dashboard (Streamlit on port 8502)
#   5. Sentinel Passive Challenger Observer (PR #985 in /private/tmp/tradebot-sentinel-quant-audit)
#
# Non-negotiable Trading Safety Rules:
# - Read-only, paper-shadow mode only.
# - Zero broker order routing.
# ==============================================================================

set -euo pipefail

LOG_DIR="/private/tmp/tradebot-sentinel-quant-audit/runtime/logs_oct16"
mkdir -p "$LOG_DIR"

PYTHON_BIN="/opt/anaconda3/bin/python"
STREAMLIT_BIN="/opt/anaconda3/bin/streamlit"

echo "=================================================================="
echo "🛰️ Sentinel Friday Oct 16 Parallel Execution Launch Initiated..."
echo "Timestamp: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=================================================================="

# 1. Pre-Flight Calendar & Manifest Verification
echo "[1/6] Running Pre-Flight Verification Gate..."
"$PYTHON_BIN" -c "
from core.expiry_calendar import is_holiday
from datetime import date
assert not is_holiday(date(2026, 10, 16)), 'Oct 16 is marked as a holiday!'
print('Trading Calendar Verified: Active trading session.')
"
"$PYTHON_BIN" -c "
from core.model_manifest_generator import SentinelManifestLock
lock_n = SentinelManifestLock(artifact_directory='/private/tmp/tradebot-nifty-engine/artifacts')
assert lock_n.verify_manifest_or_fail_closed(), 'NIFTY model manifest lock failed!'
lock_s = SentinelManifestLock(artifact_directory='/private/tmp/tradebot-sensex-engine/artifacts')
assert lock_s.verify_manifest_or_fail_closed(), 'SENSEX model manifest lock failed!'
print('Model Manifests Verified for both NIFTY and SENSEX.')
"

# 2. Launch NIFTY Sentinel Paper-Shadow Engine (PR #968)
echo "[2/6] Launching NIFTY Sentinel Paper-Shadow Engine..."
(
    cd /private/tmp/tradebot-nifty-engine
    export PYTHONPATH="."
    "$PYTHON_BIN" -u scripts/run_live_feed_advisor.py > "$LOG_DIR/nifty_engine.log" 2>&1
) &
NIFTY_PID=$!
echo "NIFTY Sentinel Engine started with PID: $NIFTY_PID"

# 3. Launch NIFTY Streamlit Dashboard (Port 8501)
echo "[3/6] Launching NIFTY Streamlit Dashboard (Port 8501)..."
(
    cd /private/tmp/tradebot-nifty-engine
    export PYTHONPATH="."
    "$STREAMLIT_BIN" run scripts/run_sentinel_dashboard.py --server.port 8501 --server.headless true > "$LOG_DIR/nifty_dashboard.log" 2>&1
) &
NIFTY_DASH_PID=$!
echo "NIFTY Dashboard started with PID: $NIFTY_DASH_PID on port 8501"

# 4. Launch SENSEX Sentinel Paper-Shadow Engine (PR #980)
echo "[4/6] Launching SENSEX Sentinel Paper-Shadow Engine..."
(
    cd /private/tmp/tradebot-sensex-engine
    export PYTHONPATH="."
    "$PYTHON_BIN" -u scripts/run_live_feed_advisor.py --ticker SENSEX > "$LOG_DIR/sensex_engine.log" 2>&1
) &
SENSEX_PID=$!
echo "SENSEX Sentinel Engine started with PID: $SENSEX_PID"

# 5. Launch SENSEX Streamlit Dashboard (Port 8502)
echo "[5/6] Launching SENSEX Streamlit Dashboard (Port 8502)..."
(
    cd /private/tmp/tradebot-sensex-engine
    export PYTHONPATH="."
    "$STREAMLIT_BIN" run scripts/run_sentinel_dashboard.py --server.port 8502 --server.headless true > "$LOG_DIR/sensex_dashboard.log" 2>&1
) &
SENSEX_DASH_PID=$!
echo "SENSEX Dashboard started with PID: $SENSEX_DASH_PID on port 8502"

# 6. Launch Sentinel Passive Challenger Observer Daemon (PR #985)
echo "[6/6] Launching Sentinel Passive Challenger Observer Daemon..."
(
    cd /private/tmp/tradebot-sentinel-quant-audit
    export PYTHONPATH="."
    export SHADOW_NIFTY_WAL_PATH="/private/tmp/tradebot-nifty-engine/runtime/sentinel_apm_wal.json"
    export SHADOW_SENSEX_WAL_PATH="/private/tmp/tradebot-sensex-engine/runtime/sentinel_apm_wal_sensex.json"
    export SHADOW_STATE_PATH="runtime/shadow_evaluator_live_state.json"
    export SHADOW_ALLOW_FRESH_INIT=true
    export SHADOW_MAX_CLOCK_SKEW_SEC=300.0
    "$PYTHON_BIN" -u scripts/run_prospective_shadow_observer.py > "$LOG_DIR/shadow_observer.log" 2>&1
) &
OBSERVER_PID=$!
echo "Passive Observer Daemon started with PID: $OBSERVER_PID"

echo "$NIFTY_PID $NIFTY_DASH_PID $SENSEX_PID $SENSEX_DASH_PID $OBSERVER_PID" > "$LOG_DIR/running_pids.txt"
echo "All 5 processes successfully launched in background."
echo "PID manifest saved to $LOG_DIR/running_pids.txt"
