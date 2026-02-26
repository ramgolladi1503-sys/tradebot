"""Migration note:
Central SLO guard for auth/feed latency with deterministic optional failover.
LIVE-open can auto-trigger failover; PAPER/SIM stays observable-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import config as cfg
from core import risk_halt
from core.auth_health import get_kite_auth_health
from core.feed_circuit_breaker import trip as trip_feed_breaker
from core.freshness_sla import get_freshness_status
from core.market_context import derive_market_context
from core.time_utils import compute_age_sec, now_ist, now_utc_epoch


def _state_path() -> Path:
    return Path(getattr(cfg, "SLO_FAILOVER_STATE_PATH", "logs/slo_failover_state.json"))


def _events_path() -> Path:
    return Path(getattr(cfg, "SLO_EVENT_LOG_PATH", "logs/slo_events.jsonl"))


def _default_state() -> dict[str, Any]:
    return {
        "consecutive_breaches": 0,
        "last_breach_ts": None,
        "last_failover_ts": None,
        "last_reasons": [],
        "failover_active": False,
    }


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _load_state() -> dict[str, Any]:
    path = _state_path()
    if not path.exists():
        return _default_state()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_state()
    if not isinstance(payload, dict):
        return _default_state()
    out = _default_state()
    out.update(payload)
    return out


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


def _append_event(payload: dict[str, Any]) -> None:
    path = _events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row = dict(payload)
    row.setdefault("ts_epoch", now_utc_epoch())
    row.setdefault("ts_ist", now_ist().isoformat())
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=True, default=str) + "\n")
    except Exception:
        pass


def evaluate_slo_status(
    *,
    auth_payload: dict[str, Any] | None = None,
    feed_payload: dict[str, Any] | None = None,
    market_context: dict[str, Any] | None = None,
    now_epoch: float | None = None,
    enforce_failover: bool = False,
) -> dict[str, Any]:
    """
    Evaluate runtime auth/feed SLOs and optionally trigger failover.
    """
    now_ts = float(now_epoch if now_epoch is not None else now_utc_epoch())
    ctx = derive_market_context(
        market_context
        or {
            "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper(),
        }
    )
    live_open = bool(ctx.mode == "LIVE" and ctx.is_market_open)
    enforce_live_only = bool(getattr(cfg, "SLO_ENFORCE_LIVE_ONLY", True))
    guard_enabled = bool(getattr(cfg, "SLO_GUARD_ENABLE", True))
    should_enforce = bool(guard_enabled and (live_open or (not enforce_live_only)))

    auth = dict(auth_payload or get_kite_auth_health(force=False) or {})
    feed = dict(feed_payload or get_freshness_status(force=True) or {})
    feed_market_open = bool(feed.get("market_open", ctx.is_market_open))
    feed_allow_stale = bool(feed.get("allow_stale_quotes", ctx.allow_stale_quotes))
    ignore_feed_stale = bool(feed_allow_stale or (not feed_market_open))

    auth_age_sec = compute_age_sec(auth.get("ts_epoch"), now_ts)
    auth_latency_sec = _coerce_float(auth.get("latency_sec"))
    ltp_age_sec = _coerce_float((feed.get("ltp") or {}).get("age_sec"))
    depth_age_sec = _coerce_float((feed.get("depth") or {}).get("age_sec"))
    depth_required = bool(
        (feed.get("depth") or {}).get(
            "required", bool(getattr(cfg, "SLA_REQUIRE_OPTIONS_DEPTH_LIVE", True))
        )
    )

    max_auth_age_sec = float(getattr(cfg, "SLO_AUTH_MAX_AGE_SEC", getattr(cfg, "GOV_AUTH_MAX_AGE_SEC", 180.0)))
    max_auth_latency_sec = float(getattr(cfg, "SLO_AUTH_MAX_LATENCY_SEC", 2.0))
    max_ltp_age_sec = _coerce_float((feed.get("ltp") or {}).get("max_age_sec"))
    if max_ltp_age_sec is None:
        max_ltp_age_sec = float(getattr(cfg, "SLO_FEED_MAX_LTP_AGE_SEC", getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5)))
    max_depth_age_sec = _coerce_float((feed.get("depth") or {}).get("max_age_sec"))
    if max_depth_age_sec is None:
        max_depth_age_sec = float(getattr(cfg, "SLO_FEED_MAX_DEPTH_AGE_SEC", getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 2.0)))

    reasons: list[str] = []
    warnings: list[str] = []
    suppressed: list[str] = []

    def _record(code: str, *, suppress: bool = False) -> None:
        if suppress:
            suppressed.append(code)
            return
        if should_enforce:
            reasons.append(code)
        else:
            warnings.append(code)

    if not bool(auth.get("ok", False)):
        _record("AUTH_UNHEALTHY")
    if auth_age_sec is None:
        _record("AUTH_TS_MISSING")
    elif auth_age_sec > max_auth_age_sec:
        _record("AUTH_STALE")
    if auth_latency_sec is None:
        _record("AUTH_LATENCY_MISSING")
    elif auth_latency_sec > max_auth_latency_sec:
        _record("AUTH_LATENCY_BREACH")

    if ltp_age_sec is None:
        _record("FEED_LTP_TS_MISSING", suppress=ignore_feed_stale)
    elif ltp_age_sec > max_ltp_age_sec:
        _record("FEED_LTP_STALE", suppress=ignore_feed_stale)

    if depth_required:
        if depth_age_sec is None:
            _record("FEED_DEPTH_TS_MISSING", suppress=ignore_feed_stale)
        elif depth_age_sec > max_depth_age_sec:
            _record("FEED_DEPTH_STALE", suppress=ignore_feed_stale)
    elif depth_age_sec is not None and depth_age_sec > max_depth_age_sec:
        _record("FEED_DEPTH_DEGRADED_OPTIONAL", suppress=ignore_feed_stale)

    state = _load_state()
    prev_consecutive = int(state.get("consecutive_breaches") or 0)
    breached = bool(reasons)
    consecutive = (prev_consecutive + 1) if breached else 0
    failover_triggered = False
    failover_reason_code = None
    failover_action = str(getattr(cfg, "SLO_FAILOVER_ACTION", "RISK_HALT") or "RISK_HALT").upper()
    failover_threshold = max(1, int(getattr(cfg, "SLO_FAILOVER_CONSECUTIVE_BREACHES", 3)))
    failover_cooldown_sec = float(getattr(cfg, "SLO_FAILOVER_COOLDOWN_SEC", 300.0))
    last_failover_ts = _coerce_float(state.get("last_failover_ts"))
    cooldown_elapsed = (
        (last_failover_ts is None)
        or (compute_age_sec(last_failover_ts, now_ts) is None)
        or (float(compute_age_sec(last_failover_ts, now_ts) or 0.0) >= failover_cooldown_sec)
    )

    if breached:
        state["last_breach_ts"] = now_ts
        state["last_reasons"] = list(reasons)

    if breached and should_enforce and enforce_failover and consecutive >= failover_threshold and cooldown_elapsed:
        details = {
            "reason_code": "SLO_FAILOVER",
            "reasons": list(reasons),
            "mode": ctx.mode,
            "market_open": bool(ctx.is_market_open),
            "consecutive_breaches": consecutive,
            "auth_age_sec": auth_age_sec,
            "auth_latency_sec": auth_latency_sec,
            "ltp_age_sec": ltp_age_sec,
            "depth_age_sec": depth_age_sec,
        }
        if failover_action in {"RISK_HALT", "HARD_HALT"}:
            try:
                risk_halt.set_halt("slo_failover", details)
            except Exception:
                pass
        if failover_action in {"RISK_HALT", "HARD_HALT", "FEED_BREAKER"}:
            try:
                trip_feed_breaker("slo_failover", meta=details)
            except Exception:
                pass
        failover_triggered = True
        failover_reason_code = "SLO_FAILOVER_TRIGGERED"
        state["last_failover_ts"] = now_ts
        state["failover_active"] = True
        _append_event(
            {
                "event": "slo_failover_triggered",
                "action": failover_action,
                **details,
            }
        )
    elif not breached:
        state["failover_active"] = False

    state["consecutive_breaches"] = consecutive
    _save_state(state)

    status = "OK"
    if failover_triggered:
        status = "FAILOVER"
    elif breached:
        status = "BREACH"
    elif warnings:
        status = "DEGRADED"

    payload = {
        "status": status,
        "ok": bool((not breached) or (not should_enforce)),
        "guard_enabled": bool(guard_enabled),
        "should_enforce": bool(should_enforce),
        "mode": ctx.mode,
        "market_open": bool(ctx.is_market_open),
        "planning_only": bool(ctx.planning_only),
        "reasons": list(reasons),
        "warnings": list(warnings),
        "suppressed_warnings": list(suppressed),
        "consecutive_breaches": int(consecutive),
        "failover_triggered": bool(failover_triggered),
        "failover_reason_code": failover_reason_code,
        "failover_action": failover_action,
        "auth": {
            "ok": bool(auth.get("ok", False)),
            "age_sec": auth_age_sec,
            "latency_sec": auth_latency_sec,
            "max_age_sec": max_auth_age_sec,
            "max_latency_sec": max_auth_latency_sec,
        },
        "feed": {
            "ltp_age_sec": ltp_age_sec,
            "depth_age_sec": depth_age_sec,
            "max_ltp_age_sec": max_ltp_age_sec,
            "max_depth_age_sec": max_depth_age_sec,
            "depth_required": bool(depth_required),
            "market_open": bool(feed_market_open),
            "allow_stale_quotes": bool(feed_allow_stale),
            "ignore_stale": bool(ignore_feed_stale),
        },
        "state_path": str(_state_path()),
    }
    _append_event(
        {
            "event": "slo_eval",
            "status": status,
            "mode": ctx.mode,
            "market_open": bool(ctx.is_market_open),
            "reasons": list(reasons),
            "warnings": list(warnings),
            "suppressed_warnings": list(suppressed),
            "consecutive_breaches": int(consecutive),
        }
    )
    return payload
