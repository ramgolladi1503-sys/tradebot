from __future__ import annotations
from core.paths import logs_dir

import json
from pathlib import Path
from typing import Any, Dict

from config import config as cfg
from core import risk_halt
from core.time_utils import is_market_open_ist, now_ist, now_utc_epoch
from core.trade_store import fetch_open_positions_dict
from core.log_writer import get_jsonl_writer


def auto_clear_risk_halt_if_safe() -> Dict[str, Any]:
    """
    Auto-clear an active risk halt only when safety preconditions are satisfied.

    Preconditions are controlled by config and default to conservative behavior:
    - AUTO_CLEAR_RISK_HALT_ON_START=True
    - AUTO_CLEAR_RISK_HALT_REQUIRE_MARKET_CLOSED=True
    - AUTO_CLEAR_RISK_HALT_REQUIRE_NO_OPEN_POSITIONS=True
    - AUTO_CLEAR_RISK_HALT_ALLOW_MARKET_OPEN_IF_FLAT=True
    """
    now = now_ist()
    enabled = bool(getattr(cfg, "AUTO_CLEAR_RISK_HALT_ON_START", True))
    require_market_closed = bool(getattr(cfg, "AUTO_CLEAR_RISK_HALT_REQUIRE_MARKET_CLOSED", True))
    require_no_positions = bool(getattr(cfg, "AUTO_CLEAR_RISK_HALT_REQUIRE_NO_OPEN_POSITIONS", True))
    allow_market_open_if_flat = bool(getattr(cfg, "AUTO_CLEAR_RISK_HALT_ALLOW_MARKET_OPEN_IF_FLAT", True))
    market_open = bool(is_market_open_ist(now=now))

    result: Dict[str, Any] = {
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now.isoformat(),
        "enabled": enabled,
        "market_open": market_open,
        "halted_before": bool(risk_halt.is_halted()),
        "cleared": False,
        "reason_code": "NO_ACTION",
        "open_positions_count": None,
    }

    try:
        if not enabled:
            result["reason_code"] = "AUTO_CLEAR_DISABLED"
            return _write_guard_log(result)

        if not result["halted_before"]:
            result["reason_code"] = "HALT_NOT_ACTIVE"
            return _write_guard_log(result)

        open_positions_count = len(fetch_open_positions_dict(limit=5000))
        result["open_positions_count"] = open_positions_count

        if require_market_closed and market_open:
            if not (allow_market_open_if_flat and (not require_no_positions or open_positions_count == 0)):
                result["reason_code"] = "HALT_CLEAR_BLOCKED_MARKET_OPEN"
                return _write_guard_log(result)

        if require_no_positions and open_positions_count > 0:
            result["reason_code"] = "HALT_CLEAR_BLOCKED_OPEN_POSITIONS"
            return _write_guard_log(result)

        risk_halt.clear_halt()
        result["cleared"] = True
        result["reason_code"] = "HALT_AUTO_CLEARED_SAFE_SESSION_START"
        return _write_guard_log(result)
    except Exception as exc:
        result["reason_code"] = "HALT_AUTO_CLEAR_ERROR"
        result["error"] = str(exc)
        return _write_guard_log(result)


def _write_guard_log(payload: Dict[str, Any]) -> Dict[str, Any]:
    path = logs_dir() / "session_guard.jsonl"
    if not get_jsonl_writer(path).write(payload):
        raise OSError("bounded_session_guard_write_rejected")
    return payload
