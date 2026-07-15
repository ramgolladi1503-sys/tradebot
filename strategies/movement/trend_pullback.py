"""Trend Pullback movement strategy.

Joins an established trend after a controlled pullback holds VWAP/structure. This
module emits read-only StrategyCandidate objects only. It does not call brokers,
submit orders, alter execution gates, touch depth subscriptions, or tune live
trading.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_parameter_profiles import (
    RuntimeProfileResolution,
    resolve_required_profile_parameters,
)
from strategies.movement._utils import (
    block_on_required_fields,
    clamp_score,
    emit_strategy_evidence_blocked,
    make_candidate,
    pct_distance,
    ratio_score,
    safe_float,
    side_evidence,
)

STRATEGY_ID = "trend_pullback_v1"
MOVEMENT_TYPE = "TREND_PULLBACK"
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_TREND_SCORE": 0.45,
    "MAX_PULLBACK_DISTANCE_PCT": 0.0035,
    "MIN_STRUCTURE_RESUME_PCT": 0.0004,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)
TEMPORAL_CONTRACT_VERSION = "trend_pullback_temporal_v1"
IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class _HistoryBar:
    symbol: str
    session_date: str
    timeframe: str
    bar_start_timestamp: str
    bar_end_timestamp: str
    open: float
    high: float
    low: float
    close: float
    start_dt: datetime
    end_dt: datetime


@dataclass(frozen=True)
class _ValidatedHistory:
    bars: tuple[_HistoryBar, ...] | None
    missing_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()
    reason: str = "missing_required_temporal_evidence"

    @property
    def valid(self) -> bool:
        return self.bars is not None and not self.missing_fields and not self.invalid_fields


@dataclass(frozen=True)
class _TemporalContractResult:
    valid: bool
    missing_fields: tuple[str, ...] = ()
    invalid_fields: tuple[str, ...] = ()
    reason: str = "missing_required_temporal_evidence"
    setup_identity: dict[str, Any] | None = None


def generate_trend_pullback_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate CALL/PUT candidates after pullback hold and trend resumption."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    min_trend_score = float(params["MIN_TREND_SCORE"])

    if block_on_required_fields(
        STRATEGY_ID,
        reason="missing_required_thesis_evidence",
        field_specs=(
            ("spot_ltp", ctx.spot_ltp, "positive"),
            ("vwap", ctx.vwap, "positive"),
        ),
    ):
        return ()

    history_result = _validated_completed_history(ctx)
    trend_up = safe_float(regime.scores.get("TREND_UP")) or 0.0
    trend_down = safe_float(regime.scores.get("TREND_DOWN")) or 0.0

    if not history_result.valid:
        if trend_up >= min_trend_score or trend_down >= min_trend_score:
            emit_strategy_evidence_blocked(
                STRATEGY_ID,
                reason=history_result.reason,
                missing_fields=history_result.missing_fields,
                invalid_fields=history_result.invalid_fields,
            )
        return ()

    assert history_result.bars is not None
    bars = history_result.bars
    vwap = safe_float(ctx.vwap)
    assert vwap is not None

    candidates: list[StrategyCandidate] = []

    if trend_up >= min_trend_score:
        call_result = _call_pullback_result(
            ctx,
            bars=bars,
            vwap=vwap,
            max_pullback_distance_pct=float(params["MAX_PULLBACK_DISTANCE_PCT"]),
            min_structure_resume_pct=float(params["MIN_STRUCTURE_RESUME_PCT"]),
        )
        if call_result.valid:
            candidates.append(
                _build_candidate(
                    ctx,
                    regime,
                    profile,
                    "BUY_CALL",
                    trend_up,
                    call_result.setup_identity,
                )
            )
        else:
            emit_strategy_evidence_blocked(
                STRATEGY_ID,
                reason=call_result.reason,
                missing_fields=call_result.missing_fields,
                invalid_fields=call_result.invalid_fields,
            )

    if trend_down >= min_trend_score:
        put_result = _put_pullback_result(
            ctx,
            bars=bars,
            vwap=vwap,
            max_pullback_distance_pct=float(params["MAX_PULLBACK_DISTANCE_PCT"]),
            min_structure_resume_pct=float(params["MIN_STRUCTURE_RESUME_PCT"]),
        )
        if put_result.valid:
            candidates.append(
                _build_candidate(
                    ctx,
                    regime,
                    profile,
                    "BUY_PUT",
                    trend_down,
                    put_result.setup_identity,
                )
            )
        else:
            emit_strategy_evidence_blocked(
                STRATEGY_ID,
                reason=put_result.reason,
                missing_fields=put_result.missing_fields,
                invalid_fields=put_result.invalid_fields,
            )

    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
    direction: str,
    trend_score: float,
    setup_identity: dict[str, Any] | None,
) -> StrategyCandidate:
    params = dict(profile.parameters)
    max_pullback_distance_pct = float(params["MAX_PULLBACK_DISTANCE_PCT"])
    min_structure_resume_pct = float(params["MIN_STRUCTURE_RESUME_PCT"])
    side = side_evidence(ctx, direction)
    anchor = _pullback_anchor(ctx, direction)
    spot = safe_float(ctx.spot_ltp)
    pullback_distance = pct_distance(spot, anchor) or 0.0
    resume_distance = _resume_distance(ctx, direction, anchor)
    price_structure_score = clamp_score(
        0.45 * trend_score
        + 0.35
        * (
            1.0
            - ratio_score(pullback_distance, start=0.0, full=max_pullback_distance_pct)
        )
        + 0.20
        * ratio_score(resume_distance, start=min_structure_resume_pct, full=0.003)
    )
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "nearest_support": ctx.nearest_support,
        "nearest_resistance": ctx.nearest_resistance,
        "trend_score": trend_score,
        "pullback_anchor": anchor,
        "pullback_distance_pct": pullback_distance,
        "resume_distance_pct": resume_distance,
        "temporal_contract_version": TEMPORAL_CONTRACT_VERSION,
        "setup_identity": setup_identity,
        "option_ltp": side.option_ltp,
        "premium_change": side.premium_change,
        "spread_pct": side.spread_pct,
        "depth": side.depth,
    }
    return make_candidate(
        ctx=ctx,
        regime=regime,
        strategy_id=STRATEGY_ID,
        movement_type=MOVEMENT_TYPE,
        direction=direction,
        price_structure_score=price_structure_score,
        side=side,
        entry_trigger="trend_pullback_hold_resume",
        invalid_if="pullback_breaks_anchor",
        rank_reason="established trend resumed after a controlled pullback",
        evidence=evidence,
        warnings=(),
        confluence_tags=("trend", "pullback_hold"),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.parameter_hash,
        promotion_state="ADVISORY_ONLY",
    )


def _pullback_anchor(ctx: StrategyContext, direction: str) -> float | None:
    if direction == "BUY_CALL":
        return safe_float(ctx.nearest_support)
    if direction == "BUY_PUT":
        return safe_float(ctx.nearest_resistance)
    return None


def _resume_distance(
    ctx: StrategyContext, direction: str, anchor: float | None
) -> float:
    spot = safe_float(ctx.spot_ltp)
    if spot is None or anchor is None or anchor <= 0:
        return 0.0
    if direction == "BUY_CALL" and spot >= anchor:
        return (spot - anchor) / abs(anchor)
    if direction == "BUY_PUT" and spot <= anchor:
        return (anchor - spot) / abs(anchor)
    return 0.0


def _call_pullback_result(
    ctx: StrategyContext,
    *,
    bars: tuple[_HistoryBar, ...],
    vwap: float,
    max_pullback_distance_pct: float,
    min_structure_resume_pct: float,
) -> _TemporalContractResult:
    support = safe_float(ctx.nearest_support)
    if support is None or support <= 0:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("nearest_support",),
            reason="missing_required_structure_anchor",
        )
    first, second, pullback, trigger = bars[-4:]
    if first.close >= second.close:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("trend_establishment",),
            reason="missing_required_temporal_evidence",
        )
    if second.close < vwap:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("trend_vwap_alignment",),
            reason="missing_required_temporal_evidence",
        )
    spot = safe_float(ctx.spot_ltp)
    if spot is None or spot < support or spot < vwap:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("spot_ltp", "vwap_alignment"),
            reason="missing_required_thesis_evidence",
        )
    pullback_distance = pct_distance(spot, support)
    if pullback_distance is None or pullback_distance > max_pullback_distance_pct:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("pullback_distance_pct",),
            reason="missing_required_temporal_evidence",
        )
    if second.close <= pullback.close:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("pullback_structure",),
            reason="missing_required_temporal_evidence",
        )
    if pullback.close < support or trigger.close < support:
        return _TemporalContractResult(
            valid=False,
            invalid_fields=("nearest_support",),
            reason="pullback_breaks_anchor",
        )
    if pullback.close >= trigger.close:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("continuation_trigger",),
            reason="missing_required_temporal_evidence",
        )
    if trigger.close < vwap:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("vwap_alignment",),
            reason="missing_required_temporal_evidence",
        )
    resume_distance = _resume_distance(ctx, "BUY_CALL", support)
    if resume_distance < min_structure_resume_pct:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("resume_distance_pct",),
            reason="missing_required_temporal_evidence",
        )
    setup_identity = {
        "contract_version": TEMPORAL_CONTRACT_VERSION,
        "symbol": ctx.symbol,
        "session_date": first.session_date,
        "direction": "BUY_CALL",
        "trend_establishment_timestamp": second.bar_end_timestamp,
        "pullback_ready_timestamp": pullback.bar_end_timestamp,
        "expiry_timestamp": trigger.bar_end_timestamp,
    }
    return _TemporalContractResult(valid=True, setup_identity=setup_identity)


def _put_pullback_result(
    ctx: StrategyContext,
    *,
    bars: tuple[_HistoryBar, ...],
    vwap: float,
    max_pullback_distance_pct: float,
    min_structure_resume_pct: float,
) -> _TemporalContractResult:
    resistance = safe_float(ctx.nearest_resistance)
    if resistance is None or resistance <= 0:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("nearest_resistance",),
            reason="missing_required_structure_anchor",
        )
    first, second, pullback, trigger = bars[-4:]
    if first.close <= second.close:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("trend_establishment",),
            reason="missing_required_temporal_evidence",
        )
    if second.close > vwap:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("trend_vwap_alignment",),
            reason="missing_required_temporal_evidence",
        )
    spot = safe_float(ctx.spot_ltp)
    if spot is None or spot > resistance or spot > vwap:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("spot_ltp", "vwap_alignment"),
            reason="missing_required_thesis_evidence",
        )
    pullback_distance = pct_distance(spot, resistance)
    if pullback_distance is None or pullback_distance > max_pullback_distance_pct:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("pullback_distance_pct",),
            reason="missing_required_temporal_evidence",
        )
    if second.close >= pullback.close:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("pullback_structure",),
            reason="missing_required_temporal_evidence",
        )
    if pullback.close > resistance or trigger.close > resistance:
        return _TemporalContractResult(
            valid=False,
            invalid_fields=("nearest_resistance",),
            reason="pullback_breaks_anchor",
        )
    if pullback.close <= trigger.close:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("continuation_trigger",),
            reason="missing_required_temporal_evidence",
        )
    if trigger.close > vwap:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("vwap_alignment",),
            reason="missing_required_temporal_evidence",
        )
    resume_distance = _resume_distance(ctx, "BUY_PUT", resistance)
    if resume_distance < min_structure_resume_pct:
        return _TemporalContractResult(
            valid=False,
            missing_fields=("resume_distance_pct",),
            reason="missing_required_temporal_evidence",
        )
    setup_identity = {
        "contract_version": TEMPORAL_CONTRACT_VERSION,
        "symbol": ctx.symbol,
        "session_date": first.session_date,
        "direction": "BUY_PUT",
        "trend_establishment_timestamp": second.bar_end_timestamp,
        "pullback_ready_timestamp": pullback.bar_end_timestamp,
        "expiry_timestamp": trigger.bar_end_timestamp,
    }
    return _TemporalContractResult(valid=True, setup_identity=setup_identity)


def _validated_completed_history(ctx: StrategyContext) -> _ValidatedHistory:
    history = ctx.completed_bar_history
    if history is None:
        return _ValidatedHistory(None, ("completed_bar_history",), ())
    if not isinstance(history, (list, tuple)):
        return _ValidatedHistory(None, (), ("completed_bar_history",))
    if len(history) < 4:
        return _ValidatedHistory(None, ("completed_bar_history",), ())

    normalized: list[_HistoryBar] = []
    invalid_fields: list[str] = []
    seen_starts: set[datetime] = set()
    previous_start: datetime | None = None
    symbols: set[str] = set()
    sessions: set[str] = set()
    timeframes: set[str] = set()
    for index, entry in enumerate(history):
        bar, _, bar_invalid = _coerce_completed_bar(entry, index=index)
        invalid_fields.extend(bar_invalid)
        if bar is None:
            continue
        if previous_start is not None and bar.start_dt < previous_start:
            invalid_fields.append(f"completed_bar_history[{index}].bar_start_timestamp")
        if bar.start_dt in seen_starts:
            invalid_fields.append(f"completed_bar_history[{index}].bar_start_timestamp")
        previous_start = bar.start_dt
        seen_starts.add(bar.start_dt)
        symbols.add(bar.symbol)
        sessions.add(bar.session_date)
        timeframes.add(bar.timeframe)
        normalized.append(bar)

    if not normalized:
        return _ValidatedHistory(
            None,
            (),
            tuple(sorted(set(invalid_fields))),
            "invalid_completed_history",
        )

    if len(symbols) > 1:
        for index in range(len(normalized)):
            invalid_fields.append(f"completed_bar_history[{index}].symbol")
    if len(sessions) > 1:
        for index in range(len(normalized)):
            invalid_fields.append(f"completed_bar_history[{index}].session_date")
    if len(timeframes) > 1:
        for index in range(len(normalized)):
            invalid_fields.append(f"completed_bar_history[{index}].timeframe")

    context_previous_close = safe_float(ctx.previous_completed_close)
    if ctx.previous_completed_close is not None and context_previous_close is None:
        invalid_fields.append("previous_completed_close")
    elif (
        context_previous_close is not None
        and len(normalized) >= 2
        and abs(context_previous_close - normalized[-2].close) > 1e-9
    ):
        invalid_fields.append("previous_completed_close")

    if invalid_fields:
        return _ValidatedHistory(
            None,
            (),
            tuple(sorted(set(invalid_fields))),
            "invalid_completed_history",
        )

    return _ValidatedHistory(tuple(normalized), (), (), "missing_required_temporal_evidence")


def _coerce_completed_bar(entry: object, *, index: int) -> tuple[_HistoryBar | None, tuple[str, ...], tuple[str, ...]]:
    if not isinstance(entry, Mapping):
        return None, (), (f"completed_bar_history[{index}]",)

    invalid_fields: list[str] = []

    symbol = str(entry.get("symbol") or "").strip().upper()
    session_date = str(entry.get("session_date") or "").strip()
    timeframe = str(entry.get("timeframe") or "").strip().lower()
    start_raw = entry.get("bar_start_timestamp") or entry.get("ts")
    end_raw = entry.get("bar_end_timestamp")
    start_dt = _parse_timestamp(start_raw)
    end_dt = _parse_timestamp(end_raw)
    open_price = safe_float(entry.get("open"))
    high_price = safe_float(entry.get("high"))
    low_price = safe_float(entry.get("low"))
    close_price = safe_float(entry.get("close"))

    if not symbol:
        invalid_fields.append(f"completed_bar_history[{index}].symbol")
    if not session_date:
        invalid_fields.append(f"completed_bar_history[{index}].session_date")
    if timeframe != "1m":
        invalid_fields.append(f"completed_bar_history[{index}].timeframe")
    if start_dt is None:
        invalid_fields.append(f"completed_bar_history[{index}].bar_start_timestamp")
    if end_dt is None:
        invalid_fields.append(f"completed_bar_history[{index}].bar_end_timestamp")
    elif start_dt is not None and end_dt <= start_dt:
        invalid_fields.append(f"completed_bar_history[{index}].bar_end_timestamp")
    if open_price is None or open_price <= 0:
        invalid_fields.append(f"completed_bar_history[{index}].open")
    if high_price is None or high_price <= 0:
        invalid_fields.append(f"completed_bar_history[{index}].high")
    if low_price is None or low_price <= 0:
        invalid_fields.append(f"completed_bar_history[{index}].low")
    if close_price is None or close_price <= 0:
        invalid_fields.append(f"completed_bar_history[{index}].close")
    if (
        open_price is not None
        and high_price is not None
        and low_price is not None
        and close_price is not None
        and (high_price < max(open_price, close_price, low_price) or low_price > min(open_price, close_price, high_price))
    ):
        invalid_fields.append(f"completed_bar_history[{index}].ohlc")
    if entry.get("is_complete") is False:
        invalid_fields.append(f"completed_bar_history[{index}].is_complete")

    if invalid_fields:
        return None, (), tuple(sorted(set(invalid_fields)))

    assert start_dt is not None
    assert end_dt is not None
    assert open_price is not None
    assert high_price is not None
    assert low_price is not None
    assert close_price is not None
    return (
        _HistoryBar(
            symbol=symbol,
            session_date=session_date,
            timeframe=timeframe,
            bar_start_timestamp=str(start_raw),
            bar_end_timestamp=str(end_raw),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            start_dt=start_dt,
            end_dt=end_dt,
        ),
        (),
        (),
    )


def _parse_timestamp(value: object) -> datetime | None:
    if value in (None, "", "None"):
        return None
    try:
        out = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=IST)
    return out


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_trend_pullback_candidates"]
