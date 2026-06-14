#!/bin/bash
cd /Users/madhuram/tradebot

PIDS=$(pgrep -f "run_live.sh|python .*main.py|kite_depth_ws|depth_ws" || true)
if [ -n "$PIDS" ]; then
  echo "Killing: $PIDS"
  kill $PIDS || true
  sleep 2
  kill -9 $PIDS 2>/dev/null || true
fi

mkdir -p .runtime/locks runtime/live_observation runtime/feed_soak
rm -f .runtime/locks/kite_session.lock .runtime/locks/depth_ws.lock
find .runtime/locks -type f -name "*.lock" -delete 2>/dev/null || true

export PYTHONPATH=.
export EXECUTION_MODE=LIVE
export TRADEBOT_MODE=LIVE
export TRADING_MODE=LIVE
export LIVE_AUDIT_ONLY=1
export ALLOW_LIVE_ORDERS=0
export AUTO_TRADE=0
export AUTO_ORDER=0
export MANUAL_APPROVAL_REQUIRED=1
export LIVE_TRADING_ENABLED=false
export FEED_SOAK_RUN=1
export FEED_OBSERVATION_RUN=1
export FEED_RECOVERY_OBSERVATION=1
export LIVE_BROKER_ADAPTER_ACTIVE=1
export MAX_DAILY_LOSS_PCT=0.02

RUN_ID="feed_stab_09_canonical_proof_live_probe_$(date +%Y%m%d_%H%M%S)"
export TRADEBOT_RUN_ID="$RUN_ID"

bash run_live.sh 2>&1 | tee "runtime/live_observation/${RUN_ID}.log"
