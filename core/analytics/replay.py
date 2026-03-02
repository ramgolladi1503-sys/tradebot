from __future__ import annotations

from typing import Any, Iterable, Mapping


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


def _normalize_side(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"SELL", "SHORT"}:
        return "SELL"
    return "BUY"


def _coerce_ts(value: Any) -> float | None:
    ts = _safe_float(value)
    if ts is None:
        return None
    if ts > 1e12:
        return ts / 1000.0
    return ts


def _tick_price(row: Mapping[str, Any]) -> float | None:
    bid = _safe_float(row.get("bid"))
    ask = _safe_float(row.get("ask"))
    mark = _safe_float(row.get("mark"))
    if mark is None:
        mark = _safe_float(row.get("mark_price"))
    ltp = _safe_float(row.get("ltp"))
    if bid is not None and ask is not None:
        mid = (bid + ask) / 2.0
    else:
        mid = None
    for candidate in (mark, mid, ltp, bid, ask, _safe_float(row.get("price"))):
        if candidate is not None:
            return float(candidate)
    return None


def classify_outcome_for_rejected_trade(
    reject_event: Mapping[str, Any],
    future_ticks: Iterable[Mapping[str, Any]],
    target_pct: float = 0.02,
    sl_pct: float = 0.01,
) -> dict[str, Any]:
    side = _normalize_side(
        reject_event.get("side")
        or reject_event.get("trade_side")
        or reject_event.get("direction")
    )
    entry = _safe_float(
        reject_event.get("intended_entry")
        or reject_event.get("entry")
        or reject_event.get("entry_price")
        or reject_event.get("mark")
        or reject_event.get("ltp")
    )
    if entry is None:
        return {"outcome": "NO_HIT", "mfe": None, "mae": None, "resolution_ts": None}

    target = _safe_float(reject_event.get("target") or reject_event.get("target_price"))
    stop = _safe_float(
        reject_event.get("stop")
        or reject_event.get("stop_price")
        or reject_event.get("stop_loss")
    )
    if target is None:
        target = entry * (1.0 + float(target_pct)) if side == "BUY" else entry * (1.0 - float(target_pct))
    if stop is None:
        stop = entry * (1.0 - float(sl_pct)) if side == "BUY" else entry * (1.0 + float(sl_pct))

    rows = sorted(
        [dict(row) for row in list(future_ticks or []) if isinstance(row, Mapping)],
        key=lambda row: float(_coerce_ts(row.get("ts_utc") or row.get("ts") or row.get("ts_epoch") or row.get("ts_epoch_ms")) or 0.0),
    )
    if not rows:
        return {"outcome": "NO_HIT", "mfe": 0.0, "mae": 0.0, "resolution_ts": None}

    outcome = "NO_HIT"
    resolution_ts = None
    mfe = None
    mae = None

    for row in rows:
        price = _tick_price(row)
        ts = _coerce_ts(
            row.get("ts_utc")
            or row.get("ts")
            or row.get("ts_epoch")
            or row.get("ts_epoch_ms")
        )
        if price is None:
            continue

        if side == "BUY":
            favorable = float(price - entry)
            adverse = float(entry - price)
            hit_target = price >= float(target)
            hit_sl = price <= float(stop)
        else:
            favorable = float(entry - price)
            adverse = float(price - entry)
            hit_target = price <= float(target)
            hit_sl = price >= float(stop)

        mfe = favorable if mfe is None else max(float(mfe), favorable)
        mae = adverse if mae is None else max(float(mae), adverse)

        if hit_target:
            outcome = "HIT"
            resolution_ts = ts
            break
        if hit_sl:
            outcome = "SL"
            resolution_ts = ts
            break

    if mfe is None:
        mfe = 0.0
    if mae is None:
        mae = 0.0

    return {
        "outcome": outcome,
        "mfe": float(mfe),
        "mae": float(mae),
        "resolution_ts": resolution_ts,
    }
