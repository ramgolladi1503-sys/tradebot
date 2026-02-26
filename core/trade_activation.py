# Migration note:
# Added deterministic activation rules for suggested trades (PLANNING -> ACTIVE).

from __future__ import annotations

from datetime import datetime, timezone


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def should_activate(side, entry_condition, entry, ltp) -> bool:
    cond = str(entry_condition or "BREAKOUT").strip().upper()
    side_val = str(side or "").strip().upper()
    entry_val = _to_float(entry)
    ltp_val = _to_float(ltp)
    if entry_val is None or ltp_val is None:
        return False
    if cond in ("BREAKOUT", "ABOVE", "CROSS_ABOVE"):
        if side_val == "BUY":
            return ltp_val >= entry_val
        if side_val == "SELL":
            return ltp_val <= entry_val
        return False
    # Unknown conditions default to breakout semantics for deterministic behavior.
    if side_val == "BUY":
        return ltp_val >= entry_val
    if side_val == "SELL":
        return ltp_val <= entry_val
    return False


def activate_trade(row: dict, ltp, ts=None) -> dict:
    if row is None:
        return {}
    updated = dict(row)
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    updated["status"] = "ACTIVE"
    updated["activated_ts"] = ts
    updated["ltp_at_activation"] = _to_float(ltp)
    entry_val = _to_float(updated.get("entry"))
    if entry_val is not None:
        updated["fill_price"] = entry_val
    else:
        updated["fill_price"] = _to_float(ltp)
    return updated
