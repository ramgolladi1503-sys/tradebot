from __future__ import annotations

from typing import Any, Iterable


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def compute_r_multiple(*, entry_price: Any, exit_price: Any, stop_loss: Any, direction: str = "BUY_CALL") -> float | None:
    entry = _safe_float(entry_price)
    exit_val = _safe_float(exit_price)
    stop = _safe_float(stop_loss)
    if entry is None or exit_val is None or stop is None:
        return None
    risk = abs(float(entry) - float(stop))
    if risk <= 0:
        return None
    # Long option model: both BUY_CALL and BUY_PUT profit when selected option price rises.
    return round((float(exit_val) - float(entry)) / risk, 6)


def label_shadow_record(
    record: dict[str, Any],
    *,
    future_price: Any,
    horizon_min: int,
    execution_cost_r: float = 0.0,
) -> dict[str, Any]:
    out = dict(record)
    r = compute_r_multiple(
        entry_price=record.get("entry_price"),
        exit_price=future_price,
        stop_loss=record.get("stop_loss"),
        direction=str(record.get("direction") or ""),
    )
    if r is None:
        out.update({"outcome_status": "UNLABELABLE", "label_reason": "missing_entry_exit_or_stop"})
        return out
    execution_adjusted_r = round(float(r) - float(execution_cost_r or 0.0), 6)
    out.update(
        {
            "outcome_status": "LABELED",
            "horizon_min": int(horizon_min),
            "exit_price": future_price,
            "r_multiple": r,
            "execution_cost_r": round(float(execution_cost_r or 0.0), 6),
            "execution_adjusted_r": execution_adjusted_r,
            "actual_win": execution_adjusted_r > 0,
        }
    )
    return out


def label_records_from_price_map(
    records: Iterable[dict[str, Any]],
    *,
    price_by_key: dict[str, Any],
    horizon_min: int,
    key_field: str = "instrument_id",
    execution_cost_r: float = 0.0,
) -> list[dict[str, Any]]:
    labeled: list[dict[str, Any]] = []
    for record in list(records or []):
        key = str(record.get(key_field) or record.get("symbol") or "")
        if key not in price_by_key:
            row = dict(record)
            row.update({"outcome_status": "UNLABELED", "label_reason": "future_price_missing"})
            labeled.append(row)
            continue
        labeled.append(
            label_shadow_record(
                record,
                future_price=price_by_key[key],
                horizon_min=horizon_min,
                execution_cost_r=execution_cost_r,
            )
        )
    return labeled
