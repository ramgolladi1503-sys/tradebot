from __future__ import annotations

import hashlib
import importlib
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeClassifier, MovementRegimeResult


CANONICAL_STRATEGIES: dict[str, tuple[str, str]] = {
    "OPENING_DRIVE": ("strategies.movement.opening_drive", "generate_opening_drive_candidates"),
    "OPENING_RANGE_RETEST": ("strategies.movement.opening_range_breakout", "generate_opening_range_retest_candidates"),
    "COMPRESSION_BREAKOUT": ("strategies.movement.compression_breakout", "generate_compression_breakout_candidates"),
    "TREND_PULLBACK": ("strategies.movement.trend_pullback", "generate_trend_pullback_candidates"),
    "VWAP_RECLAIM": ("strategies.movement.vwap_reclaim", "generate_vwap_reclaim_rejection_candidates"),
    "FAILED_BREAKOUT_TRAP": ("strategies.movement.failed_breakout_trap", "generate_failed_breakout_trap_candidates"),
    "EXHAUSTION_REVERSAL": ("strategies.movement.exhaustion_reversal", "generate_exhaustion_reversal_candidates"),
    "MEAN_REVERSION_EXTENSION": ("strategies.movement.mean_reversion_extension", "generate_mean_reversion_extension_candidates"),
    "EVENT_VOLATILITY_EXPANSION": ("strategies.movement.event_volatility_expansion", "generate_event_volatility_expansion_candidates"),
    "OPTION_PRESSURE": ("strategies.movement.option_pressure", "generate_option_pressure_candidates"),
    "LATE_DAY_MOMENTUM": ("strategies.movement.late_day_momentum", "generate_late_day_momentum_candidates"),
    "NO_TRADE_ENGINE": ("strategies.movement.no_trade_chop", "generate_no_trade_candidates"),
}


@dataclass(frozen=True)
class InvocationRecord:
    strategy_key: str
    module: str
    callable_name: str
    callable_identity: str
    callable_source_hash: str
    invocation_count: int
    candidate_count: int
    exception_count: int
    exact_reason: str | None = None


def _source_hash(fn: Callable[..., Any]) -> str:
    try:
        source = inspect.getsource(fn).encode("utf-8")
    except (OSError, TypeError):
        source = repr(fn).encode("utf-8")
    return hashlib.sha256(source).hexdigest()


def resolve_callable(strategy_key: str) -> tuple[Callable[..., Any], str, str]:
    try:
        module_name, callable_name = CANONICAL_STRATEGIES[strategy_key]
    except KeyError as exc:
        raise KeyError(f"unknown_canonical_strategy:{strategy_key}") from exc
    module = importlib.import_module(module_name)
    fn = getattr(module, callable_name)
    if not callable(fn):
        raise TypeError(f"canonical_owner_not_callable:{module_name}.{callable_name}")
    return fn, module_name, callable_name


def build_completed_history(
    rows: list[Mapping[str, Any]], *, symbol: str, session_date: str, timeframe: str
) -> tuple[dict[str, Any], ...]:
    history: list[dict[str, Any]] = []
    for row in rows:
        start = row["timestamp"]
        end = row.get("bar_end_timestamp")
        if end is None:
            end = start + row["bar_duration"]
        history.append(
            {
                "symbol": symbol,
                "session_date": session_date,
                "timeframe": timeframe,
                "bar_start_timestamp": str(start),
                "bar_end_timestamp": str(end),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume") or 0.0),
                "is_complete": True,
            }
        )
    return tuple(history)


def build_context(
    *,
    symbol: str,
    current: Mapping[str, Any],
    completed_history: tuple[dict[str, Any], ...],
    minutes_since_open: int,
    minutes_to_close: int,
) -> StrategyContext:
    closes = [float(row["close"]) for row in completed_history]
    highs = [float(row["high"]) for row in completed_history]
    lows = [float(row["low"]) for row in completed_history]
    volumes = [float(row.get("volume") or 0.0) for row in completed_history]
    typical = [(h + l + c) / 3.0 for h, l, c in zip(highs, lows, closes)]
    cumulative_volume = sum(volumes)
    vwap = (
        sum(price * volume for price, volume in zip(typical, volumes)) / cumulative_volume
        if cumulative_volume > 0
        else sum(typical) / len(typical)
    )
    previous_vwap = vwap
    if len(typical) > 1:
        prior_volume = sum(volumes[:-1])
        previous_vwap = (
            sum(price * volume for price, volume in zip(typical[:-1], volumes[:-1])) / prior_volume
            if prior_volume > 0
            else sum(typical[:-1]) / len(typical[:-1])
        )
    ranges = [high - low for high, low in zip(highs, lows)]
    atr = sum(ranges[-14:]) / min(len(ranges), 14)
    atr_short = sum(ranges[-5:]) / min(len(ranges), 5)
    atr_long = sum(ranges[-30:]) / min(len(ranges), 30)
    orb_slice = completed_history[: min(3, len(completed_history))]
    return StrategyContext(
        symbol=symbol,
        ts_epoch=float(current["timestamp"].timestamp()),
        spot_ltp=float(current["close"]),
        open_price=float(completed_history[0]["open"]),
        vwap=vwap,
        vwap_slope=vwap - previous_vwap,
        day_high=max(highs),
        day_low=min(lows),
        orb_high=max(float(row["high"]) for row in orb_slice),
        orb_low=min(float(row["low"]) for row in orb_slice),
        previous_completed_close=closes[-2] if len(closes) > 1 else None,
        nearest_support=min(lows[-5:]),
        nearest_resistance=max(highs[-5:]),
        completed_bar_history=completed_history,
        atr=atr,
        atr_short=atr_short,
        atr_long=atr_long,
        range_width_pct=(max(highs) - min(lows)) / max(closes[-1], 1e-9),
        volume_z=0.0,
        quote_source="kite_historical_underlying_5m",
        fallback_used=False,
        time_of_day=current["timestamp"].strftime("%H:%M"),
        minutes_since_open=minutes_since_open,
        minutes_to_close=minutes_to_close,
        expiry_context=False,
        metadata={
            "replay_authority": "UNDERLYING_5M_OHLCV",
            "option_contract_truth_available": False,
            "causal_completed_bar_count": len(completed_history),
        },
    )


def invoke_canonical(
    strategy_key: str, ctx: StrategyContext, regime: MovementRegimeResult | None = None
) -> tuple[tuple[StrategyCandidate, ...], InvocationRecord]:
    fn, module_name, callable_name = resolve_callable(strategy_key)
    identity = f"{fn.__module__}.{fn.__qualname__}"
    source_hash = _source_hash(fn)
    if regime is None:
        regime = MovementRegimeClassifier().classify(ctx)
    try:
        result = fn(ctx, regime)
        candidates = tuple(result or ())
        if not all(isinstance(candidate, StrategyCandidate) for candidate in candidates):
            raise TypeError(f"canonical_candidate_type_violation:{identity}")
        record = InvocationRecord(
            strategy_key=strategy_key,
            module=module_name,
            callable_name=callable_name,
            callable_identity=identity,
            callable_source_hash=source_hash,
            invocation_count=1,
            candidate_count=len(candidates),
            exception_count=0,
        )
        return candidates, record
    except Exception as exc:
        record = InvocationRecord(
            strategy_key=strategy_key,
            module=module_name,
            callable_name=callable_name,
            callable_identity=identity,
            callable_source_hash=source_hash,
            invocation_count=1,
            candidate_count=0,
            exception_count=1,
            exact_reason=f"{type(exc).__name__}:{exc}",
        )
        return (), record


def assert_no_proxy_strategy_logic(source: str) -> None:
    forbidden = (
        "if strategy in",
        "elif strategy ==",
        "1.5 * sd",
        "closes[i] > ma",
        "max(highs[:3])",
    )
    hits = [token for token in forbidden if token in source]
    if hits:
        raise AssertionError(f"proxy_strategy_logic_detected:{','.join(hits)}")
