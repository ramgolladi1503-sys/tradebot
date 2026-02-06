#!/usr/bin/env bash
set -euo pipefail

PLIST="$HOME/Library/LaunchAgents/com.axiom.tradingbot.plist"

if [[ -f "$PLIST" ]]; then
  echo "LaunchAgent plist: $PLIST"
  echo "Loaded status:" 
  launchctl list | grep com.axiom.tradingbot || echo "Not loaded"
else
  echo "LaunchAgent plist not found: $PLIST"
fi
