# Migration note:
# Added premium-based simulated P&L helpers for suggested trades (1-lot scenarios).

from __future__ import annotations

from typing import Iterable


DEFAULT_DELTAS = (-20, -10, -5, 5, 10, 20)


def _to_float(value):
    try:
        return float(value)
    except Exception:
        return None


def delta_key(delta: float) -> str:
    try:
        val = int(delta) if float(delta).is_integer() else float(delta)
    except Exception:
        val = delta
    sign = "+" if isinstance(val, (int, float)) and val > 0 else ""
    return f"sim_pnl_{sign}{val}"


def resolve_lot_size(row: dict, meta_map: dict | None = None) -> tuple[int | None, str | None, bool]:
    if row is None:
        return None, None, False
    lot_raw = row.get("lot_size")
    if lot_raw not in (None, ""):
        try:
            lot_val = int(float(lot_raw))
            if lot_val > 0:
                return lot_val, "row", False
        except Exception:
            pass
    token = row.get("instrument_token")
    if meta_map and token is not None:
        meta = meta_map.get(token)
        if isinstance(meta, dict):
            meta_lot = meta.get("lot_size")
            if meta_lot not in (None, ""):
                try:
                    lot_val = int(float(meta_lot))
                    if lot_val > 0:
                        return lot_val, "meta_map", False
                except Exception:
                    pass
    try:
        from config import config as cfg
        sym = row.get("symbol")
        lot_map = getattr(cfg, "LOT_SIZE", {}) or {}
        if sym in lot_map:
            lot_val = int(float(lot_map.get(sym)))
            if lot_val > 0:
                return lot_val, "config", False
    except Exception:
        pass
    sym = str(row.get("symbol") or "").upper()
    fallback_map = {
<<<<<<< HEAD
        "NIFTY": 50,
        "BANKNIFTY": 15,
        "SENSEX": 10,
=======
        "NIFTY": 65,
        "BANKNIFTY": 30,
        "SENSEX": 20,
>>>>>>> origin/main
    }
    if sym in fallback_map:
        return fallback_map[sym], "fallback", True
    return None, None, False


def get_lot_size(row: dict, meta_map: dict | None = None) -> int | None:
    lot, _source, _fallback = resolve_lot_size(row, meta_map=meta_map)
    return lot


def is_contract_resolved(row: dict) -> tuple[bool, str | None]:
    if row is None:
        return False, "unresolved_contract"
    expiry = row.get("expiry_date") or row.get("expiry")
    token = row.get("instrument_token")
    instrument_id = row.get("instrument_id") or row.get("tradingsymbol")
    if not expiry:
        return False, "unresolved_contract"
    if not token and not instrument_id:
        return False, "unresolved_contract"
    return True, None


def simulate_pnl(entry: float, side: str, lot_size: int, deltas: Iterable[float] = DEFAULT_DELTAS) -> dict:
    results = {}
    entry_val = float(entry)
    side_val = str(side or "").upper()
    for delta in deltas:
        new_price = entry_val + float(delta)
        if side_val == "SELL":
            pnl = (entry_val - new_price) * lot_size
        else:
            pnl = (new_price - entry_val) * lot_size
        results[delta_key(delta)] = round(float(pnl), 2)
    return results


def compute_live_pnl(entry_price: float, current_ltp: float, side: str, qty: float) -> float | None:
    try:
        entry_val = float(entry_price)
        ltp_val = float(current_ltp)
        qty_val = float(qty)
    except Exception:
        return None
    side_val = str(side or "").upper()
    if side_val not in ("BUY", "SELL"):
        return None
    if side_val == "SELL":
        return (entry_val - ltp_val) * qty_val
    return (ltp_val - entry_val) * qty_val


def _resolve_current_price(row: dict) -> float | None:
    if row is None:
        return None
    live = _to_float(row.get("live_ltp"))
    if live is not None:
        return live
    opt_ltp = _to_float(row.get("opt_ltp"))
    if opt_ltp is not None:
        return opt_ltp
    bid = _to_float(row.get("opt_bid"))
    ask = _to_float(row.get("opt_ask"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    return None


def compute_row_live_pnl(row: dict, meta_map: dict | None = None) -> dict:
    out = {
        "pnl_1qty": None,
        "pnl_1lot": None,
        "lot_size": None,
        "lot_size_source": None,
        "lot_fallback_used": False,
        "live_ltp": None,
        "pnl_reason": None,
    }
    if not isinstance(row, dict):
        out["pnl_reason"] = "invalid_row"
        return out
    status = str(row.get("status") or "PLANNING").upper()
    if status != "ACTIVE":
        out["pnl_reason"] = "inactive"
        return out
    fill = _to_float(row.get("fill_price"))
    if fill is None:
        fill = _to_float(row.get("activation_price"))
    if fill is None:
        out["pnl_reason"] = "missing_fill_price"
        return out
    ltp = _resolve_current_price(row)
    if ltp is None:
        out["pnl_reason"] = "missing_ltp"
        return out
    out["live_ltp"] = ltp
    side = str(row.get("side") or "").upper()
    pnl_1qty = compute_live_pnl(fill, ltp, side, 1.0)
    if pnl_1qty is None:
        out["pnl_reason"] = "invalid_side"
        return out
    out["pnl_1qty"] = round(float(pnl_1qty), 2)
    lot_size, source, fallback_used = resolve_lot_size(row, meta_map=meta_map)
    out["lot_size"] = lot_size
    out["lot_size_source"] = source
    out["lot_fallback_used"] = fallback_used
    if lot_size:
        pnl_1lot = compute_live_pnl(fill, ltp, side, float(lot_size))
        if pnl_1lot is not None:
            out["pnl_1lot"] = round(float(pnl_1lot), 2)
    return out


def simulate_row(row: dict, meta_map: dict | None = None, deltas: Iterable[float] = DEFAULT_DELTAS) -> dict:
    out = {"sim_reason": None}
    ok, reason = is_contract_resolved(row)
    if not ok:
        out["sim_reason"] = reason
        for d in deltas:
            out[delta_key(d)] = None
        return out
    status = str(row.get("status") or "PLANNING").upper()
    if status != "ACTIVE":
        out["sim_reason"] = "waiting_for_entry" if status == "PLANNING" else f"status_{status.lower()}"
        for d in deltas:
            out[delta_key(d)] = None
        return out
    entry = _to_float(row.get("fill_price"))
    side = str(row.get("side") or "").upper()
    if entry is None:
        out["sim_reason"] = "missing_fill_price"
        for d in deltas:
            out[delta_key(d)] = None
        return out
    if side not in ("BUY", "SELL"):
        out["sim_reason"] = "invalid_side"
        for d in deltas:
            out[delta_key(d)] = None
        return out
    lot_size, source, fallback_used = resolve_lot_size(row, meta_map=meta_map)
    if not lot_size or lot_size <= 0:
        out["sim_reason"] = "missing_lot_size"
        for d in deltas:
            out[delta_key(d)] = None
        return out
    out["lot_size"] = lot_size
    out["lot_size_source"] = source
    out["lot_fallback_used"] = fallback_used
    out.update(simulate_pnl(entry, side, lot_size, deltas=deltas))
    return out
