"""Runtime health snapshot helper.

Produces a compact JSON snapshot for operator dashboards and CLI checks.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import config as cfg
from core.feed_debug import get_feed_debug
from core.freshness_sla import get_freshness_status
from core.time_utils import is_market_open_ist, now_utc_epoch


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


def get_runtime_health(orchestrator: Any | None = None, now_epoch: float | None = None) -> dict[str, Any]:
    ts_epoch = float(now_epoch if now_epoch is not None else now_utc_epoch())
    freshness = dict(get_freshness_status(force=False) or {})
    feed_debug = dict(get_feed_debug(now_epoch=ts_epoch) or {})

    market_open = bool(freshness.get("market_open", is_market_open_ist()))
    mode = str(
        freshness.get("mode")
        or freshness.get("execution_mode")
        or getattr(cfg, "EXECUTION_MODE", "SIM")
    ).upper()

    ltp_age = None
    depth_age = None
    ltp_block = freshness.get("ltp") or {}
    depth_block = freshness.get("depth") or {}
    if isinstance(ltp_block, dict):
        ltp_age = ltp_block.get("age_sec")
    if isinstance(depth_block, dict):
        depth_age = depth_block.get("age_sec")

    feed = {
        "ws_connected": feed_debug.get("ws_connected"),
        "subscriptions_count": feed_debug.get("subscribed_tokens_count"),
        "last_tick_age_sec": feed_debug.get("last_tick_age_sec"),
        "ltp_age_sec": ltp_age,
        "depth_age_sec": depth_age,
        "sla_status": freshness.get("state"),
        "reasons": list(freshness.get("reasons") or []),
    }

    execution_engine = getattr(orchestrator, "execution_engine", None)
    kill_switch_triggered = None
    kill_switch_reason = None
    last_spread_decision = None
    recon = {"daemon_running": None, "last_cycle_ts_epoch": None}
    if execution_engine is not None:
        kill_switch_triggered = getattr(execution_engine, "kill_switch_triggered", None)
        kill_switch_reason = getattr(execution_engine, "kill_switch_reason", None)
        try:
            last_spread_decision = execution_engine.get_last_spread_decision()
        except Exception:
            last_spread_decision = None
        try:
            recon = execution_engine.get_reconciliation_status()
        except Exception:
            recon = {"daemon_running": None, "last_cycle_ts_epoch": None}

    risk_state = getattr(orchestrator, "risk_state", None)
    risk = {
        "hard_halt": None,
        "daily_pnl_pct": None,
        "open_risk_pct": None,
    }
    if risk_state is not None:
        try:
            risk["hard_halt"] = bool(getattr(risk_state, "mode", "") == "HARD_HALT")
        except Exception:
            risk["hard_halt"] = None
        try:
            risk["daily_pnl_pct"] = float(getattr(risk_state, "daily_pnl_pct", 0.0))
        except Exception:
            risk["daily_pnl_pct"] = None
        try:
            risk["open_risk_pct"] = float(getattr(risk_state, "open_risk_pct", 0.0))
        except Exception:
            risk["open_risk_pct"] = None

    execution = {
        "kill_switch_triggered": kill_switch_triggered,
        "kill_switch_reason": kill_switch_reason,
        "last_spread_decision": last_spread_decision,
    }

    return {
        "ts_epoch": ts_epoch,
        "mode": mode,
        "market_open": market_open,
        "feed": feed,
        "execution": execution,
        "risk": risk,
        "recon": recon,
    }


def write_runtime_health_snapshot(orchestrator: Any | None = None, path: str | Path | None = None) -> dict[str, Any]:
    payload = get_runtime_health(orchestrator=orchestrator)
    target = Path(path or getattr(cfg, "RUNTIME_HEALTH_PATH", "logs/runtime_health_latest.json"))
    _atomic_write(target, payload)
    return payload
