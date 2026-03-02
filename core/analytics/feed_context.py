from __future__ import annotations

import re
from typing import Any, Mapping

from core.feed.runtime import classify_group, get_runtime_feed_health

_FEED_STATE_RE = re.compile(r"\bfeed_state_(OK|DEGRADED|DOWN|UNKNOWN)\b", re.IGNORECASE)
_VALID_STATES = {"OK", "DEGRADED", "DOWN", "UNKNOWN"}


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _normalize_state(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in _VALID_STATES:
        return text
    return "UNKNOWN"


def _state_from_reject_reason(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    match = _FEED_STATE_RE.search(text)
    if not match:
        return None
    return _normalize_state(match.group(1))


def _empty_feed_metrics(*, flap_locked: bool | None = None) -> dict[str, Any]:
    return {
        "tick_age_p50": None,
        "tick_age_p95": None,
        "ws_age": None,
        "spread_p95": None,
        "depth_missing_pct": None,
        "tokens_recent_pct": None,
        "flap_locked": flap_locked,
    }


def _tokens_recent_pct(group_key: str, tick_age_sec: float | None, machine) -> float | None:
    if tick_age_sec is None:
        return None
    try:
        thresholds = getattr(machine, "thresholds_by_group", {}) or {}
        threshold = thresholds.get(group_key)
        ok_age = _safe_float(getattr(threshold, "ok_age_sec", None))
    except Exception:
        ok_age = None
    if ok_age is None:
        return None
    return 1.0 if float(tick_age_sec) <= float(ok_age) else 0.0


def build_feed_context(
    symbol: str,
    machine=None,
    metrics_map: Mapping[str, Any] | None = None,
    *,
    reject_reason: str | None = None,
) -> dict[str, Any]:
    """
    Build optional feed context for offline analytics events.
    Read-only: this helper never advances feed state transitions.
    """
    group_key = str(classify_group(symbol))
    if machine is None or metrics_map is None:
        runtime_machine, runtime_metrics_map = get_runtime_feed_health()
        if machine is None:
            machine = runtime_machine
        if metrics_map is None:
            metrics_map = runtime_metrics_map

    status = {}
    try:
        if hasattr(machine, "get_status"):
            status = dict(machine.get_status(group_key) or {})
    except Exception:
        status = {}

    flap_locked = status.get("flap_locked")
    state = _normalize_state(status.get("state"))
    snapshot = {}
    metrics = (metrics_map or {}).get(group_key)
    try:
        if metrics is not None and hasattr(metrics, "snapshot"):
            snapshot = dict(metrics.snapshot() or {})
    except Exception:
        snapshot = {}

    metrics_payload = _empty_feed_metrics(
        flap_locked=(bool(flap_locked) if isinstance(flap_locked, bool) else None)
    )
    if snapshot:
        tick_age = _safe_float(snapshot.get("tick_age_sec"))
        ws_age = _safe_float(snapshot.get("ws_age_sec"))
        spread_pct = _safe_float(snapshot.get("spread_pct"))
        depth_ok = snapshot.get("depth_ok")
        metrics_payload["tick_age_p50"] = tick_age
        metrics_payload["tick_age_p95"] = tick_age
        metrics_payload["ws_age"] = ws_age
        metrics_payload["spread_p95"] = spread_pct
        if depth_ok is True:
            metrics_payload["depth_missing_pct"] = 0.0
        elif depth_ok is False:
            metrics_payload["depth_missing_pct"] = 1.0
        metrics_payload["tokens_recent_pct"] = _tokens_recent_pct(group_key, tick_age, machine)

    reason_state = _state_from_reject_reason(reject_reason)
    if reason_state is not None:
        state = reason_state

    if "UNKNOWN" in group_key and reason_state is None:
        state = "UNKNOWN"

    return {
        "feed_group": group_key,
        "feed_state": state,
        "feed_metrics": metrics_payload,
    }
