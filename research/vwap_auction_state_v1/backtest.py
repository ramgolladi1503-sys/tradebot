from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from research.vwap_auction_state_v1.model import (
    Bar,
    DEFAULT_CONFIG,
    EntryFill,
    FormulaConfig,
    OptionQuote,
    SignalIntent,
    TradeOutcome,
    generate_signals,
    next_bar_long_entry,
    select_option_contract,
)


@dataclass(frozen=True)
class RejectedSignal:
    signal_ts: datetime
    setup_type: str
    direction: str
    reason: str


@dataclass(frozen=True)
class SessionEvaluation:
    trades: tuple[TradeOutcome, ...]
    rejections: tuple[RejectedSignal, ...]


@dataclass(frozen=True)
class Summary:
    trade_count: int
    win_rate: float
    avg_option_points: float
    median_option_points: float
    total_option_points: float
    profit_factor: float | None
    max_drawdown_points: float


def _forced_exit_deadline(signal: SignalIntent, entry: EntryFill, cfg: FormulaConfig) -> datetime:
    by_hold = entry.ts + timedelta(minutes=cfg.max_hold_minutes)
    by_clock = datetime.combine(entry.ts.date(), cfg.forced_exit_time, tzinfo=entry.ts.tzinfo)
    return min(by_hold, by_clock)


def _structural_exit(
    signal: SignalIntent,
    entry: EntryFill,
    bars: Sequence[Bar],
    cfg: FormulaConfig,
) -> tuple[datetime, str] | None:
    deadline = _forced_exit_deadline(signal, entry, cfg)
    candidates = [bar for bar in bars if bar.ts > entry.ts and bar.ts <= deadline]
    for bar in candidates:
        if signal.direction == "BUY_CALL":
            stop_hit = bar.low <= signal.structural_stop
            target_hit = bar.high >= signal.structural_target
        else:
            stop_hit = bar.high >= signal.structural_stop
            target_hit = bar.low <= signal.structural_target
        # One-minute ambiguity is resolved adversely. Tick-level truth may replace
        # this convention in a later separately frozen evaluator.
        if stop_hit:
            return bar.ts, "STRUCTURAL_STOP"
        if target_hit:
            return bar.ts, "STRUCTURAL_TARGET"
    if candidates:
        return candidates[-1].ts, "TIME_OR_SESSION_STOP"
    return None


def _exit_bid(
    selected: OptionQuote,
    exit_ts: datetime,
    quotes: Sequence[OptionQuote],
    cfg: FormulaConfig,
) -> OptionQuote | None:
    candidates = [q for q in quotes if q.symbol == selected.symbol and q.ts >= exit_ts]
    candidates.sort(key=lambda q: q.ts)
    for q in candidates:
        q.validate()
        delay = (q.ts - exit_ts).total_seconds()
        if delay > cfg.option_max_quote_staleness_seconds:
            return None
        if q.spread_pct > cfg.option_max_spread_pct:
            continue
        return q
    return None


def evaluate_session(
    bars: Sequence[Bar],
    quotes: Sequence[OptionQuote],
    cfg: FormulaConfig = DEFAULT_CONFIG,
) -> SessionEvaluation:
    cfg.validate()
    signals = generate_signals(bars, cfg)
    trades: list[TradeOutcome] = []
    rejects: list[RejectedSignal] = []
    last_exit: datetime | None = None
    for signal in signals:
        if last_exit is not None and signal.ts <= last_exit:
            rejects.append(RejectedSignal(signal.ts, signal.setup_type.value, signal.direction, "OVERLAPPING_POSITION"))
            continue
        selected = select_option_contract(signal, quotes, signal.entry_reference, cfg)
        if selected is None:
            rejects.append(RejectedSignal(signal.ts, signal.setup_type.value, signal.direction, "NO_EXECUTABLE_CONTRACT"))
            continue
        entry = next_bar_long_entry(signal, selected, quotes, cfg)
        if entry is None:
            rejects.append(RejectedSignal(signal.ts, signal.setup_type.value, signal.direction, "NO_NEXT_ASK_FILL"))
            continue
        structural = _structural_exit(signal, entry, bars, cfg)
        if structural is None:
            rejects.append(RejectedSignal(signal.ts, signal.setup_type.value, signal.direction, "NO_CAUSAL_EXIT_BAR"))
            continue
        exit_ts, exit_reason = structural
        exit_quote = _exit_bid(selected, exit_ts, quotes, cfg)
        if exit_quote is None:
            rejects.append(RejectedSignal(signal.ts, signal.setup_type.value, signal.direction, "NO_EXIT_BID"))
            continue
        points = exit_quote.bid - entry.price
        trades.append(
            TradeOutcome(
                symbol=selected.symbol,
                direction=signal.direction,
                setup_type=signal.setup_type,
                signal_ts=signal.ts,
                entry_ts=entry.ts,
                exit_ts=exit_quote.ts,
                entry_price=entry.price,
                exit_price=exit_quote.bid,
                option_points=points,
                option_return_pct=points / entry.price if entry.price > 0 else 0.0,
                exit_reason=exit_reason,
            )
        )
        last_exit = exit_quote.ts
    return SessionEvaluation(tuple(trades), tuple(rejects))


def summarize(trades: Sequence[TradeOutcome]) -> Summary:
    if not trades:
        return Summary(0, 0.0, 0.0, 0.0, 0.0, None, 0.0)
    pnl = [float(t.option_points) for t in trades]
    wins = [x for x in pnl if x > 0]
    losses = [x for x in pnl if x < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else (math.inf if gross_profit > 0 else None)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in pnl:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return Summary(
        trade_count=len(pnl),
        win_rate=len(wins) / len(pnl),
        avg_option_points=sum(pnl) / len(pnl),
        median_option_points=statistics.median(pnl),
        total_option_points=sum(pnl),
        profit_factor=pf,
        max_drawdown_points=max_dd,
    )
