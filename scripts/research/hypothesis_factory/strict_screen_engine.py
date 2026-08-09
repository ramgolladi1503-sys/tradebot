#!/usr/bin/env python3
"""Strict research-only hypothesis screening semantics.

This engine deliberately tightens the cheap screen before robustness:
- one active position at a time per session (no overlapping trades);
- only exit rules with implemented semantics are evaluated;
- unsupported exit rules fail closed;
- session concentration and drawdown diagnostics are emitted;
- BUY_CE / BUY_PE remain underlying-direction proxy labels only, not option-PnL claims.

It never certifies edge, never grants runtime authority, and never enables broker actions.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any

import hypothesis_factory as hf

SUPPORTED_EXIT_RULES = {"time_stop"}


def _trade_pnl_bps(h: dict[str, Any], session: list[dict[str, Any]], idx: int, cfg: hf.ScreenConfig) -> tuple[float | None, int]:
    """Return proxy underlying-direction PnL in bps and deterministic exit index."""
    if h.get("exit_rule") not in SUPPORTED_EXIT_RULES:
        return None, idx
    entry = hf.f(session[idx], "close")
    exit_idx = min(len(session) - 1, idx + cfg.max_hold_bars)
    if entry <= 0 or exit_idx <= idx:
        return None, exit_idx
    if any(hf.is_fallback(row) for row in session[idx : exit_idx + 1]):
        return None, exit_idx
    sign = 1 if h["direction"] == "BUY_CE" else -1
    gross = sign * ((hf.f(session[exit_idx], "close") - entry) / entry) * 10_000
    return gross - cfg.cost_bps, exit_idx


def _max_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def evaluate_hypothesis_strict(h: dict[str, Any], rows: list[dict[str, Any]], cfg: hf.ScreenConfig) -> dict[str, Any]:
    base = {
        "hypothesis_id": h["hypothesis_id"],
        "family": h["family"],
        "instrument": h["instrument"],
        "direction": h["direction"],
        "window_minutes": h["window_minutes"],
        "filters": h.get("filters", []),
        "exit_rule": h.get("exit_rule", ""),
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
        "fallback_execution_data_used": False,
        "pnl_semantics": "UNDERLYING_DIRECTION_PROXY_BPS",
        "option_pnl_claimed": False,
        "overlapping_trades_allowed": False,
    }
    if h.get("exit_rule") not in SUPPORTED_EXIT_RULES:
        return {
            **base,
            "status": "REJECTED",
            "screen_rejection_reason": "UNSUPPORTED_EXIT_RULE",
            "trades": 0,
            "sessions_traded": 0,
            "win_rate": 0.0,
            "net_expectancy_bps": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_bps": 0.0,
            "max_drawdown_per_100_trades_bps": 0.0,
            "top_session_trade_share": 0.0,
            "top_session_abs_pnl_share": 0.0,
            "max_trades_in_one_session": 0,
            "score": 0.0,
        }

    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("instrument", h["instrument"])).upper() == h["instrument"].upper():
            sessions[hf.session_key(row)].append(row)

    pnls: list[float] = []
    pnl_by_session: dict[str, list[float]] = defaultdict(list)
    previous_close: float | None = None
    for session_id, session in sorted(sessions.items()):
        session.sort(key=hf.ts)
        window_bars = max(1, min(len(session) - 1, h["window_minutes"] // 5))
        if len(session) <= window_bars + 1:
            previous_close = hf.f(session[-1], "close", previous_close or 0) if session else previous_close
            continue
        opening = session[:window_bars]
        opening_high = max(hf.f(row, "high") for row in opening)
        opening_low = min(hf.f(row, "low") for row in opening)
        idx = window_bars
        while idx < len(session) - 1:
            if hf.passes_filters(h, session, idx, cfg) and hf.entry_signal(h, session, idx, opening_high, opening_low, previous_close):
                pnl, exit_idx = _trade_pnl_bps(h, session, idx, cfg)
                if pnl is not None:
                    pnls.append(pnl)
                    pnl_by_session[session_id].append(pnl)
                    idx = max(idx + 1, exit_idx + 1)
                    continue
            idx += 1
        previous_close = hf.f(session[-1], "close", previous_close or 0)

    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    trades = len(pnls)
    expectancy = statistics.mean(pnls) if pnls else 0.0
    win_rate = len(wins) / trades if trades else 0.0
    profit_factor = sum(wins) / abs(sum(losses)) if losses and sum(losses) < 0 else (float("inf") if wins else 0.0)
    drawdown = _max_drawdown(pnls)
    sessions_traded = len(pnl_by_session)
    max_trades_session = max((len(v) for v in pnl_by_session.values()), default=0)
    top_session_trade_share = (max_trades_session / trades) if trades else 0.0
    session_abs = [abs(sum(v)) for v in pnl_by_session.values()]
    total_abs_session_pnl = sum(session_abs)
    top_session_abs_pnl_share = (max(session_abs) / total_abs_session_pnl) if total_abs_session_pnl > 0 else 0.0
    dd_per_100 = abs(drawdown) / max(1, trades) * 100.0
    score = hf.score_result(trades, expectancy, win_rate, drawdown, cfg)
    status = "PROMISING_NOT_CERTIFIED" if trades >= cfg.min_trades and expectancy > cfg.min_net_expectancy_bps else "REJECTED"
    reason = "" if status == "PROMISING_NOT_CERTIFIED" else ("TRADES_BELOW_THRESHOLD" if trades < cfg.min_trades else "EXPECTANCY_NOT_POSITIVE")

    return {
        **base,
        "status": status,
        "screen_rejection_reason": reason,
        "trades": trades,
        "sessions_traded": sessions_traded,
        "win_rate": round(win_rate, 4),
        "net_expectancy_bps": round(expectancy, 4),
        "profit_factor": "INF" if math.isinf(profit_factor) else round(profit_factor, 4),
        "max_drawdown_bps": round(drawdown, 4),
        "max_drawdown_per_100_trades_bps": round(dd_per_100, 4),
        "top_session_trade_share": round(top_session_trade_share, 6),
        "top_session_abs_pnl_share": round(top_session_abs_pnl_share, 6),
        "max_trades_in_one_session": max_trades_session,
        "score": round(score, 6),
    }


def screen_hypotheses_strict(hypotheses: list[dict[str, Any]], rows: list[dict[str, Any]], cfg: hf.ScreenConfig) -> list[dict[str, Any]]:
    results = [evaluate_hypothesis_strict(h, rows, cfg) for h in hypotheses]
    return sorted(results, key=lambda r: (r.get("score", 0.0), r.get("trades", 0)), reverse=True)
