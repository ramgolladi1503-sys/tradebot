"""Opening Range Breakout Retest movement strategy.

This strategy avoids chasing the first break. It emits candidates only when the
opening range is completed from causal one-minute bars, the breakout is later
retested, and a strictly later continuation bar confirms the setup. It is
read-only and never calls broker/order/depth/execution code.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections.abc import Mapping
from zoneinfo import ZoneInfo
from typing import Any

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_parameter_profiles import (
    RuntimeProfileResolution,
    resolve_required_profile_parameters,
)
from strategies.movement._utils import (
    clamp_score,
    emit_strategy_evidence_blocked,
    make_candidate,
    pct_distance,
    ratio_score,
    safe_float,
    side_evidence,
)

IST = ZoneInfo("Asia/Kolkata")
STRATEGY_ID = "opening_range_retest_v1"
MOVEMENT_TYPE = "OPENING_RANGE_RETEST"
TEMPORAL_CONTRACT_VERSION = "opening_range_retest_temporal_v1"
TEMPORAL_PROPOSAL_STATE = "READY_FOR_PUBLICATION"
OPENING_RANGE_BARS = 15
MAX_BREAKOUT_TO_RETEST_AGE = 5
MAX_RETEST_TO_CONTINUATION_AGE = 3
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_RETEST_MINUTES": 15,
    "MAX_RETEST_MINUTES": 90,
    "MAX_RETEST_DISTANCE_PCT": 0.0018,
    "MIN_BREAKOUT_DISTANCE_PCT": 0.0008,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)


@dataclass(frozen=True)
class _HistoryBar:
    index: int
    symbol: str
    session_date: str
    timeframe: str
    bar_start_timestamp: str
    bar_end_timestamp: str
    start_dt: datetime
    end_dt: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class _ValidatedHistory:
    bars: tuple[_HistoryBar, ...] | None
    missing_fields: tuple[str, ...]
    invalid_fields: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class _DirectionalSetup:
    direction: str
    boundary_type: str
    normalized_boundary_value: float
    orb_high: float
    orb_low: float
    breakout_bar: _HistoryBar
    retest_bar: _HistoryBar
    continuation_bar: _HistoryBar
    causal_history: tuple[_HistoryBar, ...]
    setup_id: str
    history_hash: str


def generate_opening_range_retest_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate ORB retest candidates for CALL/PUT when completed history exists."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    history_result = _validated_completed_history(ctx)
    if history_result.invalid_fields:
        emit_strategy_evidence_blocked(
            STRATEGY_ID,
            reason=history_result.reason,
            missing_fields=history_result.missing_fields,
            invalid_fields=history_result.invalid_fields,
        )
        return ()
    history = history_result.bars
    if history is None or len(history) < OPENING_RANGE_BARS:
        emit_strategy_evidence_blocked(
            STRATEGY_ID,
            reason=history_result.reason,
            missing_fields=history_result.missing_fields or ("completed_bar_history",),
            invalid_fields=history_result.invalid_fields,
        )
        return ()

    candidates: list[StrategyCandidate] = []
    opening_range = history[:OPENING_RANGE_BARS]
    orb_high = max(bar.high for bar in opening_range)
    orb_low = min(bar.low for bar in opening_range)
    orb_invalid_fields = _reconcile_supplied_orb_fields(
        supplied_orb_high=ctx.orb_high,
        supplied_orb_low=ctx.orb_low,
        recomputed_orb_high=orb_high,
        recomputed_orb_low=orb_low,
    )
    if orb_invalid_fields:
        emit_strategy_evidence_blocked(
            STRATEGY_ID,
            reason="invalid_orb_reconciliation",
            invalid_fields=orb_invalid_fields,
        )
        return ()

    for direction in ("BUY_CALL", "BUY_PUT"):
        setup = _scan_directional_setup(
            history=history,
            direction=direction,
            orb_high=orb_high,
            orb_low=orb_low,
        )
        if setup is not None:
            candidates.append(_build_temporal_candidate(ctx, regime, profile, setup))
    return tuple(candidates)


def _build_temporal_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
    setup: _DirectionalSetup,
) -> StrategyCandidate:
    params = dict(profile.parameters)
    max_retest_distance_pct = float(params["MAX_RETEST_DISTANCE_PCT"])
    min_breakout_distance_pct = float(params["MIN_BREAKOUT_DISTANCE_PCT"])
    side = side_evidence(ctx, setup.direction)
    scoring_spot = setup.breakout_bar.close
    retest_level = setup.normalized_boundary_value
    retest_distance = pct_distance(scoring_spot, retest_level) or 0.0
    breakout_distance = _breakout_distance(scoring_spot, setup.direction, retest_level)
    price_structure_score = clamp_score(
        0.45
        * (1.0 - ratio_score(retest_distance, start=0.0, full=max_retest_distance_pct))
        + 0.35
        * ratio_score(breakout_distance, start=min_breakout_distance_pct, full=0.004)
        + 0.20 * clamp_score(regime.scores.get("VOLATILITY_EXPANSION", 0.0))
    )
    completed_history_provenance = _completed_history_provenance(ctx, setup)
    evidence = {
        "spot_ltp": scoring_spot,
        "vwap": ctx.vwap,
        "orb_high": setup.orb_high,
        "orb_low": setup.orb_low,
        "retest_level": retest_level,
        "retest_distance_pct": retest_distance,
        "breakout_distance_pct": breakout_distance,
        "setup_identity": {
            "contract_version": TEMPORAL_CONTRACT_VERSION,
            "strategy_id": STRATEGY_ID,
            "symbol": ctx.symbol,
            "session_date": setup.breakout_bar.session_date,
            "direction": setup.direction,
            "boundary_type": setup.boundary_type,
            "normalized_boundary_value": setup.normalized_boundary_value,
            "breakout_timestamp": setup.breakout_bar.bar_end_timestamp,
            "retest_timestamp": setup.retest_bar.bar_end_timestamp,
            "continuation_timestamp": setup.continuation_bar.bar_end_timestamp,
            "proposal_ready_at_iso": setup.continuation_bar.bar_end_timestamp,
            "setup_id": setup.setup_id,
            "history_hash": setup.history_hash,
        },
        "completed_bar_history_provenance": completed_history_provenance,
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
        direction=setup.direction,
        price_structure_score=price_structure_score,
        side=side,
        entry_trigger="opening_range_breakout_retest_hold",
        invalid_if="price_returns_inside_opening_range",
        rank_reason="opening range breakout retest held",
        evidence=evidence,
        warnings=(),
        confluence_tags=("orb_retest", "vwap_alignment"),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.parameter_hash,
        promotion_state=TEMPORAL_PROPOSAL_STATE,
    )


def _validated_completed_history(ctx: StrategyContext) -> _ValidatedHistory:
    history = ctx.completed_bar_history
    if history is None:
        return _ValidatedHistory(None, ("completed_bar_history",), (), "missing_required_temporal_evidence")
    if not isinstance(history, (list, tuple)):
        return _ValidatedHistory(None, (), ("completed_bar_history",), "invalid_completed_history")
    if not history:
        return _ValidatedHistory(None, ("completed_bar_history",), (), "missing_required_temporal_evidence")

    normalized: list[_HistoryBar] = []
    invalid_fields: list[str] = []
    symbols: set[str] = set()
    sessions: set[str] = set()
    timeframes: set[str] = set()
    seen_starts: set[datetime] = set()
    previous_start: datetime | None = None
    for index, entry in enumerate(history):
        bar, bar_invalid = _coerce_completed_bar(entry, index=index)
        invalid_fields.extend(bar_invalid)
        if bar is None:
            continue
        normalized.append(bar)
        symbols.add(bar.symbol)
        sessions.add(bar.session_date)
        timeframes.add(bar.timeframe)
        if previous_start is not None and bar.start_dt < previous_start:
            invalid_fields.append(f"completed_bar_history[{index}].bar_start_timestamp")
        if bar.start_dt in seen_starts:
            invalid_fields.append(f"completed_bar_history[{index}].bar_start_timestamp")
        seen_starts.add(bar.start_dt)
        previous_start = bar.start_dt

    if not normalized:
        return _ValidatedHistory(None, (), tuple(sorted(set(invalid_fields))) or ("completed_bar_history",), "invalid_completed_history")

    if len(symbols) > 1:
        invalid_fields.extend(f"completed_bar_history[{bar.index}].symbol" for bar in normalized)
    if len(sessions) > 1:
        invalid_fields.extend(f"completed_bar_history[{bar.index}].session_date" for bar in normalized)
    if len(timeframes) > 1:
        invalid_fields.extend(f"completed_bar_history[{bar.index}].timeframe" for bar in normalized)

    session_date = normalized[0].session_date
    session_open = _session_open_timestamp(session_date)
    for position, bar in enumerate(normalized):
        expected_start = session_open + timedelta(minutes=position)
        expected_end = expected_start + timedelta(minutes=1)
        if bar.start_dt != expected_start:
            invalid_fields.append(f"completed_bar_history[{bar.index}].bar_start_timestamp")
        if bar.end_dt != expected_end:
            invalid_fields.append(f"completed_bar_history[{bar.index}].bar_end_timestamp")

    if invalid_fields:
        return _ValidatedHistory(None, (), tuple(sorted(set(invalid_fields))), "invalid_completed_history")

    return _ValidatedHistory(tuple(normalized), (), (), "missing_required_temporal_evidence")


def _coerce_completed_bar(entry: object, *, index: int) -> tuple[_HistoryBar | None, tuple[str, ...]]:
    if not isinstance(entry, Mapping):
        return None, (f"completed_bar_history[{index}]",)

    invalid_fields: list[str] = []
    symbol = str(entry.get("symbol") or "").strip().upper()
    session_date = str(entry.get("session_date") or "").strip()
    timeframe = str(entry.get("timeframe") or "").strip().lower()
    start_raw = entry.get("bar_start_timestamp") or entry.get("ts") or entry.get("date")
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
        return None, tuple(sorted(set(invalid_fields)))

    assert start_dt is not None
    assert end_dt is not None
    assert open_price is not None
    assert high_price is not None
    assert low_price is not None
    assert close_price is not None
    return (
        _HistoryBar(
            index=index,
            symbol=symbol,
            session_date=session_date,
            timeframe=timeframe,
            bar_start_timestamp=str(start_raw),
            bar_end_timestamp=str(end_raw),
            start_dt=start_dt,
            end_dt=end_dt,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
        ),
        (),
    )


def _scan_directional_setup(
    *,
    history: tuple[_HistoryBar, ...],
    direction: str,
    orb_high: float,
    orb_low: float,
) -> _DirectionalSetup | None:
    breakout_bar: _HistoryBar | None = None
    retest_bar: _HistoryBar | None = None
    breakout_index: int | None = None
    retest_index: int | None = None

    for index, bar in enumerate(history[OPENING_RANGE_BARS:], start=OPENING_RANGE_BARS):
        while True:
            if breakout_index is not None and retest_index is None and index - breakout_index > MAX_BREAKOUT_TO_RETEST_AGE:
                breakout_bar = None
                breakout_index = None
                continue
            if breakout_index is not None and retest_index is not None and index - retest_index > MAX_RETEST_TO_CONTINUATION_AGE:
                breakout_bar = None
                retest_bar = None
                breakout_index = None
                retest_index = None
                continue
            break

        if breakout_index is None:
            if _is_breakout(bar, direction=direction, orb_high=orb_high, orb_low=orb_low):
                breakout_index = index
                breakout_bar = bar
            continue

        assert breakout_bar is not None
        if retest_index is None:
            if _is_invalidation(bar, direction=direction, orb_high=orb_high, orb_low=orb_low):
                breakout_bar = None
                breakout_index = None
                continue
            if _is_retest(bar, direction=direction, orb_high=orb_high, orb_low=orb_low):
                retest_index = index
                retest_bar = bar
            continue

        assert retest_bar is not None
        if _is_invalidation_after_retest(bar, direction=direction, orb_high=orb_high, orb_low=orb_low):
            breakout_bar = None
            retest_bar = None
            breakout_index = None
            retest_index = None
            continue
        if _is_continuation(bar, direction=direction, retest_bar=retest_bar):
            if index != len(history) - 1:
                continue
            previous_bar = history[index - 1] if index > 0 else None
            if previous_bar is not None and _is_continuation(previous_bar, direction=direction, retest_bar=retest_bar):
                continue
            causal_history = history[: index + 1]
            return _DirectionalSetup(
                direction=direction,
                boundary_type="ORB_HIGH" if direction == "BUY_CALL" else "ORB_LOW",
                normalized_boundary_value=orb_high if direction == "BUY_CALL" else orb_low,
                orb_high=orb_high,
                orb_low=orb_low,
                breakout_bar=breakout_bar,
                retest_bar=retest_bar,
                continuation_bar=bar,
                causal_history=causal_history,
                setup_id=_build_setup_id(
                    strategy_id=STRATEGY_ID,
                    symbol=bar.symbol,
                    session_date=bar.session_date,
                    direction=direction,
                    boundary_type="ORB_HIGH" if direction == "BUY_CALL" else "ORB_LOW",
                    normalized_boundary_value=orb_high if direction == "BUY_CALL" else orb_low,
                    breakout_timestamp=breakout_bar.bar_end_timestamp,
                ),
                history_hash=_build_history_hash(causal_history),
            )
    return None


def _is_breakout(bar: _HistoryBar, *, direction: str, orb_high: float, orb_low: float) -> bool:
    if direction == "BUY_CALL":
        return bar.close > orb_high
    return bar.close < orb_low


def _is_retest(bar: _HistoryBar, *, direction: str, orb_high: float, orb_low: float) -> bool:
    if direction == "BUY_CALL":
        return bar.low <= orb_high and bar.close >= orb_high and bar.low > orb_low
    return bar.high >= orb_low and bar.close <= orb_low and bar.high < orb_high


def _is_continuation(bar: _HistoryBar, *, direction: str, retest_bar: _HistoryBar) -> bool:
    if direction == "BUY_CALL":
        return bar.close > retest_bar.high
    return bar.close < retest_bar.low


def _is_invalidation(bar: _HistoryBar, *, direction: str, orb_high: float, orb_low: float) -> bool:
    if direction == "BUY_CALL":
        return bar.close < orb_high
    return bar.close > orb_low


def _is_invalidation_after_retest(bar: _HistoryBar, *, direction: str, orb_high: float, orb_low: float) -> bool:
    return _is_invalidation(bar, direction=direction, orb_high=orb_high, orb_low=orb_low)


def _session_open_timestamp(session_date: str) -> datetime:
    return datetime.fromisoformat(f"{session_date}T09:15:00+05:30").astimezone(IST)


def _parse_timestamp(value: object) -> datetime | None:
    if value in (None, "", "None"):
        return None
    try:
        out = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=IST)
    return out.astimezone(IST)


def _build_setup_id(
    *,
    strategy_id: str,
    symbol: str,
    session_date: str,
    direction: str,
    boundary_type: str,
    normalized_boundary_value: float,
    breakout_timestamp: str,
) -> str:
    payload = {
        "strategy_id": strategy_id,
        "symbol": symbol,
        "session_date": session_date,
        "direction": direction,
        "boundary_type": boundary_type,
        "normalized_boundary_value": normalized_boundary_value,
        "breakout_timestamp": breakout_timestamp,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _build_history_hash(rows: tuple[_HistoryBar, ...]) -> str:
    payload = [
        {
            "timestamp_iso_ist": bar.bar_start_timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
        }
        for bar in rows
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _completed_history_provenance(ctx: StrategyContext, setup: _DirectionalSetup) -> dict[str, Any]:
    provenance = dict(ctx.metadata.get("completed_bar_history_provenance") or {})
    if provenance:
        provenance.setdefault("source_field", "completed_bar_history")
        provenance.setdefault("source_component", "core.runtime_snapshot_producer")
        provenance.setdefault("status", "TRUTHFUL")
        provenance.setdefault("source_event_timestamp", setup.continuation_bar.bar_end_timestamp)
        provenance.setdefault("receipt_timestamp", setup.continuation_bar.bar_end_timestamp)
        provenance.setdefault("timeframe", "1m")
        provenance.setdefault("symbol", ctx.symbol)
        provenance.setdefault("session_date", setup.breakout_bar.session_date)
        provenance.setdefault("completed_bar_count", len(setup.causal_history))
        provenance.setdefault("latest_completed_timestamp", setup.continuation_bar.bar_end_timestamp)
        provenance.setdefault("history_hash", setup.history_hash)
        return provenance
    return {
        "status": "TRUTHFUL",
        "source_component": "strategies.movement.opening_range_breakout",
        "source_field": "completed_bar_history",
        "source_event_timestamp": setup.continuation_bar.bar_end_timestamp,
        "receipt_timestamp": setup.continuation_bar.bar_end_timestamp,
        "timeframe": "1m",
        "symbol": ctx.symbol,
        "session_date": setup.breakout_bar.session_date,
        "completed_bar_count": len(setup.causal_history),
        "latest_completed_timestamp": setup.continuation_bar.bar_end_timestamp,
        "history_hash": setup.history_hash,
    }


def _reconcile_supplied_orb_fields(
    *,
    supplied_orb_high: object,
    supplied_orb_low: object,
    recomputed_orb_high: float,
    recomputed_orb_low: float,
) -> tuple[str, ...]:
    invalid_fields: list[str] = []
    if supplied_orb_high is not None:
        supplied_high = safe_float(supplied_orb_high)
        if supplied_high is None or abs(supplied_high - recomputed_orb_high) > 1e-9:
            invalid_fields.append("orb_high")
    if supplied_orb_low is not None:
        supplied_low = safe_float(supplied_orb_low)
        if supplied_low is None or abs(supplied_low - recomputed_orb_low) > 1e-9:
            invalid_fields.append("orb_low")
    return tuple(sorted(set(invalid_fields)))


def _call_retest_confirmed(
    profile: RuntimeProfileResolution,
    *,
    spot: float | None,
    vwap: float | None,
    orb_high: float | None,
) -> bool:
    params = dict(profile.parameters)
    max_retest_distance_pct = float(params["MAX_RETEST_DISTANCE_PCT"])
    return (
        spot is not None
        and orb_high is not None
        and vwap is not None
        and spot >= orb_high
        and spot >= vwap
        and (pct_distance(spot, orb_high) or 1.0) <= max_retest_distance_pct
        and ((spot - orb_high) / abs(orb_high)) >= 0.0
    )


def _put_retest_confirmed(
    profile: RuntimeProfileResolution,
    *,
    spot: float | None,
    vwap: float | None,
    orb_low: float | None,
) -> bool:
    params = dict(profile.parameters)
    max_retest_distance_pct = float(params["MAX_RETEST_DISTANCE_PCT"])
    return (
        spot is not None
        and orb_low is not None
        and vwap is not None
        and spot <= orb_low
        and spot <= vwap
        and (pct_distance(spot, orb_low) or 1.0) <= max_retest_distance_pct
        and ((orb_low - spot) / abs(orb_low)) >= 0.0
    )


def _breakout_distance(
    spot: float | None,
    direction: str,
    level: float | None,
) -> float:
    if spot is None:
        return 0.0
    if level is None:
        return 0.0
    if direction == "BUY_CALL":
        if spot < level:
            return 0.0
        return (spot - level) / abs(level)
    if spot > level:
        return 0.0
    return (level - spot) / abs(level)


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_opening_range_retest_candidates"]
