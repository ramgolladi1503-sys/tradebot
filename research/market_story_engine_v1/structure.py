from __future__ import annotations

import numpy as np
import pandas as pd


def bps(reference: float, value: float) -> float:
    return 0.0 if reference <= 0 else (value / reference - 1.0) * 10000.0


def clip01(value: float) -> float:
    return float(min(1.0, max(0.0, value)))


def build_structure(history: pd.DataFrame, cfg: object) -> dict[str, float | int | bool]:
    prior, row = history.iloc[:-1], history.iloc[-1]
    recent = prior.tail(cfg.level_lookback)
    resistance, support = float(recent.high.max()), float(recent.low.min())
    close = float(row.close)
    tr = np.maximum(
        history.high - history.low,
        np.maximum((history.high - history.close.shift(1)).abs(), (history.low - history.close.shift(1)).abs()),
    ).fillna(history.high - history.low)
    atr = float(tr.tail(cfg.compression_slow).median())
    fast = float(tr.tail(cfg.compression_fast).median())
    slow = float(tr.iloc[:-cfg.compression_fast].tail(cfg.compression_slow).median())
    compressed = fast / max(slow, 1e-9) <= 0.82
    tol_res = resistance * cfg.level_tolerance_bps / 10000.0
    tol_sup = support * cfg.level_tolerance_bps / 10000.0
    touches_res = int(((prior.tail(cfg.touch_lookback).high - resistance).abs() <= tol_res).sum())
    touches_sup = int(((prior.tail(cfg.touch_lookback).low - support).abs() <= tol_sup).sum())
    higher, lower = prior[prior.high > close], prior[prior.low < close]
    next_res = float(higher.high.min()) if not higher.empty else resistance + max(atr * 1.5, close * cfg.min_room_bps / 10000.0)
    next_sup = float(lower.low.max()) if not lower.empty else support - max(atr * 1.5, close * cfg.min_room_bps / 10000.0)
    span = max(float(row.high - row.low), 1e-9)
    body_ratio = abs(float(row.close - row.open)) / span
    close_location = float((row.close - row.low) / span)
    move = abs(float(history.close.iloc[-1] - history.close.iloc[-4]))
    overextended = move / max(atr, 1e-9) > cfg.max_overextension_atr
    return {
        "resistance": resistance,
        "support": support,
        "atr": atr,
        "room_up_bps": max(0.0, bps(close, next_res)),
        "room_down_bps": max(0.0, -bps(close, next_sup)),
        "close_location": close_location,
        "overextended": overextended,
        "long_score": clip01(0.25 * (touches_res >= 2) + 0.25 * compressed + 0.25 * (close_location >= 0.70) + 0.25 * (body_ratio >= 0.55)),
        "short_score": clip01(0.25 * (touches_sup >= 2) + 0.25 * compressed + 0.25 * (close_location <= 0.30) + 0.25 * (body_ratio >= 0.55)),
    }
