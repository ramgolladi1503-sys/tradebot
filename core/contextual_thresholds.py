from __future__ import annotations

from typing import Any, Mapping

from config import config as cfg

_HARD_PROTECT_STAGES = {"risk_budget", "portfolio_heat", "kill_switch"}
_ADJUSTABLE_STAGES = {"trigger", "entry_quality", "family_survival"}


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _normalized_key(stage: Any, family: Any, session: Any, regime: Any) -> str:
    return "|".join(
        [
            str(stage or "unknown").strip().lower() or "unknown",
            str(family or "unknown").strip().lower() or "unknown",
            str(session or "UNKNOWN").strip().upper() or "UNKNOWN",
            str(regime or "UNKNOWN").strip().upper() or "UNKNOWN",
        ]
    )


def get_contextual_threshold_delta(
    stage: str | None,
    family: str | None,
    session: str | None,
    regime: str | None,
    recommendations: Mapping[str, Any] | None,
) -> float:
    normalized_stage = str(stage or "unknown").strip().lower() or "unknown"
    normalized_family = str(family or "unknown").strip().lower() or "unknown"
    normalized_session = str(session or "UNKNOWN").strip().upper() or "UNKNOWN"
    normalized_regime = str(regime or "UNKNOWN").strip().upper() or "UNKNOWN"
    if normalized_stage not in _ADJUSTABLE_STAGES:
        return 0.0
    if normalized_stage in _HARD_PROTECT_STAGES:
        return 0.0

    payload = dict(recommendations or {})
    protected_gate_map = payload.get("protected_gate_map") or {}
    if isinstance(protected_gate_map, Mapping):
        gate_key = f"{normalized_stage}|{normalized_family}"
        if bool((protected_gate_map.get(gate_key) or {}).get("gate_protected_flag", False)):
            return 0.0

    adjustments = payload.get("recommended_contextual_adjustments") or {}
    if not isinstance(adjustments, Mapping):
        return 0.0

    lookup_keys = [
        _normalized_key(normalized_stage, normalized_family, normalized_session, normalized_regime),
        _normalized_key(normalized_stage, normalized_family, normalized_session, "UNKNOWN"),
        _normalized_key(normalized_stage, normalized_family, "UNKNOWN", normalized_regime),
        _normalized_key(normalized_stage, normalized_family, "UNKNOWN", "UNKNOWN"),
    ]
    for key in lookup_keys:
        item = adjustments.get(key) or {}
        if not isinstance(item, Mapping):
            continue
        delta = _safe_float(item.get("recommended_delta"))
        if delta is None:
            continue
        max_delta = abs(float(getattr(cfg, "OFFLINE_THRESHOLD_TUNING_MAX_DELTA", 0.03) or 0.03))
        return round(_clamp(float(delta), -max_delta, max_delta), 6)
    return 0.0
