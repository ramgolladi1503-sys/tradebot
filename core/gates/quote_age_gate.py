from __future__ import annotations

from typing import Any


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def validate_quote_age(snapshot, thresholds: dict[str, float] | None = None) -> dict[str, Any]:
    """
    Validate quote ages from a DecisionSnapshot.

    Returns:
        {
            "pass": bool,
            "reason_code": "STALE_OPTION_LTP" | "STALE_INDEX" | None,
            "index_age_ms": float|None,
            "option_age_ms": float|None,
            "index_max_age_ms": float,
            "option_max_age_ms": float,
        }
    """

    th = dict(thresholds or {})
    index_max_age_ms = _safe_float(th.get("index_max_age_ms"))
    option_max_age_ms = _safe_float(th.get("option_max_age_ms"))
    if index_max_age_ms is None:
        index_max_age_ms = 1500.0
    if option_max_age_ms is None:
        option_max_age_ms = 1500.0

    index_age_ms = _safe_float(getattr(getattr(snapshot, "index_quote", None), "age_ms", None))
    option_age_ms = _safe_float(getattr(getattr(snapshot, "option_quote", None), "age_ms", None))

    # Fail-closed on missing ages when snapshot gate is enabled.
    if index_age_ms is None or index_age_ms > index_max_age_ms:
        return {
            "pass": False,
            "reason_code": "STALE_INDEX",
            "index_age_ms": index_age_ms,
            "option_age_ms": option_age_ms,
            "index_max_age_ms": index_max_age_ms,
            "option_max_age_ms": option_max_age_ms,
        }

    if option_age_ms is None or option_age_ms > option_max_age_ms:
        return {
            "pass": False,
            "reason_code": "STALE_OPTION_LTP",
            "index_age_ms": index_age_ms,
            "option_age_ms": option_age_ms,
            "index_max_age_ms": index_max_age_ms,
            "option_max_age_ms": option_max_age_ms,
        }

    return {
        "pass": True,
        "reason_code": None,
        "index_age_ms": index_age_ms,
        "option_age_ms": option_age_ms,
        "index_max_age_ms": index_max_age_ms,
        "option_max_age_ms": option_max_age_ms,
    }

