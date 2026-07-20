"""VWAP Reclaim/Rejection compatibility strategy.

This strategy keeps its historical compatibility identity but implements a
causal VWAP reclaim-and-hold pattern. It emits read-only StrategyCandidate
objects only and does not touch execution paths.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
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
    make_candidate,
    missing_evidence_warning,
    ratio_score,
    safe_float,
    side_evidence,
    signed_pct_distance,
)

IST = ZoneInfo("Asia/Kolkata")
STRATEGY_ID = "vwap_reclaim_rejection_v1"
MOVEMENT_TYPE = "VWAP_RECLAIM_REJECTION"
TEMPORAL_CONTRACT_VERSION = "vwap_reclaim_causal_v1"
IMPLEMENTED_PATTERN = "VWAP_RECLAIM_HOLD"
MIN_TEMPORAL_BAR_COUNT = 3
EMBEDDED_PROFILE_DEFAULTS = {
    "MIN_VWAP_DISTANCE_PCT": 0.00035,
    "MAX_VWAP_ENTRY_DISTANCE_PCT": 0.0035,
    "MAX_CHOP_SCORE": 0.55,
}
REQUIRED_PROFILE_KEYS = tuple(EMBEDDED_PROFILE_DEFAULTS)


@dataclass(frozen=True)
class _ValidatedHistoryBar:
    index: int
    symbol: str
    session_date: str
    timeframe: str
    bar_start_timestamp: str
    bar_end_timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None
    causal_vwap: float
    volume_provenance: str
    source_timestamp: str | None
    receipt_timestamp: str | None


@dataclass(frozen=True)
class _ValidatedHistoryResult:
    bars: tuple[_ValidatedHistoryBar, ...] | None
    missing_fields: tuple[str, ...]
    invalid_fields: tuple[str, ...]
    reason: str
    evaluation_cutoff: str | None
    history_hash: str | None
    volume_provenance: str | None


@dataclass(frozen=True)
class _CausalSequenceResult:
    direction: str
    history: tuple[_ValidatedHistoryBar, ...]
    vwap_provenance: str
    evaluation_cutoff: str
    history_hash: str


def generate_vwap_reclaim_rejection_candidates(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
) -> tuple[StrategyCandidate, ...]:
    """Generate CALL/PUT candidates for causal VWAP reclaim-and-hold events."""

    profile = resolve_required_profile_parameters(STRATEGY_ID, REQUIRED_PROFILE_KEYS)
    if not profile.is_valid:
        return ()
    params = dict(profile.parameters)
    min_vwap_distance_pct = float(params["MIN_VWAP_DISTANCE_PCT"])
    max_vwap_entry_distance_pct = float(params["MAX_VWAP_ENTRY_DISTANCE_PCT"])
    max_chop_score = float(params["MAX_CHOP_SCORE"])

    if float(regime.scores.get("CHOP", 0.0)) >= max_chop_score:
        return ()

    spot = safe_float(ctx.spot_ltp)
    vwap = safe_float(ctx.vwap)
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
    if history_result.invalid_fields:
        _emit_history_blocked(
            reason=history_result.reason,
            missing_fields=history_result.missing_fields,
            invalid_fields=history_result.invalid_fields,
        )
        return ()
    if history_result.bars is None or len(history_result.bars) < MIN_TEMPORAL_BAR_COUNT:
        _emit_history_blocked(
            reason=history_result.reason,
            missing_fields=history_result.missing_fields or ("completed_bar_history",),
            invalid_fields=history_result.invalid_fields,
        )
        return ()

    vwap_move = signed_pct_distance(spot, vwap)
    if vwap_move is None or abs(vwap_move) < min_vwap_distance_pct:
        return ()
    if abs(vwap_move) > max_vwap_entry_distance_pct:
        return ()

    candidates: list[StrategyCandidate] = []
    if vwap_move > 0:
        sequence = _sequence_from_history(history_result, ctx=ctx, direction="BUY_CALL")
        if sequence is not None:
            candidates.append(
                _build_candidate(
                    ctx,
                    regime,
                    profile,
                    "BUY_CALL",
                    vwap_move,
                    "upside_vwap_reclaim_hold",
                    sequence,
                )
            )
    if vwap_move < 0:
        sequence = _sequence_from_history(history_result, ctx=ctx, direction="BUY_PUT")
        if sequence is not None:
            candidates.append(
                _build_candidate(
                    ctx,
                    regime,
                    profile,
                    "BUY_PUT",
                    abs(vwap_move),
                    "downside_vwap_reclaim_hold",
                    sequence,
                )
            )
    return tuple(candidates)


def _build_candidate(
    ctx: StrategyContext,
    regime: MovementRegimeResult,
    profile: RuntimeProfileResolution,
    direction: str,
    vwap_distance_abs: float,
    confirmation_type: str,
    sequence: _CausalSequenceResult,
) -> StrategyCandidate:
    params = dict(profile.parameters)
    max_vwap_entry_distance_pct = float(params["MAX_VWAP_ENTRY_DISTANCE_PCT"])
    side = side_evidence(ctx, direction)
    slope_score = _vwap_slope_alignment_score(ctx, direction)
    distance_quality = clamp_score(
        1.0
        - ratio_score(vwap_distance_abs, start=0.0, full=max_vwap_entry_distance_pct)
    )
    price_structure_score = clamp_score(
        0.45 * distance_quality
        + 0.30 * slope_score
        + 0.25 * ratio_score(abs(safe_float(ctx.volume_z) or 0.0), start=0.5, full=2.0)
    )
    temporal_evidence = {
        "contract_version": TEMPORAL_CONTRACT_VERSION,
        "bar_interval": sequence.history[-1].timeframe,
        "minimum_bar_count": MIN_TEMPORAL_BAR_COUNT,
        "evaluation_cutoff": sequence.evaluation_cutoff,
        "symbol": sequence.history[-1].symbol,
        "session_date": sequence.history[-1].session_date,
        "direction": sequence.direction,
        "bar_count": len(sequence.history),
        "sequence_bar_timestamps": tuple(bar.bar_end_timestamp for bar in sequence.history),
        "sequence_stage_names": ("establishment", "reclaim", "hold"),
        "sequence_closes": tuple(bar.close for bar in sequence.history),
        "sequence_causal_vwap": tuple(bar.causal_vwap for bar in sequence.history),
        "vwap_provenance": sequence.vwap_provenance,
        "history_hash": sequence.history_hash,
        "completed_bar_history_provenance": _completed_history_provenance(ctx, sequence),
    }
    evidence = {
        "spot_ltp": ctx.spot_ltp,
        "vwap": ctx.vwap,
        "vwap_slope": ctx.vwap_slope,
        "vwap_distance_abs_pct": vwap_distance_abs,
        "confirmation_type": confirmation_type,
        "implemented_pattern": IMPLEMENTED_PATTERN,
        "compatibility_strategy_id": STRATEGY_ID,
        "previous_spot_ltp": _metadata_float(ctx, "previous_spot_ltp"),
        "temporal_contract_version": TEMPORAL_CONTRACT_VERSION,
        "temporal_evidence": temporal_evidence,
        "option_ltp": side.option_ltp,
        "premium_change": side.premium_change,
        "spread_pct": side.spread_pct,
        "depth": side.depth,
    }
    warnings = missing_evidence_warning(STRATEGY_ID, "vwap_slope") if safe_float(ctx.vwap_slope) is None else ()
    return make_candidate(
        ctx=ctx,
        regime=regime,
        strategy_id=STRATEGY_ID,
        movement_type=MOVEMENT_TYPE,
        direction=direction,
        price_structure_score=price_structure_score,
        side=side,
        entry_trigger="confirmed_vwap_reclaim_hold",
        invalid_if="price_crosses_back_through_vwap",
        rank_reason="confirmed VWAP reclaim and hold in a non-chop regime",
        evidence=evidence,
        warnings=warnings,
        confluence_tags=("vwap", "reclaim_hold"),
        strategy_version="v1",
        params_used=params,
        params_hash=profile.parameter_hash,
        promotion_state="ADVISORY_ONLY",
    )


def _sequence_from_history(
    history_result: _ValidatedHistoryResult,
    *,
    ctx: StrategyContext,
    direction: str,
) -> _CausalSequenceResult | None:
    history = history_result.bars
    if history is None or len(history) < MIN_TEMPORAL_BAR_COUNT:
        return None

    sequence = history[-MIN_TEMPORAL_BAR_COUNT :]
    bullish = direction == "BUY_CALL"
    if not _sequence_matches(sequence, bullish=bullish):
        return None

    final_vwap = sequence[-1].causal_vwap
    ctx_vwap = safe_float(ctx.vwap)
    if ctx_vwap is None or abs(ctx_vwap - final_vwap) > 1e-6:
        _emit_history_blocked(
            reason="inconsistent_causal_vwap",
            invalid_fields=("vwap",),
        )
        return None

    return _CausalSequenceResult(
        direction=direction,
        history=sequence,
        vwap_provenance=history_result.volume_provenance or sequence[-1].volume_provenance,
        evaluation_cutoff=history_result.evaluation_cutoff or sequence[-1].bar_end_timestamp,
        history_hash=history_result.history_hash or _history_hash(sequence),
    )


def _sequence_matches(sequence: tuple[_ValidatedHistoryBar, ...], *, bullish: bool) -> bool:
    if len(sequence) < MIN_TEMPORAL_BAR_COUNT:
        return False
    establishment, reclaim, hold = sequence
    if bullish:
        return (
            establishment.close < establishment.causal_vwap
            and reclaim.close > reclaim.causal_vwap
            and hold.close > hold.causal_vwap
        )
    return (
        establishment.close > establishment.causal_vwap
        and reclaim.close < reclaim.causal_vwap
        and hold.close < hold.causal_vwap
    )


def _validated_completed_history(ctx: StrategyContext) -> _ValidatedHistoryResult:
    history = ctx.completed_bar_history
    if history is None:
        return _ValidatedHistoryResult(
            None,
            ("completed_bar_history",),
            (),
            "missing_required_temporal_evidence",
            None,
            None,
            None,
        )
    if not isinstance(history, (list, tuple)):
        return _ValidatedHistoryResult(
            None,
            (),
            ("completed_bar_history",),
            "invalid_completed_history",
            None,
            None,
            None,
        )
    if not history:
        return _ValidatedHistoryResult(
            None,
            ("completed_bar_history",),
            (),
            "missing_required_temporal_evidence",
            None,
            None,
            None,
        )

    cutoff = _evaluation_cutoff(ctx, history)
    if cutoff is None:
        return _ValidatedHistoryResult(
            None,
            (),
            ("completed_bar_history",),
            "invalid_completed_history",
            None,
            None,
            None,
        )

    normalized_symbol = str(ctx.symbol or "").strip().upper()
    provisional: list[_ValidatedHistoryBar] = []
    missing_fields: list[str] = []
    invalid_fields: list[str] = []
    seen_starts: set[datetime] = set()
    previous_start: datetime | None = None
    volume_provenance = "VWAP_AUTHORITATIVE"

    for index, raw_bar in enumerate(history):
        if not isinstance(raw_bar, Mapping):
            invalid_fields.append(f"completed_bar_history[{index}]")
            continue
        bar_result = _coerce_history_bar(
            raw_bar,
            index=index,
            expected_symbol=normalized_symbol,
            previous_start=previous_start,
            seen_starts=seen_starts,
            cutoff=cutoff,
        )
        bar, bar_missing, bar_invalid, bar_volume_provenance = bar_result
        missing_fields.extend(bar_missing)
        invalid_fields.extend(bar_invalid)
        if bar is None:
            continue
        previous_start = _parse_datetime(bar.bar_start_timestamp)
        provisional.append(bar)
        if bar_volume_provenance == "VWAP_UNIT_WEIGHT_PROXY":
            volume_provenance = "VWAP_UNIT_WEIGHT_PROXY"

    if invalid_fields:
        return _ValidatedHistoryResult(
            None,
            tuple(sorted(set(missing_fields))),
            tuple(sorted(set(invalid_fields))),
            "invalid_completed_history",
            cutoff.isoformat(),
            None,
            volume_provenance,
        )

    validated = _with_causal_vwap(provisional)
    if len(validated) < MIN_TEMPORAL_BAR_COUNT:
        return _ValidatedHistoryResult(
            tuple(validated),
            ("completed_bar_history",),
            (),
            "missing_required_temporal_evidence",
            cutoff.isoformat(),
            _history_hash(validated),
            volume_provenance,
        )

    return _ValidatedHistoryResult(
        tuple(validated),
        (),
        (),
        "truthful_completed_history",
        cutoff.isoformat(),
        _history_hash(validated),
        volume_provenance,
    )


def _with_causal_vwap(bars: list[_ValidatedHistoryBar]) -> list[_ValidatedHistoryBar]:
    running_tp_weight = 0.0
    running_volume = 0.0
    result: list[_ValidatedHistoryBar] = []
    for bar in bars:
        weight = 1.0 if bar.volume is None or bar.volume <= 0 else float(bar.volume)
        typical_price = (bar.high + bar.low + bar.close) / 3.0
        running_tp_weight += typical_price * weight
        running_volume += weight
        result.append(
            replace(
                bar,
                causal_vwap=running_tp_weight / running_volume if running_volume > 0 else typical_price,
            )
        )
    return result


def _coerce_history_bar(
    raw_bar: Mapping[str, Any],
    *,
    index: int,
    expected_symbol: str,
    previous_start: datetime | None,
    seen_starts: set[datetime],
    cutoff: datetime,
) -> tuple[_ValidatedHistoryBar | None, tuple[str, ...], tuple[str, ...], str]:
    missing_fields: list[str] = []
    invalid_fields: list[str] = []
    volume_provenance = "VWAP_AUTHORITATIVE"

    raw_symbol = str(raw_bar.get("symbol") or raw_bar.get("instrument") or "").strip().upper()
    if not raw_symbol:
        missing_fields.append(f"completed_bar_history[{index}].symbol")
    elif raw_symbol != expected_symbol:
        invalid_fields.append(f"completed_bar_history[{index}].symbol")

    session_date = str(raw_bar.get("session_date") or "").strip()
    if not session_date:
        missing_fields.append(f"completed_bar_history[{index}].session_date")

    timeframe = str(raw_bar.get("timeframe") or "").strip().lower()
    if not timeframe:
        missing_fields.append(f"completed_bar_history[{index}].timeframe")
    elif timeframe != "1m":
        invalid_fields.append(f"completed_bar_history[{index}].timeframe")

    start_raw = raw_bar.get("bar_start_timestamp", raw_bar.get("ts", raw_bar.get("date")))
    if start_raw is None:
        missing_fields.append(f"completed_bar_history[{index}].bar_start_timestamp")
        return None, tuple(missing_fields), tuple(invalid_fields), volume_provenance
    start = _parse_datetime(start_raw)
    if start is None:
        invalid_fields.append(f"completed_bar_history[{index}].bar_start_timestamp")
        return None, tuple(missing_fields), tuple(invalid_fields), volume_provenance

    end_raw = raw_bar.get("bar_end_timestamp")
    end = _parse_datetime(end_raw) if end_raw is not None else start + timedelta(minutes=1)
    if end is None or end - start != timedelta(minutes=1):
        invalid_fields.append(f"completed_bar_history[{index}].bar_end_timestamp")
        return None, tuple(missing_fields), tuple(invalid_fields), volume_provenance
    if end > cutoff:
        return None, (), (), volume_provenance

    if previous_start is not None and start <= previous_start:
        invalid_fields.append(f"completed_bar_history[{index}].bar_start_timestamp")
    if start in seen_starts:
        invalid_fields.append(f"completed_bar_history[{index}].bar_start_timestamp")
    seen_starts.add(start)

    open_price = _parse_positive_float(raw_bar.get("open"))
    high_price = _parse_positive_float(raw_bar.get("high"))
    low_price = _parse_positive_float(raw_bar.get("low"))
    close_price = _parse_positive_float(raw_bar.get("close"))
    if open_price is None:
        missing_fields.append(f"completed_bar_history[{index}].open")
    if high_price is None:
        missing_fields.append(f"completed_bar_history[{index}].high")
    if low_price is None:
        missing_fields.append(f"completed_bar_history[{index}].low")
    if close_price is None:
        missing_fields.append(f"completed_bar_history[{index}].close")
    if missing_fields:
        return None, tuple(sorted(set(missing_fields))), tuple(sorted(set(invalid_fields))), volume_provenance
    assert open_price is not None
    assert high_price is not None
    assert low_price is not None
    assert close_price is not None

    if high_price < low_price:
        invalid_fields.append(f"completed_bar_history[{index}].high")
    if not (low_price <= open_price <= high_price):
        invalid_fields.append(f"completed_bar_history[{index}].open")
    if not (low_price <= close_price <= high_price):
        invalid_fields.append(f"completed_bar_history[{index}].close")

    raw_volume = raw_bar.get("volume")
    if raw_volume in (None, "", "None"):
        volume_value = None
        volume_provenance = "VWAP_UNIT_WEIGHT_PROXY"
    else:
        parsed_volume = _parse_numeric(raw_volume)
        if parsed_volume is None or parsed_volume < 0:
            invalid_fields.append(f"completed_bar_history[{index}].volume")
            return None, tuple(sorted(set(missing_fields))), tuple(sorted(set(invalid_fields))), volume_provenance
        if parsed_volume == 0:
            volume_value = 0.0
            volume_provenance = "VWAP_UNIT_WEIGHT_PROXY"
        else:
            volume_value = parsed_volume

    if raw_bar.get("is_complete") is False:
        invalid_fields.append(f"completed_bar_history[{index}].is_complete")

    source_timestamp = raw_bar.get("source_timestamp")
    receipt_timestamp = raw_bar.get("receipt_timestamp", raw_bar.get("receipt_ts"))

    return (
        _ValidatedHistoryBar(
            index=index,
            symbol=raw_symbol or expected_symbol,
            session_date=session_date or start.date().isoformat(),
            timeframe=timeframe or "1m",
            bar_start_timestamp=start.isoformat(),
            bar_end_timestamp=end.isoformat(),
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume_value,
            causal_vwap=0.0,
            volume_provenance=volume_provenance,
            source_timestamp=str(source_timestamp) if source_timestamp is not None else None,
            receipt_timestamp=str(receipt_timestamp) if receipt_timestamp is not None else None,
        ),
        tuple(sorted(set(missing_fields))),
        tuple(sorted(set(invalid_fields))),
        volume_provenance,
    )


def _evaluation_cutoff(ctx: StrategyContext, history: tuple[dict[str, Any], ...] | list[dict[str, Any]]) -> datetime | None:
    ts_epoch = safe_float(ctx.ts_epoch)
    if ts_epoch is not None:
        return datetime.fromtimestamp(ts_epoch, tz=IST)
    if not history:
        return None
    last = history[-1]
    last_end = _parse_datetime(last.get("bar_end_timestamp", last.get("ts")))
    if last_end is not None:
        return last_end
    last_start = _parse_datetime(last.get("bar_start_timestamp", last.get("ts")))
    if last_start is not None:
        return last_start + timedelta(minutes=1)
    return None


def _history_hash(bars: tuple[_ValidatedHistoryBar, ...] | list[_ValidatedHistoryBar]) -> str:
    payload = [
        {
            "symbol": bar.symbol,
            "session_date": bar.session_date,
            "timeframe": bar.timeframe,
            "bar_start_timestamp": bar.bar_start_timestamp,
            "bar_end_timestamp": bar.bar_end_timestamp,
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
            "causal_vwap": bar.causal_vwap,
            "volume_provenance": bar.volume_provenance,
        }
        for bar in bars
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _completed_history_provenance(
    ctx: StrategyContext,
    sequence: _CausalSequenceResult,
) -> dict[str, Any]:
    provenance = dict((ctx.metadata or {}).get("completed_bar_history_provenance") or {})
    final_bar = sequence.history[-1]
    provenance.setdefault("source_component", "strategies.movement.vwap_reclaim")
    provenance.setdefault("source_field", "completed_bar_history")
    provenance.setdefault("source_event_timestamp", final_bar.bar_end_timestamp)
    provenance.setdefault("receipt_timestamp", final_bar.receipt_timestamp or final_bar.bar_end_timestamp)
    provenance.setdefault("scope", "session_completed_bar_history")
    provenance.setdefault("symbol", final_bar.symbol)
    provenance.setdefault("session_date", final_bar.session_date)
    provenance.setdefault("timeframe", final_bar.timeframe)
    provenance.setdefault("completed_bar_count", len(sequence.history))
    provenance.setdefault("latest_completed_timestamp", final_bar.bar_end_timestamp)
    provenance.setdefault("history_hash", sequence.history_hash)
    provenance["status"] = sequence.vwap_provenance
    provenance["complete"] = True
    return provenance


def _emit_history_blocked(
    *,
    reason: str,
    missing_fields: tuple[str, ...] = (),
    invalid_fields: tuple[str, ...] = (),
) -> None:
    from strategies.movement._utils import emit_strategy_evidence_blocked

    emit_strategy_evidence_blocked(
        STRATEGY_ID,
        reason=reason,
        missing_fields=missing_fields,
        invalid_fields=invalid_fields,
    )


def _vwap_slope_alignment_score(ctx: StrategyContext, direction: str) -> float:
    slope = safe_float(ctx.vwap_slope)
    if slope is None:
        return 0.0
    if direction == "BUY_CALL" and slope >= 0:
        return clamp_score(0.5 + ratio_score(abs(slope), start=0.0, full=0.08) * 0.5)
    if direction == "BUY_PUT" and slope <= 0:
        return clamp_score(0.5 + ratio_score(abs(slope), start=0.0, full=0.08) * 0.5)
    return 0.15


def _metadata_float(ctx: StrategyContext, key: str) -> float | None:
    value: Any = (ctx.metadata or {}).get(key)
    return safe_float(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, "", "None"):
        return None
    try:
        if isinstance(value, datetime):
            out = value
        elif isinstance(value, (int, float)):
            out = datetime.fromtimestamp(float(value), tz=IST)
        else:
            out = datetime.fromisoformat(str(value))
    except Exception:
        return None
    if out.tzinfo is None:
        out = out.replace(tzinfo=IST)
    return out.astimezone(IST)


def _parse_numeric(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return float(out)


def _parse_positive_float(value: Any) -> float | None:
    parsed = _parse_numeric(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


__all__ = ["STRATEGY_ID", "MOVEMENT_TYPE", "generate_vwap_reclaim_rejection_candidates"]
