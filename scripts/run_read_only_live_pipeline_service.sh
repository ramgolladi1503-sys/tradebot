#!/usr/bin/env bash
set -euo pipefail

ROOT="/Volumes/TradeBotData/tradebot-readonly-live-authority-0916a95f"
cd "$ROOT"
# Existing governed loader: validates mode and approved key names, and never
# prints or persists credential values. Missing binding fails closed.
source "$ROOT/scripts/live_credentials.sh"
exec /opt/anaconda3/bin/python "$ROOT/scripts/run_read_only_live_pipeline_service.py"
