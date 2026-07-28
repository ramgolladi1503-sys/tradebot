from __future__ import annotations

import pandas as pd

from .structure import bps


def participation(history: pd.DataFrame) -> dict[str, float | bool]:
    row = history.iloc[-1]
    cols = ["weighted_breadth", "equal_breadth", "top5_concentration", "sector_agreement"]
    if any(pd.isna(row.get(c)) for c in cols):
        return {"long": 0.0, "short": 0.0, "complete": False}
    wb, eb = float(row.weighted_breadth), float(row.equal_breadth)
    accel = wb - float(history.weighted_breadth.iloc[-3])
    concentration, sector = float(row.top5_concentration), float(row.sector_agreement)
    long = [wb >= 0.58, eb >= 0.55, accel > 0.02, concentration <= 0.58, sector >= 0.55]
    short = [wb <= 0.42, eb <= 0.45, accel < -0.02, concentration <= 0.58, sector >= 0.55]
    return {"long": sum(long) / 5, "short": sum(short) / 5, "complete": True}


def option_confirmation(history: pd.DataFrame, cfg: object) -> dict[str, object]:
    row = history.iloc[-1]
    cols = ["ce_bid", "ce_ask", "ce_last", "ce_volume", "pe_bid", "pe_ask", "pe_last", "pe_volume", "underlying_reference"]
    if any(pd.isna(row.get(c)) for c in cols):
        return {"long": 0.0, "short": 0.0, "complete": False, "reasons": ("OPTION_DATA_MISSING",)}
    ce_bid, ce_ask, pe_bid, pe_ask = map(float, [row.ce_bid, row.ce_ask, row.pe_bid, row.pe_ask])
    if ce_bid <= 0 or pe_bid <= 0 or ce_ask < ce_bid or pe_ask < pe_bid:
        return {"long": 0.0, "short": 0.0, "complete": False, "reasons": ("INVALID_OR_CROSSED_OPTION_MARKET",)}
    if abs(bps(float(row.underlying_reference), float(row.close))) > cfg.level_tolerance_bps:
        return {"long": 0.0, "short": 0.0, "complete": False, "reasons": ("OPTION_UNDERLYING_SYNC_MISMATCH",)}
    prev = history.iloc[-3]
    if any(pd.isna(prev.get(c)) for c in ["ce_last", "pe_last", "close"]):
        return {"long": 0.0, "short": 0.0, "complete": False, "reasons": ("OPTION_HISTORY_MISSING",)}
    underlying_move = bps(float(prev.close), float(row.close))
    ce_move, pe_move = bps(float(prev.ce_last), float(row.ce_last)), bps(float(prev.pe_last), float(row.pe_last))
    ce_spread = (ce_ask - ce_bid) / ((ce_ask + ce_bid) / 2.0)
    pe_spread = (pe_ask - pe_bid) / ((pe_ask + pe_bid) / 2.0)
    long_ok = underlying_move > 0 and ce_move / max(abs(underlying_move), 1.0) >= 1.0 and ce_move > 0
    short_ok = underlying_move < 0 and pe_move / max(abs(underlying_move), 1.0) >= 1.0 and pe_move > 0
    long_checks = [ce_spread <= cfg.max_spread_pct, float(row.ce_volume) > 0, pe_move <= 0]
    short_checks = [pe_spread <= cfg.max_spread_pct, float(row.pe_volume) > 0, ce_move <= 0]
    return {
        "long": sum(long_checks) / 3 if long_ok else 0.0,
        "short": sum(short_checks) / 3 if short_ok else 0.0,
        "complete": True,
        "reasons": (),
    }
