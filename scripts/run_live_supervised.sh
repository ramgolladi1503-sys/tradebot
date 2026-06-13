#!/usr/bin/env bash
# Safe live run supervisor — wraps main.py with restart on fatal exit.
# Does NOT enable live orders. Does NOT change safety gates.
# ALLOW_LIVE_ORDERS, MANUAL_APPROVAL_REQUIRED etc. must be set by caller.

set -euo pipefail
MAX_RESTARTS=${LIVE_SUPERVISED_MAX_RESTARTS:-10}
RESTART_WAIT_SEC=${LIVE_SUPERVISED_RESTART_WAIT_SEC:-15}
RESTART_COUNT=0

echo "[supervisor] Starting tradebot supervised run. MAX_RESTARTS=$MAX_RESTARTS"

while [ $RESTART_COUNT -lt $MAX_RESTARTS ]; do
    ATTEMPT=$((RESTART_COUNT+1))
    echo "[supervisor] Attempt $ATTEMPT/$MAX_RESTARTS"
    python main.py "$@" || EXIT_CODE=$?
    EXIT_CODE=${EXIT_CODE:-0}
    RESTART_COUNT=$((RESTART_COUNT+1))
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[supervisor] Clean exit (code 0). Not restarting."
        break
    fi
    echo "[supervisor] Exited code=$EXIT_CODE. Restarting in ${RESTART_WAIT_SEC}s..."
    sleep "$RESTART_WAIT_SEC"
done

echo "[supervisor] Done. restarts=$RESTART_COUNT"
