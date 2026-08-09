"""Fail-closed causal bar utilities for movement strategies.

Every returned bar must have a parseable timestamp, be strictly ordered, and be
strictly earlier than StrategyContext.ts_epoch when decision time is supplied.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.movement_contract import StrategyContext
from strategies.movement._utils import safe_float


def _epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        out = safe_float(value)
        return out
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except Exception:
        return None


def _bar_epoch(bar: dict[str, Any]) -> float | None:
    for key in ("ts_epoch", "timestamp", "datetime", "time", "date"):
        if key in bar:
            parsed = _epoch(bar.get(key))
            if parsed is not None:
                return parsed
    return None


def completed_bars_before(ctx: StrategyContext, *, min_bars: int = 1) -> tuple[dict[str, Any], ...]:
    history = ctx.completed_bar_history
    if not isinstance(history, (list, tuple)) or len(history) < min_bars:
        return ()
    decision = safe_float(ctx.ts_epoch)
    out: list[tuple[float, dict[str, Any]]] = []
    for raw in history:
        if not isinstance(raw, dict):
            return ()
        ts = _bar_epoch(raw)
        if ts is None:
            return ()
        if decision is not None and ts >= decision:
            return ()
        # Require completed OHLC evidence, not marker-only metadata.
        for field in ("open", "high", "low", "close"):
            if safe_float(raw.get(field)) is None:
                return ()
        out.append((ts, raw))
    times = [x[0] for x in out]
    if any(b <= a for a, b in zip(times, times[1:])):
        return ()
    return tuple(x[1] for x in out)


def bar_value(bar: dict[str, Any], key: str) -> float | None:
    return safe_float(bar.get(key))


def compression_window(ctx: StrategyContext, *, lookback: int = 6) -> tuple[float, float, float] | None:
    bars = completed_bars_before(ctx, min_bars=lookback)
    if not bars:
        return None
    window = bars[-lookback:]
    highs = [bar_value(b, "high") for b in window]
    lows = [bar_value(b, "low") for b in window]
    close = bar_value(window[-1], "close")
    if close is None or close <= 0 or any(v is None for v in highs + lows):
        return None
    upper = max(float(v) for v in highs if v is not None)
    lower = min(float(v) for v in lows if v is not None)
    width_pct = (upper - lower) / abs(close)
    return upper, lower, width_pct


def failed_break_reentry(
    ctx: StrategyContext,
    *,
    level: float,
    side: str,
    min_break_distance_pct: float,
) -> dict[str, float] | None:
    bars = completed_bars_before(ctx, min_bars=2)
    if not bars or level <= 0:
        return None
    break_index: int | None = None
    break_extreme: float | None = None
    for i, bar in enumerate(bars[:-1]):
        if side == "UP":
            extreme = bar_value(bar, "high")
            if extreme is not None and (extreme - level) / abs(level) >= min_break_distance_pct:
                break_index, break_extreme = i, extreme
                break
        else:
            extreme = bar_value(bar, "low")
            if extreme is not None and (level - extreme) / abs(level) >= min_break_distance_pct:
                break_index, break_extreme = i, extreme
                break
    if break_index is None or break_extreme is None:
        return None
    for j in range(break_index + 1, len(bars)):
        close = bar_value(bars[j], "close")
        if close is None:
            return None
        if side == "UP" and close < level:
            return {"break_extreme": break_extreme, "reentry_close": close, "break_index": float(break_index), "reentry_index": float(j)}
        if side == "DOWN" and close > level:
            return {"break_extreme": break_extreme, "reentry_close": close, "break_index": float(break_index), "reentry_index": float(j)}
    return None


__all__ = ["completed_bars_before", "compression_window", "failed_break_reentry", "bar_value"]
