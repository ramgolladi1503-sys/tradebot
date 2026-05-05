from __future__ import annotations

from typing import Any, Iterable


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def analyze_conflict(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    call_strength = 0.0
    put_strength = 0.0
    for row in list(rows or []):
        direction = str(row.get("direction") or "").upper()
        strength = _safe_float(row.get("score"), 0.0) * _safe_float(row.get("confidence"), 0.0)
        if direction == "BUY_CALL":
            call_strength += strength
        elif direction == "BUY_PUT":
            put_strength += strength
    stronger = max(call_strength, put_strength)
    weaker = min(call_strength, put_strength)
    conflict_ratio = 0.0 if stronger <= 0 else weaker / stronger
    winner = "BUY_CALL" if call_strength > put_strength else ("BUY_PUT" if put_strength > call_strength else "NONE")
    return {
        "call_strength": round(call_strength, 6),
        "put_strength": round(put_strength, 6),
        "conflict_ratio": round(conflict_ratio, 6),
        "winner_direction": winner,
        "skip_recommended": conflict_ratio > 0.70,
    }


def attach_conflict_outcome(conflict_report: dict[str, Any], *, actual_r: float | None) -> dict[str, Any]:
    out = dict(conflict_report)
    out["actual_r"] = actual_r
    out["good_skip"] = bool(out.get("skip_recommended") and (actual_r is None or float(actual_r) <= 0.25))
    return out
