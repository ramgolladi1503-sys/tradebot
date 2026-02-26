# Migration note:
# Adds trailing display shaping for UI tables (preview in PLANNING, live in ACTIVE).

from __future__ import annotations

from typing import Any, Dict

from config import config as cfg


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def apply_trailing_display_row(row: Dict[str, Any]) -> Dict[str, Any]:
    if row is None:
        return {}
    out = dict(row)
    status = str(out.get("status") or "PLANNING").upper()
    out.setdefault("trail_enabled", bool(out.get("trail_enabled", True)))
    out.setdefault("trail_rule", getattr(cfg, "TRAIL_RULE_DEFAULT", "MFE_MINUS_OFFSET"))
    out.setdefault("trail_start", getattr(cfg, "TRAIL_START_DEFAULT", "AFTER_1R"))
    if out.get("original_stop") is None:
        out["original_stop"] = out.get("stop")
    if status != "ACTIVE":
        out["mfe_price"] = None
        out["trail_stop"] = None
        out["current_stop"] = None
        out["profit_locked"] = None
        return out
    current_stop = out.get("stop") if out.get("stop") is not None else out.get("current_stop")
    out["current_stop"] = current_stop
    entry = _to_float(out.get("entry") or out.get("entry_price"))
    stop_val = _to_float(current_stop)
    side = str(out.get("side") or "").upper()
    profit_locked = None
    if entry is not None and stop_val is not None:
        if side == "BUY":
            profit_locked = stop_val > entry
        elif side == "SELL":
            profit_locked = stop_val < entry
    out["profit_locked"] = profit_locked
    return out


def apply_trailing_display_df(df):
    if df is None or df.empty:
        return df
    for col in (
        "trail_enabled",
        "trail_rule",
        "trail_offset",
        "trail_start",
        "original_stop",
        "current_stop",
        "mfe_price",
        "trail_stop",
        "profit_locked",
    ):
        if col not in df.columns:
            df[col] = None
    for idx, row in df.iterrows():
        updated = apply_trailing_display_row(row.to_dict())
        for key, value in updated.items():
            if key in df.columns:
                df.at[idx, key] = value
    return df

