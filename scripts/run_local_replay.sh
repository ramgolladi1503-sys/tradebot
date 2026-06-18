#!/usr/bin/env bash

set -e

# Local Historical Replay Script
# This runs the outcome replay engine over a specified number of recent days
# to generate fresh TradeOutcome events in the local analytics store.
# This runs completely offline and adheres to Tradebot safety rules.

# Ensure we are in the repo root
cd "$(dirname "$0")/.."

DAYS_TO_REPLAY=${1:-30}

echo "=========================================================="
echo " Starting Local Historical Replay ($DAYS_TO_REPLAY days)"
echo "=========================================================="

export PYTHONPATH="."

# Loop over the last N days
for i in $(seq $DAYS_TO_REPLAY -1 1); do
    # MacOS date command vs Linux date command
    if [[ "$OSTYPE" == "darwin"* ]]; then
        TARGET_DATE=$(date -v-${i}d +%Y-%m-%d)
    else
        TARGET_DATE=$(date -d "${i} days ago" +%Y-%m-%d)
    fi
    
    echo " -> Replaying outcomes for $TARGET_DATE"
    
    # We allow this to fail silently if there's no data for weekends/holidays
    python -m core.analytics.outcome_replay --date "$TARGET_DATE" --scope rejected || true
done

echo "=========================================================="
echo " Replay Complete. The local analytics store is now populated."
echo " You can now run './scripts/run_walk_forward_analysis.sh'."
echo "=========================================================="
