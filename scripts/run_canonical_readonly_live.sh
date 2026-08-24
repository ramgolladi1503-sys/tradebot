#!/usr/bin/env bash
set -euo pipefail

ROOT="/Volumes/TradeBotData/tradebot-readonly-live-authority-0916a95f"
cd "$ROOT"
source "$ROOT/scripts/live_credentials.sh"
exec /opt/anaconda3/bin/python "$ROOT/scripts/run_canonical_readonly_live.py" "$@"
