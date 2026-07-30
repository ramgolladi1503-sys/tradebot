#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if pgrep -af "python .*main.py|run_live.sh" >/dev/null 2>&1; then
  echo "[FEED_FRESHNESS_LIVE][FATAL] tradebot_process_already_running"
  pgrep -af "python .*main.py|run_live.sh" || true
  exit 2
fi

export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"
export TRADING_MODE="LIVE"
export EXECUTION_MODE="LIVE"
export TRADEBOT_MODE="LIVE"
export LIVE_AUDIT_ONLY="1"
export ALLOW_LIVE_ORDERS="0"
export AUTO_TRADE="0"
export AUTO_ORDER="0"
export MANUAL_APPROVAL="true"
export MANUAL_APPROVAL_REQUIRED="1"
export LIVE_TRADING_ENABLED="false"
export FEED_SOAK_RUN="0"
export FEED_OBSERVATION_RUN="1"
export FEED_RECOVERY_OBSERVATION="1"
export LIVE_BROKER_ADAPTER_ACTIVE="${LIVE_BROKER_ADAPTER_ACTIVE:-1}"
export DATA_ROOT="${DATA_ROOT:-$ROOT_DIR/.runtime}"
export DESKS_ROOT="${DESKS_ROOT:-$DATA_ROOT/desks}"
export LOGS_ROOT="${LOGS_ROOT:-$DATA_ROOT/logs}"
export REPORTS_ROOT="${REPORTS_ROOT:-$DATA_ROOT/reports}"
export LOCKS_ROOT="${LOCKS_ROOT:-$DATA_ROOT/locks}"
export DB_ROOT="${DB_ROOT:-$DATA_ROOT/db}"

python - <<'PY'
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from config import config as cfg
from core.auth_health import get_kite_auth_health
from core.market_context import derive_market_context

repo = Path(__file__).resolve().parent
resolved_runtime_mode = str(getattr(cfg, "EXECUTION_MODE", "") or "").strip().upper()
contract = {
    "repo_path": str(repo),
    "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
    "runtime_mode": resolved_runtime_mode,
    "trading_mode_env": os.getenv("TRADING_MODE"),
    "execution_mode_env": os.getenv("EXECUTION_MODE"),
    "broker_mode": "LIVE_BROKER_ADAPTER_ACTIVE=" + str(os.getenv("LIVE_BROKER_ADAPTER_ACTIVE", "")),
    "manual_approval": bool(getattr(cfg, "MANUAL_APPROVAL", True)),
    "manual_approval_required_env": os.getenv("MANUAL_APPROVAL_REQUIRED"),
    "auto_execution": {
        "LIVE_TRADING_ENABLED": os.getenv("LIVE_TRADING_ENABLED"),
        "ALLOW_LIVE_ORDERS": os.getenv("ALLOW_LIVE_ORDERS"),
        "AUTO_TRADE": os.getenv("AUTO_TRADE"),
        "AUTO_ORDER": os.getenv("AUTO_ORDER"),
    },
    "runtime_state_directory": str(Path(os.getenv("DATA_ROOT", repo / ".runtime")).resolve()),
    "diagnostic_directory": str((repo / "runtime" / "diagnostics").resolve()),
}
auth = get_kite_auth_health(force=True)
contract["auth_valid"] = bool(auth.get("ok")) and str(auth.get("auth_state") or "").upper() == "OK"
contract["auth_state"] = str(auth.get("auth_state") or "UNKNOWN")
contract["auth_user_present"] = bool(str(auth.get("user_id") or "").strip())
try:
    market_context = derive_market_context({"execution_mode": resolved_runtime_mode})
    contract["market_session"] = {
        "mode": str(getattr(market_context, "mode", "") or ""),
        "is_market_open": bool(getattr(market_context, "is_market_open", False)),
        "source": str(getattr(market_context, "source", "") or ""),
    }
except Exception as exc:
    contract["market_session"] = {"error": f"{type(exc).__name__}:{exc}"}

print("[FEED_FRESHNESS_LIVE] startup_contract=" + json.dumps(contract, sort_keys=True))

if resolved_runtime_mode != "LIVE":
    print("[FEED_FRESHNESS_LIVE][FATAL] resolved_runtime_mode_not_live")
    sys.exit(2)
if not contract["auth_valid"]:
    print("[FEED_FRESHNESS_LIVE][FATAL] auth_not_valid")
    sys.exit(12)
if contract["auto_execution"]["LIVE_TRADING_ENABLED"] != "false":
    print("[FEED_FRESHNESS_LIVE][FATAL] live_trading_enabled_not_false")
    sys.exit(2)
if contract["auto_execution"]["ALLOW_LIVE_ORDERS"] != "0":
    print("[FEED_FRESHNESS_LIVE][FATAL] allow_live_orders_not_zero")
    sys.exit(2)
PY

exec bash "$ROOT_DIR/run_live.sh" --skip-login
