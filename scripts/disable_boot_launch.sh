#!/usr/bin/env bash
set -euo pipefail

PLIST="$HOME/Library/LaunchAgents/com.axiom.tradingbot.plist"

if [[ -f "$PLIST" ]]; then
  launchctl unload "$PLIST" || true
  rm -f "$PLIST"
  echo "LaunchAgent removed: $PLIST"
else
  echo "LaunchAgent not found: $PLIST"
fi
