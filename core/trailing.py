# Migration note:
# Added trailing stop helpers for ACTIVE trades (paper/live-safe, no alpha changes).

from __future__ import annotations

from datetime import datetime, timezone


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def init_trailing(trade: dict) -> dict:
    if trade is None:
        return {}
    updated = dict(trade)
    fill = _to_float(updated.get("fill_price"))
    if fill is None:
        return updated
    if updated.get("original_stop") is None and updated.get("stop") is not None:
        updated["original_stop"] = _to_float(updated.get("stop"))
    if updated.get("mfe_price") is None:
        updated["mfe_price"] = fill
    if updated.get("trail_stop") is None:
        updated["trail_stop"] = None
    if updated.get("trail_enabled") is None:
        updated["trail_enabled"] = True
    if updated.get("last_update_ts") is None:
        updated["last_update_ts"] = datetime.now(timezone.utc).isoformat()
    return updated


def update_trailing(trade: dict, ltp) -> dict:
    updated = init_trailing(trade)
    side = str(updated.get("side") or "").upper()
    ltp_val = _to_float(ltp)
    if ltp_val is None:
        return updated
    if not updated.get("trail_enabled"):
        return updated
    trail_offset = _to_float(updated.get("trail_offset"))
    if trail_offset is None or trail_offset <= 0:
        return updated
    original_stop = _to_float(updated.get("original_stop"))
    mfe = _to_float(updated.get("mfe_price")) or ltp_val

    if side == "BUY":
        mfe = max(mfe, ltp_val)
        trail_stop = mfe - trail_offset
        new_stop = trail_stop if original_stop is None else max(original_stop, trail_stop)
    elif side == "SELL":
        mfe = min(mfe, ltp_val)
        trail_stop = mfe + trail_offset
        new_stop = trail_stop if original_stop is None else min(original_stop, trail_stop)
    else:
        return updated

    updated["mfe_price"] = round(mfe, 4)
    updated["trail_stop"] = round(trail_stop, 4)
    updated["stop"] = round(new_stop, 4)
    updated["last_update_ts"] = datetime.now(timezone.utc).isoformat()
    return updated


def check_exit(trade: dict, ltp) -> tuple[bool, str | None]:
    side = str(trade.get("side") or "").upper()
    ltp_val = _to_float(ltp)
    stop_val = _to_float(trade.get("stop"))
    if ltp_val is None or stop_val is None:
        return False, None
    if side == "BUY" and ltp_val <= stop_val:
        return True, "TRAIL_STOP"
    if side == "SELL" and ltp_val >= stop_val:
        return True, "TRAIL_STOP"
    return False, None
