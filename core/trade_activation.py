# Migration note:
# Added deterministic activation rules for suggested trades (PLANNING -> ACTIVE).

from __future__ import annotations

from datetime import datetime, timezone

try:
    from config import config as cfg
except Exception:
    cfg = None


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
    sell_rule = "LE"
    try:
        raw = str(getattr(cfg, "ACTIVATE_SELL_RULE", "LE") or "LE").strip().upper()
        if raw in ("GE", "ABOVE", ">=", "BREAKOUT_UP"):
            sell_rule = "GE"
        elif raw in ("LE", "BELOW", "<=", "BREAKOUT_DOWN"):
            sell_rule = "LE"
    except Exception:
        sell_rule = "LE"
    if cond in ("BREAKOUT", "ABOVE", "CROSS_ABOVE"):
        if side_val == "BUY":
            return ltp_val >= entry_val
        if side_val == "SELL":
            return ltp_val >= entry_val if sell_rule == "GE" else ltp_val <= entry_val
        return False
    # Unknown conditions default to breakout semantics for deterministic behavior.
    if side_val == "BUY":
        return ltp_val >= entry_val
    if side_val == "SELL":
        return ltp_val >= entry_val if sell_rule == "GE" else ltp_val <= entry_val
    return False


def activate_trade(row: dict, ltp, ts=None) -> dict:
    if row is None:
        return {}
    updated = dict(row)
    if ts is None:
        ts = datetime.now(timezone.utc).isoformat()
    updated["status"] = "ACTIVE"
    updated["activated_ts"] = ts
    activation_price = _to_float(ltp)
    updated["activation_price"] = activation_price
    updated["ltp_at_activation"] = activation_price
    if activation_price is not None:
        updated["fill_price"] = activation_price
    else:
        updated["fill_price"] = _to_float(updated.get("entry"))
    return updated
