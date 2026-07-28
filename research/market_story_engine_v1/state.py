from __future__ import annotations

import pandas as pd

from .contracts import MarketState


def classify_state(history: pd.DataFrame, structure: dict[str, float | int | bool], cfg: object) -> MarketState:
    row, prev = history.iloc[-1], history.iloc[-2]
    close = float(row.close)
    resistance, support = float(structure["resistance"]), float(structure["support"])
    tol_up = resistance * cfg.level_tolerance_bps / 10000.0
    tol_down = support * cfg.level_tolerance_bps / 10000.0
    accept_up = resistance * cfg.acceptance_buffer_bps / 10000.0
    accept_down = support * cfg.acceptance_buffer_bps / 10000.0
    prior = history.iloc[:-1]
    prev_res = float(prior.iloc[:-1].tail(cfg.level_lookback).high.max())
    prev_sup = float(prior.iloc[:-1].tail(cfg.level_lookback).low.min())
    prev_up = float(prev.close) > prev_res + prev_res * cfg.acceptance_buffer_bps / 10000.0
    prev_down = float(prev.close) < prev_sup - prev_sup * cfg.acceptance_buffer_bps / 10000.0
    if bool(structure["overextended"]):
        return MarketState.EXHAUSTION_UP if close > float(history.close.iloc[-4]) else MarketState.EXHAUSTION_DOWN
    if prev_up and float(row.low) <= prev_res + tol_up and close >= prev_res:
        return MarketState.RETEST_HOLD_UP
    if prev_down and float(row.high) >= prev_sup - tol_down and close <= prev_sup:
        return MarketState.RETEST_HOLD_DOWN
    if prev_up and close > float(prev.close) + 0.35 * float(structure["atr"]):
        return MarketState.EXPANSION_UP
    if prev_down and close < float(prev.close) - 0.35 * float(structure["atr"]):
        return MarketState.EXPANSION_DOWN
    if close > resistance + accept_up and float(structure["close_location"]) >= 0.65:
        return MarketState.ACCEPTED_ABOVE
    if close < support - accept_down and float(structure["close_location"]) <= 0.35:
        return MarketState.ACCEPTED_BELOW
    if float(row.high) > resistance + tol_up:
        return MarketState.REJECTION_UP if close <= resistance else MarketState.BREAKOUT_ATTEMPT_UP
    if float(row.low) < support - tol_down:
        return MarketState.REJECTION_DOWN if close >= support else MarketState.BREAKOUT_ATTEMPT_DOWN
    if abs(close - resistance) <= tol_up:
        return MarketState.APPROACHING_RESISTANCE
    if abs(close - support) <= tol_down:
        return MarketState.APPROACHING_SUPPORT
    return MarketState.BALANCED_RANGE
