#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================================"
echo " Starting Aixion TradeBot Pocket Companion Service      "
echo "========================================================"

export TRADEBOT_ROOT="/Users/madhuram/tradebot"
export PYTHONPATH="$REPO_DIR:${PYTHONPATH:-}"

cd "$REPO_DIR"
exec /Users/madhuram/tradebot/.venv/bin/python -m uvicorn pocket_companion.service:app --host 0.0.0.0 --port 8765
