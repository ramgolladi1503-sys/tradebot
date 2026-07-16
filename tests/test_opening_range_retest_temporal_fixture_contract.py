from __future__ import annotations

import logging
import hashlib
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.session_bar_history import SessionBarHistoryError, build_session_bar_history_state
from core.strategy_temporal_harness import TemporalSetupConformanceCase, run_temporal_setup_conformance
from strategies.movement.opening_drive import generate_opening_drive_candidates
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates


IST = ZoneInfo("Asia/Kolkata")
SESSION_DATE = "2026-07-14"
SESSION_OPEN = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
STRATEGY_ID = "opening_range_retest_v1"
SYMBOL = "NIFTY"
SEGMENT = "NSE_FNO"
OPENING_RANGE_HIGH = 22600.0
OPENING_RANGE_LOW = 22500.0


def _bar(offset_minutes: int, open_: float, high: float, low: float, close: float, *, volume: float = 1000.0) -> dict[str, object]:
    start = SESSION_OPEN + timedelta(minutes=offset_minutes)
    end = start + timedelta(minutes=1)
    return {
        "symbol": SYMBOL,
        "session_date": SESSION_DATE,
        "timeframe": "1m",
        "bar_start_timestamp": start.isoformat(),
        "bar_end_timestamp": end.isoformat(),
        "ts": start.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "source": "unit_test",
        "source_timestamp": end.isoformat(),
        "receipt_timestamp": (end + timedelta(seconds=1)).isoformat(),
        "is_complete": True,
    }


OPENING_RANGE_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (0, 22540.0, 22558.0, 22532.0, 22550.0),
    (1, 22549.0, 22560.0, 22535.0, 22545.0),
    (2, 22544.0, 22550.0, 22518.0, 22528.0),
    (3, 22527.0, 22540.0, 22510.0, 22518.0),
    (4, 22517.0, 22530.0, 22505.0, 22512.0),
    (5, 22511.0, 22524.0, 22502.0, 22515.0),
    (6, 22515.0, 22528.0, 22503.0, 22520.0),
    (7, 22520.0, 22526.0, 22500.0, 22508.0),
    (8, 22508.0, 22522.0, 22504.0, 22518.0),
    (9, 22518.0, 22535.0, 22510.0, 22529.0),
    (10, 22529.0, 22542.0, 22520.0, 22536.0),
    (11, 22536.0, 22548.0, 22524.0, 22540.0),
    (12, 22540.0, 22552.0, 22530.0, 22544.0),
    (13, 22544.0, 22560.0, 22538.0, 22552.0),
    (14, 22552.0, OPENING_RANGE_HIGH, 22540.0, 22556.0),  # 09:29 opening-range completion
)

CALL_VALID_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22612.0, 22554.0, 22608.0),  # 09:30 breakout
    (16, 22608.0, 22609.0, 22596.0, 22600.0),  # 09:31 hold only
    (17, 22600.0, 22611.0, 22598.0, 22603.0),  # 09:32 retest
    (18, 22603.0, 22618.0, 22601.0, 22614.0),  # 09:33 continuation
    (19, 22614.0, 22620.0, 22607.0, 22612.0),  # later future bar
)

PUT_VALID_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22558.0, 22488.0, 22492.0),  # 09:30 breakout
    (16, 22492.0, 22494.0, 22486.0, 22490.0),  # 09:31 hold only
    (17, 22490.0, 22502.0, 22488.0, 22498.0),  # 09:32 retest
    (18, 22498.0, 22499.0, 22482.0, 22484.0),  # 09:33 continuation
    (19, 22488.0, 22490.0, 22474.0, 22478.0),  # later future bar
)

CALL_WICK_ONLY_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22596.0, 22611.0, 22550.0, 22598.0),  # high breaks ORB, close does not
)

PUT_WICK_ONLY_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22502.0, 22518.0, 22488.0, 22502.0),  # low breaks ORB, close does not
)

CALL_EQUALITY_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, OPENING_RANGE_HIGH, 22554.0, OPENING_RANGE_HIGH),  # equality is not a breakout
)

PUT_EQUALITY_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22558.0, OPENING_RANGE_LOW, OPENING_RANGE_LOW),  # equality is not a breakout
)

CALL_EQUALITY_THEN_VALID_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, OPENING_RANGE_HIGH, 22554.0, OPENING_RANGE_HIGH),  # equality does not invalidate
    (16, 22600.0, 22612.0, 22596.0, 22608.0),
    (17, 22608.0, 22609.0, 22598.0, 22600.0),
    (18, 22600.0, 22611.0, 22598.0, 22603.0),
    (19, 22603.0, 22618.0, 22601.0, 22614.0),
)

PUT_EQUALITY_THEN_VALID_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22558.0, OPENING_RANGE_LOW, OPENING_RANGE_LOW),  # equality does not invalidate
    (16, 22498.0, 22502.0, 22486.0, 22490.0),
    (17, 22490.0, 22494.0, 22482.0, 22488.0),
    (18, 22488.0, 22499.0, 22484.0, 22492.0),
    (19, 22492.0, 22495.0, 22474.0, 22478.0),
)

CALL_SAME_BAR_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22612.0, 22550.0, 22608.0),  # breakout and retest collapse into one bar
)

PUT_SAME_BAR_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22500.0, 22506.0, 22488.0, 22501.0),  # breakout and retest collapse into one bar
)

CALL_AGE_5_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22612.0, 22554.0, 22608.0),  # breakout age 0
    (16, 22608.0, 22609.0, 22598.0, 22600.0),
    (17, 22600.0, 22603.0, 22596.0, 22601.0),
    (18, 22601.0, 22604.0, 22599.0, 22602.0),
    (19, 22602.0, 22605.0, 22598.0, 22603.0),
    (20, 22603.0, 22611.0, 22598.0, 22604.0),  # retest age 5
    (21, 22604.0, 22618.0, 22601.0, 22613.0),  # continuation after retest
)

CALL_AGE_6_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22612.0, 22554.0, 22608.0),  # breakout age 0
    (16, 22608.0, 22609.0, 22598.0, 22600.0),
    (17, 22600.0, 22603.0, 22596.0, 22601.0),
    (18, 22601.0, 22604.0, 22599.0, 22602.0),
    (19, 22602.0, 22605.0, 22598.0, 22603.0),
    (20, 22603.0, 22604.0, 22599.0, 22602.0),
    (21, 22602.0, 22611.0, 22598.0, 22604.0),  # retest age 6
    (22, 22604.0, 22618.0, 22601.0, 22613.0),  # continuation after expiry
)

CALL_CONTINUATION_AGE_3_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22612.0, 22554.0, 22608.0),
    (16, 22608.0, 22609.0, 22598.0, 22600.0),
    (17, 22600.0, 22603.0, 22596.0, 22601.0),
    (18, 22601.0, 22604.0, 22599.0, 22602.0),
    (19, 22602.0, 22605.0, 22598.0, 22603.0),
    (20, 22603.0, 22611.0, 22598.0, 22604.0),  # retest age 0
    (21, 22604.0, 22606.0, 22600.0, 22605.0),
    (22, 22605.0, 22608.0, 22601.0, 22607.0),
    (23, 22607.0, 22618.0, 22601.0, 22613.0),  # continuation age 3
    (24, 22613.0, 22614.0, 22605.0, 22610.0),  # age 4 expiry boundary
)

CALL_INVALIDATION_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22612.0, 22554.0, 22608.0),  # breakout age 0
    (16, 22608.0, 22609.0, 22598.0, 22601.0),  # retest age 1
    (17, 22601.0, 22602.0, 22592.0, 22595.0),  # invalidation close back inside ORB
    (18, 22595.0, 22605.0, 22593.0, 22603.0),  # later bar that would otherwise revive
)

CALL_SESSION_END_BREAKOUT_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22612.0, 22554.0, 22608.0),  # breakout only, session ends before retest
)

CALL_SESSION_END_RETEST_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22612.0, 22554.0, 22608.0),
    (16, 22608.0, 22609.0, 22598.0, 22603.0),  # retest only, session ends before continuation
)

CALL_SESSION_END_NO_BREAKOUT_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (15, 22556.0, 22582.0, 22544.0, 22558.0),  # still below ORB high
)

FUTURE_BAR_ROWS: tuple[tuple[int, float, float, float, float], ...] = (
    (20, 22614.0, 22620.0, 22607.0, 22612.0),
    (21, 22612.0, 22615.0, 22600.0, 22606.0),
)


def _bars(rows: tuple[tuple[int, float, float, float, float], ...]) -> tuple[dict[str, object], ...]:
    return tuple(_bar(*row) for row in rows)


def _opening_range_bars() -> tuple[dict[str, object], ...]:
    return _bars(OPENING_RANGE_ROWS)


def _trend_pullback_history_bars() -> tuple[dict[str, object], ...]:
    return _bars(
        (
            (0, 22585.0, 22595.0, 22575.0, 22590.0),
            (1, 22625.0, 22635.0, 22615.0, 22630.0),
            (2, 22610.0, 22620.0, 22605.0, 22615.0),
            (3, 22630.0, 22640.0, 22625.0, 22635.0),
        )
    )


def _history_hash(
    rows: tuple[tuple[int, float, float, float, float], ...],
    *,
    cutoff_index: int | None = None,
) -> str:
    causal_rows = rows if cutoff_index is None else rows[:cutoff_index]
    payload = [
        {
            "timestamp_iso_ist": _bar(row[0], row[1], row[2], row[3], row[4])["ts"],
            "open": row[1],
            "high": row[2],
            "low": row[3],
            "close": row[4],
        }
        for row in causal_rows
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _setup_id(
    *,
    direction: str,
    boundary_type: str,
    normalized_boundary_value: float,
    breakout_timestamp: str,
) -> str:
    payload = {
        "strategy_id": STRATEGY_ID,
        "symbol": SYMBOL,
        "session_date": SESSION_DATE,
        "direction": direction,
        "boundary_type": boundary_type,
        "normalized_boundary_value": normalized_boundary_value,
        "breakout_timestamp": breakout_timestamp,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def _regime(*, up: float = 0.8, down: float = 0.0) -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP" if up >= down else "TREND_DOWN",
        scores={
            "TREND_UP": up,
            "TREND_DOWN": down,
            "RANGE": 0.0,
            "CHOP": 0.0,
            "COMPRESSION": 0.0,
            "VOLATILITY_EXPANSION": 0.45,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.0,
        },
    )


def _current_snapshot_context(**overrides: object) -> StrategyContext:
    payload = {
        "symbol": SYMBOL,
        "ts_epoch": 1721028600.0,
        "spot_ltp": 22608.0,
        "open_price": 22500.0,
        "vwap": 22550.0,
        "orb_high": 22600.0,
        "orb_low": 22460.0,
        "minutes_since_open": 35,
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
        "ce_premium_change": 12.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def _temporal_context(state, **overrides: object) -> StrategyContext:
    latest = state.completed_bar_history[-1]
    closes = [bar.close for bar in state.completed_bar_history]
    orb_high = max(bar.high for bar in state.completed_bar_history[:15]) if state.completed_bar_count >= 15 else None
    orb_low = min(bar.low for bar in state.completed_bar_history[:15]) if state.completed_bar_count >= 15 else None
    payload = {
        "symbol": state.symbol,
        "ts_epoch": datetime.fromisoformat(latest.bar_end_timestamp).timestamp(),
        "spot_ltp": latest.close,
        "open_price": state.open_price,
        "day_high": state.day_high,
        "day_low": state.day_low,
        "previous_completed_close": state.previous_completed_close,
        "vwap": sum(closes) / len(closes),
        "orb_high": orb_high,
        "orb_low": orb_low,
        "minutes_since_open": state.completed_bar_count,
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
        "ce_premium_change": 12.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.8,
        "ce_depth": 1200.0,
        "pe_depth": 1200.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "completed_bar_history": state.history_payload(),
        "metadata": {"prefix_index": state.completed_bar_count, "history_hash": state.history_hash},
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def _history_state_for_rows(
    rows: tuple[tuple[int, float, float, float, float], ...],
    *,
    cutoff_index: int | None = None,
    cutoff_timestamp: str | None = None,
):
    selected_rows = rows if cutoff_index is None else rows[:cutoff_index]
    bars = list(_bars(selected_rows))
    resolved_cutoff = cutoff_timestamp or bars[-1]["bar_end_timestamp"]
    return build_session_bar_history_state(
        symbol=SYMBOL,
        bars=bars,
        cutoff_timestamp=resolved_cutoff,
        segment=SEGMENT,
        source="unit_test",
        timeframe="1m",
    )


def _stable_candidate_payload(candidate) -> dict[str, object]:
    payload = candidate.to_dict()
    payload.pop("generated_epoch", None)
    payload.pop("outcome_contract", None)
    return payload


def _first_emitting_candidate(
    *,
    case_id: str,
    rows: tuple[tuple[int, float, float, float, float], ...],
    regime_builder,
):
    trace = _trace(case_id=case_id, completed_rows=rows, regime_builder=regime_builder)
    prefix_count = next(step.prefix_bar_count for step in trace.steps if step.candidate_emitted)
    state = _history_state_for_rows(rows, cutoff_index=prefix_count)
    ctx = _temporal_context(state)
    regime = regime_builder(state)
    candidates = generate_opening_range_retest_candidates(ctx, regime)
    assert len(candidates) == 1
    return trace, state, candidates[0]


def _case(
    *,
    case_id: str,
    completed_bars: tuple[dict[str, object], ...],
    evaluator,
    regime_builder,
):
    return TemporalSetupConformanceCase(
        case_id=case_id,
        strategy_id=STRATEGY_ID,
        symbol=SYMBOL,
        segment=SEGMENT,
        session_id=f"{SYMBOL}:{SESSION_DATE}",
        completed_bars=completed_bars,
        context_builder=_temporal_context,
        regime_builder=regime_builder,
        evaluator=evaluator,
    )


def _trace(
    *,
    case_id: str,
    completed_rows: tuple[tuple[int, float, float, float, float], ...],
    regime_builder,
):
    return run_temporal_setup_conformance(
        _case(
            case_id=case_id,
            completed_bars=_bars(completed_rows),
            evaluator=lambda ctx, regime: generate_opening_range_retest_candidates(ctx, regime),
            regime_builder=regime_builder,
        )
    )


def _fingerprint(result: tuple) -> tuple:
    if not result:
        return ()
    candidate = result[0]
    return (
        candidate.strategy_id,
        candidate.direction,
        round(float(candidate.raw_score), 6),
        candidate.entry_trigger,
        candidate.invalid_if,
        candidate.rank_reason,
    )


def _blocked_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.message for record in caplog.records if "event=STRATEGY_EVIDENCE_BLOCKED" in record.message]


def test_fixture_orb_recomputes_from_completed_opening_range() -> None:
    state = build_session_bar_history_state(
        symbol=SYMBOL,
        bars=list(_opening_range_bars()),
        cutoff_timestamp="2026-07-14T09:30:00+05:30",
        segment=SEGMENT,
        source="unit_test",
        timeframe="1m",
    )

    assert state.completed_bar_count == 15
    assert state.open_price == 22540.0
    assert state.day_high == OPENING_RANGE_HIGH
    assert state.day_low == OPENING_RANGE_LOW
    assert state.latest_completed_timestamp == "2026-07-14T09:30:00+05:30"
    assert max(bar.high for bar in state.completed_bar_history) == OPENING_RANGE_HIGH
    assert min(bar.low for bar in state.completed_bar_history) == OPENING_RANGE_LOW


def test_canonical_setup_identity_and_history_hash_helper_are_deterministic_for_identical_causal_inputs() -> None:
    causal_rows = OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4]
    future_rows = causal_rows + FUTURE_BAR_ROWS
    another_future = causal_rows + (
        (20, 22618.0, 22624.0, 22608.0, 22620.0),
        (21, 22620.0, 22628.0, 22612.0, 22624.0),
    )

    identity_a = _setup_id(
        direction="BUY_CALL",
        boundary_type="ORB_HIGH",
        normalized_boundary_value=OPENING_RANGE_HIGH,
        breakout_timestamp="2026-07-14T09:30:00+05:30",
    )
    identity_b = _setup_id(
        direction="BUY_CALL",
        boundary_type="ORB_HIGH",
        normalized_boundary_value=OPENING_RANGE_HIGH,
        breakout_timestamp="2026-07-14T09:30:00+05:30",
    )
    identity_c = _setup_id(
        direction="BUY_CALL",
        boundary_type="ORB_LOW",
        normalized_boundary_value=OPENING_RANGE_LOW,
        breakout_timestamp="2026-07-14T09:30:00+05:30",
    )

    assert identity_a == identity_b
    assert identity_a != identity_c
    assert _setup_id(
        direction="BUY_CALL",
        boundary_type="ORB_HIGH",
        normalized_boundary_value=OPENING_RANGE_HIGH,
        breakout_timestamp="2026-07-14T09:30:00+05:30",
    ) == identity_a
    assert _setup_id(
        direction="BUY_PUT",
        boundary_type="ORB_HIGH",
        normalized_boundary_value=OPENING_RANGE_HIGH,
        breakout_timestamp="2026-07-14T09:30:00+05:30",
    ) != identity_a
    assert _setup_id(
        direction="BUY_CALL",
        boundary_type="ORB_HIGH",
        normalized_boundary_value=OPENING_RANGE_HIGH + 1.0,
        breakout_timestamp="2026-07-14T09:30:00+05:30",
    ) != identity_a
    assert _setup_id(
        direction="BUY_CALL",
        boundary_type="ORB_HIGH",
        normalized_boundary_value=OPENING_RANGE_HIGH,
        breakout_timestamp="2026-07-14T09:31:00+05:30",
    ) != identity_a
    assert _setup_id(
        direction="BUY_CALL",
        boundary_type="ORB_HIGH",
        normalized_boundary_value=OPENING_RANGE_HIGH,
        breakout_timestamp="2026-07-14T09:30:00+05:30",
    ) == _setup_id(
        direction="BUY_CALL",
        boundary_type="ORB_HIGH",
        normalized_boundary_value=OPENING_RANGE_HIGH,
        breakout_timestamp="2026-07-14T09:30:00+05:30",
    )
    assert _history_hash(causal_rows, cutoff_index=len(causal_rows)) == _history_hash(
        future_rows,
        cutoff_index=len(causal_rows),
    )
    assert _history_hash(causal_rows, cutoff_index=len(causal_rows)) == _history_hash(
        another_future,
        cutoff_index=len(causal_rows),
    )

    timestamp_mutated = tuple(((index + 0.5) if index == 10 else index, open_, high, low, close) for index, open_, high, low, close in causal_rows)
    open_mutated = tuple((index, open_ + (1.0 if index == 10 else 0.0), high, low, close) for index, open_, high, low, close in causal_rows)
    high_mutated = tuple((index, open_, high + (1.0 if index == 10 else 0.0), low, close) for index, open_, high, low, close in causal_rows)
    low_mutated = tuple((index, open_, high, low + (1.0 if index == 10 else 0.0), close) for index, open_, high, low, close in causal_rows)
    close_mutated = tuple((index, open_, high, low, close + (1.0 if index == 10 else 0.0)) for index, open_, high, low, close in causal_rows)
    assert _history_hash(causal_rows, cutoff_index=len(causal_rows)) != _history_hash(timestamp_mutated, cutoff_index=len(causal_rows))
    assert _history_hash(causal_rows, cutoff_index=len(causal_rows)) != _history_hash(open_mutated, cutoff_index=len(causal_rows))
    assert _history_hash(causal_rows, cutoff_index=len(causal_rows)) != _history_hash(high_mutated, cutoff_index=len(causal_rows))
    assert _history_hash(causal_rows, cutoff_index=len(causal_rows)) != _history_hash(low_mutated, cutoff_index=len(causal_rows))
    assert _history_hash(causal_rows, cutoff_index=len(causal_rows)) != _history_hash(close_mutated, cutoff_index=len(causal_rows))


def test_missing_completed_history_fails_closed_without_snapshot_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        result = generate_opening_range_retest_candidates(_current_snapshot_context(), _regime())

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=opening_range_retest_v1 missing_fields=completed_bar_history invalid_fields=- reason=missing_required_temporal_evidence"
    ]


def test_unrelated_strategy_controls_remain_stable() -> None:
    opening_drive = generate_opening_drive_candidates(_current_snapshot_context(minutes_since_open=8), _regime(up=0.8))
    trend_pullback = generate_trend_pullback_candidates(
        StrategyContext(
            symbol=SYMBOL,
            ts_epoch=1721028600.0,
            spot_ltp=22620.0,
            open_price=22500.0,
            vwap=22540.0,
            day_high=22620.0,
            day_low=22460.0,
            nearest_support=22590.0,
            nearest_resistance=22600.0,
            range_width_pct=0.14,
            atr=70.0,
            volume_z=1.5,
            vwap_slope=0.03,
            option_ce_ltp=120.0,
            option_pe_ltp=90.0,
            ce_premium_change=12.0,
            pe_premium_change=0.0,
            ce_spread_pct=0.8,
            pe_spread_pct=0.8,
            ce_depth=1200.0,
            pe_depth=1200.0,
            option_ltp_age_sec=0.4,
            quote_source="live_option_tick",
            fallback_used=False,
            minutes_since_open=35,
            minutes_to_close=280,
            completed_bar_history=_trend_pullback_history_bars(),
        ),
        _regime(up=0.72),
    )

    assert len(opening_drive) == 1
    assert opening_drive[0].strategy_id == "opening_drive_v1"
    assert len(trend_pullback) == 1
    assert trend_pullback[0].strategy_id == "trend_pullback_v1"


@pytest.mark.parametrize(
    ("case_id", "rows", "regime_builder", "expected_first_emission"),
    [
        (
            "call_valid_sequence",
            OPENING_RANGE_ROWS + CALL_VALID_ROWS,
            lambda _state: _regime(up=0.8, down=0.0),
            "2026-07-14T09:34:00+05:30",
        ),
        (
            "put_valid_sequence",
            OPENING_RANGE_ROWS + PUT_VALID_ROWS,
            lambda _state: _regime(up=0.0, down=0.8),
            "2026-07-14T09:34:00+05:30",
        ),
    ],
)
def test_valid_sequences_emit_only_after_later_continuation(
    case_id: str,
    rows: tuple[tuple[int, float, float, float, float], ...],
    regime_builder,
    expected_first_emission: str,
) -> None:
    trace = _trace(case_id=case_id, completed_rows=rows, regime_builder=regime_builder)

    assert trace.emission_count == 1
    assert trace.first_emission_checkpoint == expected_first_emission
    assert trace.steps[14].candidate_emitted is False  # 09:29 opening-range completion
    assert trace.steps[15].candidate_emitted is False  # breakout alone
    assert trace.steps[16].candidate_emitted is False  # hold bar
    assert trace.steps[17].candidate_emitted is False  # retest alone
    assert trace.steps[18].candidate_emitted is True   # later continuation


@pytest.mark.parametrize(
    ("case_id", "rows", "regime_builder", "boundary_type", "normalized_boundary_value", "future_rows"),
    [
        (
            "call_future_mutation",
            OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4],
            lambda _state: _regime(up=0.8, down=0.0),
            "ORB_HIGH",
            OPENING_RANGE_HIGH,
            (
                (19, 22614.0, 22720.0, 22590.0, 22698.0),
                (20, 22698.0, 22740.0, 22640.0, 22722.0),
            ),
        ),
        (
            "put_future_mutation",
            OPENING_RANGE_ROWS + PUT_VALID_ROWS[:4],
            lambda _state: _regime(up=0.0, down=0.8),
            "ORB_LOW",
            OPENING_RANGE_LOW,
            (
                (19, 22488.0, 22510.0, 22382.0, 22392.0),
                (20, 22392.0, 22402.0, 22350.0, 22376.0),
            ),
        ),
    ],
)
def test_future_mutation_and_physical_truncation_preserve_candidate_payload_and_history_hash(
    case_id: str,
    rows: tuple[tuple[int, float, float, float, float], ...],
    regime_builder,
    boundary_type: str,
    normalized_boundary_value: float,
    future_rows: tuple[tuple[int, float, float, float, float], ...],
) -> None:
    truncated_trace, truncated_state, truncated_candidate = _first_emitting_candidate(
        case_id=case_id,
        rows=rows,
        regime_builder=regime_builder,
    )
    extended_rows = rows + future_rows
    extended_trace, extended_state, extended_candidate = _first_emitting_candidate(
        case_id=f"{case_id}_extended",
        rows=extended_rows,
        regime_builder=regime_builder,
    )

    assert truncated_trace.first_emission_checkpoint == extended_trace.first_emission_checkpoint
    assert truncated_state.history_hash == extended_state.history_hash
    assert truncated_candidate.evidence["setup_identity"]["proposal_ready_at_iso"] == "2026-07-14T09:34:00+05:30"
    assert extended_candidate.evidence["setup_identity"]["proposal_ready_at_iso"] == "2026-07-14T09:34:00+05:30"
    assert truncated_candidate.evidence["setup_identity"]["setup_id"] == extended_candidate.evidence["setup_identity"]["setup_id"]
    assert truncated_candidate.evidence["setup_identity"]["history_hash"] == extended_candidate.evidence["setup_identity"]["history_hash"]
    assert _stable_candidate_payload(truncated_candidate) == _stable_candidate_payload(extended_candidate)
    assert truncated_candidate.raw_score == pytest.approx(extended_candidate.raw_score)
    assert truncated_candidate.confidence_score == pytest.approx(extended_candidate.confidence_score)
    assert _setup_id(
        direction=truncated_candidate.direction,
        boundary_type=boundary_type,
        normalized_boundary_value=normalized_boundary_value,
        breakout_timestamp=truncated_trace.first_emission_checkpoint or "",
    ) == _setup_id(
        direction=extended_candidate.direction,
        boundary_type=boundary_type,
        normalized_boundary_value=normalized_boundary_value,
        breakout_timestamp=extended_trace.first_emission_checkpoint or "",
    )

@pytest.mark.parametrize(
    ("case_id", "ctx_overrides", "expected_has_candidate", "expected_raw_score"),
    [
        ("orb_match", {}, True, 0.451504),
        ("orb_absent", {"orb_high": None, "orb_low": None}, True, 0.451504),
        ("orb_high_mismatch", {"orb_high": OPENING_RANGE_HIGH + 5.0}, False, None),
        ("orb_low_mismatch", {"orb_low": OPENING_RANGE_LOW - 5.0}, False, None),
        (
            "orb_both_mismatch",
            {"orb_high": OPENING_RANGE_HIGH + 5.0, "orb_low": OPENING_RANGE_LOW - 5.0},
            False,
            None,
        ),
    ],
)
def test_orb_reconciliation_matrix_records_current_behavior(
    case_id: str,
    ctx_overrides: dict[str, object],
    expected_has_candidate: bool,
    expected_raw_score: float | None,
) -> None:
    state = _history_state_for_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    ctx = _temporal_context(state, **ctx_overrides)
    result = generate_opening_range_retest_candidates(ctx, _regime())

    if expected_has_candidate:
        assert len(result) == 1
        assert _fingerprint(result) == (
            "opening_range_retest_v1",
            "BUY_CALL",
            expected_raw_score,
            "opening_range_breakout_retest_hold",
            "price_returns_inside_opening_range",
            "opening range breakout retest held",
        )
    else:
        assert result == ()


def test_session_end_matrix_records_no_publication_ready_candidate() -> None:
    no_breakout = _trace(
        case_id="session_end_no_breakout",
        completed_rows=OPENING_RANGE_ROWS + CALL_SESSION_END_NO_BREAKOUT_ROWS,
        regime_builder=lambda _state: _regime(up=0.8, down=0.0),
    )
    breakout_only = _trace(
        case_id="session_end_after_breakout",
        completed_rows=OPENING_RANGE_ROWS + CALL_SESSION_END_BREAKOUT_ROWS,
        regime_builder=lambda _state: _regime(up=0.8, down=0.0),
    )
    retest_only = _trace(
        case_id="session_end_after_retest",
        completed_rows=OPENING_RANGE_ROWS + CALL_SESSION_END_RETEST_ROWS,
        regime_builder=lambda _state: _regime(up=0.8, down=0.0),
    )

    assert no_breakout.emission_count == 0
    assert no_breakout.first_emission_checkpoint is None
    assert no_breakout.steps[-1].candidate_fingerprints == ()
    assert breakout_only.emission_count == 0
    assert breakout_only.first_emission_checkpoint is None
    assert breakout_only.steps[-1].candidate_fingerprints == ()
    assert retest_only.emission_count == 0
    assert retest_only.first_emission_checkpoint is None
    assert retest_only.steps[-1].candidate_fingerprints == ()


def _malformed_history_label(bars: list[dict[str, object]]) -> str:
    try:
        state = build_session_bar_history_state(
            symbol=SYMBOL,
            bars=bars,
            cutoff_timestamp=bars[-1]["bar_end_timestamp"] if bars else "2026-07-14T09:15:00+05:30",
            segment=SEGMENT,
            source="unit_test",
            timeframe="1m",
        )
    except SessionBarHistoryError:
        return "builder rejection"
    if state.completed_bar_count == 0:
        return "no candidate"
    return "expected temporal red because production currently accepts it"


@pytest.mark.parametrize(
    ("case_id", "bars", "expected_label"),
    [
        (
            "mixed_symbol",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), symbol="BANKNIFTY"), _bar(1, 22549.0, 22560.0, 22535.0, 22545.0)],
            "expected temporal red because production currently accepts it",
        ),
        (
            "mixed_session",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), session_date="2026-07-15"), _bar(1, 22549.0, 22560.0, 22535.0, 22545.0)],
            "expected temporal red because production currently accepts it",
        ),
        (
            "out_of_order",
            [_bar(1, 22549.0, 22560.0, 22535.0, 22545.0), _bar(0, 22540.0, 22558.0, 22532.0, 22550.0)],
            "builder rejection",
        ),
        (
            "duplicate",
            [_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), close=22551.0)],
            "builder rejection",
        ),
        (
            "missing_bar",
            [_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), _bar(2, 22544.0, 22550.0, 22518.0, 22528.0)],
            "expected temporal red because production currently accepts it",
        ),
        (
            "cadence_30s",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), bar_end_timestamp="2026-07-14T09:15:30+05:30"), _bar(1, 22549.0, 22560.0, 22535.0, 22545.0)],
            "expected temporal red because production currently accepts it",
        ),
        (
            "nan_ohlc",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), open=float("nan"))],
            "builder rejection",
        ),
        (
            "inf_ohlc",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), high=float("inf"))],
            "builder rejection",
        ),
        (
            "neg_inf_ohlc",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), low=float("-inf"))],
            "builder rejection",
        ),
        (
            "high_below_low",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), high=22520.0, low=22530.0)],
            "builder rejection",
        ),
        (
            "open_outside",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), open=22570.0)],
            "builder rejection",
        ),
        (
            "close_outside",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), close=22570.0)],
            "builder rejection",
        ),
        (
            "incomplete_current",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), is_complete=False)],
            "expected temporal red because production currently accepts it",
        ),
        (
            "pre_session",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), bar_start_timestamp="2026-07-14T09:14:00+05:30", bar_end_timestamp="2026-07-14T09:15:00+05:30", ts="2026-07-14T09:14:00+05:30")],
            "no candidate",
        ),
        (
            "post_session",
            [dict(_bar(0, 22540.0, 22558.0, 22532.0, 22550.0), bar_start_timestamp="2026-07-14T15:30:00+05:30", bar_end_timestamp="2026-07-14T15:31:00+05:30", ts="2026-07-14T15:30:00+05:30")],
            "no candidate",
        ),
    ],
)
def test_malformed_history_controls_record_current_behavior(case_id: str, bars: list[dict[str, object]], expected_label: str) -> None:
    assert _malformed_history_label(bars) == expected_label


@pytest.mark.parametrize(
    ("case_id", "rows", "regime_builder", "expected_first_emission"),
    [
        (
            "call_equality_then_valid",
            OPENING_RANGE_ROWS + CALL_EQUALITY_THEN_VALID_ROWS,
            lambda _state: _regime(up=0.8, down=0.0),
            "2026-07-14T09:35:00+05:30",
        ),
        (
            "put_equality_then_valid",
            OPENING_RANGE_ROWS + PUT_EQUALITY_THEN_VALID_ROWS,
            lambda _state: _regime(up=0.0, down=0.8),
            None,
        ),
    ],
)
def test_equality_does_not_invalidate_and_later_valid_sequence_still_emits(
    case_id: str,
    rows: tuple[tuple[int, float, float, float, float], ...],
    regime_builder,
    expected_first_emission: str,
) -> None:
    trace = _trace(case_id=case_id, completed_rows=rows, regime_builder=regime_builder)

    assert trace.steps[15].candidate_emitted is False
    if expected_first_emission is None:
        assert trace.emission_count == 0
        assert trace.first_emission_checkpoint is None
    else:
        assert trace.emission_count == 1
        assert trace.first_emission_checkpoint == expected_first_emission


@pytest.mark.parametrize(
    ("case_id", "rows", "regime_builder"),
    [
        ("call_wick_only", OPENING_RANGE_ROWS + CALL_WICK_ONLY_ROWS, lambda _state: _regime(up=0.8, down=0.0)),
        ("put_wick_only", OPENING_RANGE_ROWS + PUT_WICK_ONLY_ROWS, lambda _state: _regime(up=0.0, down=0.8)),
        ("call_equality", OPENING_RANGE_ROWS + CALL_EQUALITY_ROWS, lambda _state: _regime(up=0.8, down=0.0)),
        ("put_equality", OPENING_RANGE_ROWS + PUT_EQUALITY_ROWS, lambda _state: _regime(up=0.0, down=0.8)),
    ],
)
def test_wick_only_and_equality_cases_do_not_qualify(case_id: str, rows, regime_builder) -> None:
    trace = _trace(case_id=case_id, completed_rows=rows, regime_builder=regime_builder)

    assert trace.emission_count == 0
    assert trace.first_emission_checkpoint is None
    assert trace.steps[-1].candidate_emitted is False


@pytest.mark.parametrize(
    ("case_id", "rows", "regime_builder"),
    [
        ("call_same_bar", OPENING_RANGE_ROWS + CALL_SAME_BAR_ROWS, lambda _state: _regime(up=0.8, down=0.0)),
        ("put_same_bar", OPENING_RANGE_ROWS + PUT_SAME_BAR_ROWS, lambda _state: _regime(up=0.0, down=0.8)),
    ],
)
def test_same_bar_breakout_and_retest_do_not_qualify(case_id: str, rows, regime_builder) -> None:
    trace = _trace(case_id=case_id, completed_rows=rows, regime_builder=regime_builder)

    assert trace.emission_count == 0
    assert trace.first_emission_checkpoint is None
    assert trace.steps[15].candidate_emitted is False


@pytest.mark.parametrize(
    ("case_id", "rows", "regime_builder", "expected_first_emission"),
    [
        (
            "call_age_5",
            OPENING_RANGE_ROWS + CALL_AGE_5_ROWS,
            lambda _state: _regime(up=0.8, down=0.0),
            None,
        ),
        (
            "call_age_6",
            OPENING_RANGE_ROWS + CALL_AGE_6_ROWS,
            lambda _state: _regime(up=0.8, down=0.0),
            "2026-07-14T09:38:00+05:30",
        ),
    ],
)
def test_breakout_to_retest_age_boundary(case_id: str, rows, regime_builder, expected_first_emission: str | None) -> None:
    trace = _trace(case_id=case_id, completed_rows=rows, regime_builder=regime_builder)

    assert trace.steps[15].candidate_emitted is False
    assert trace.steps[20].candidate_emitted is False
    if expected_first_emission is None:
        assert trace.emission_count == 0
        assert trace.first_emission_checkpoint is None
    else:
        assert trace.emission_count == 1
        assert trace.first_emission_checkpoint == expected_first_emission
        assert trace.steps[22].candidate_emitted is True


@pytest.mark.parametrize(
    ("case_id", "rows", "regime_builder", "expected_first_emission"),
    [
        (
            "call_continuation_age_3",
            OPENING_RANGE_ROWS + CALL_CONTINUATION_AGE_3_ROWS,
            lambda _state: _regime(up=0.8, down=0.0),
            "2026-07-14T09:38:00+05:30",
        ),
    ],
)
def test_retest_to_continuation_age_boundary(case_id: str, rows, regime_builder, expected_first_emission: str) -> None:
    trace = _trace(case_id=case_id, completed_rows=rows, regime_builder=regime_builder)

    assert trace.steps[20].candidate_emitted is False
    assert trace.steps[22].candidate_emitted is True
    assert trace.emission_count == 1
    assert trace.first_emission_checkpoint == expected_first_emission


def test_invalidation_requires_fresh_setup_identity_and_stops_revival(caplog: pytest.LogCaptureFixture) -> None:
    trace = _trace(
        case_id="call_invalidation",
        completed_rows=OPENING_RANGE_ROWS + CALL_INVALIDATION_ROWS,
        regime_builder=lambda _state: _regime(up=0.8, down=0.0),
    )

    assert trace.steps[15].candidate_emitted is False
    assert trace.steps[16].candidate_emitted is False
    assert trace.steps[17].candidate_emitted is False
    assert trace.steps[18].candidate_emitted is False
    assert trace.steps[-1].candidate_fingerprints == ()

    caplog.clear()
    with caplog.at_level("WARNING"):
        result = generate_opening_range_retest_candidates(
            _current_snapshot_context(completed_bar_history=_opening_range_bars(), orb_low=22500.0),
            _regime(),
        )
    assert result == ()
    assert _blocked_messages(caplog) == []


def test_no_pre_breakout_lineage_and_session_end_behaviour(caplog: pytest.LogCaptureFixture) -> None:
    no_breakout = _trace(
        case_id="no_breakout",
        completed_rows=OPENING_RANGE_ROWS + CALL_SESSION_END_NO_BREAKOUT_ROWS,
        regime_builder=lambda _state: _regime(up=0.8, down=0.0),
    )
    breakout_only = _trace(
        case_id="session_end_breakout_only",
        completed_rows=OPENING_RANGE_ROWS + CALL_SESSION_END_BREAKOUT_ROWS,
        regime_builder=lambda _state: _regime(up=0.8, down=0.0),
    )
    retest_only = _trace(
        case_id="session_end_retest_only",
        completed_rows=OPENING_RANGE_ROWS + CALL_SESSION_END_RETEST_ROWS,
        regime_builder=lambda _state: _regime(up=0.8, down=0.0),
    )

    assert no_breakout.emission_count == 0
    assert no_breakout.steps[-1].candidate_emitted is False
    assert breakout_only.steps[-1].candidate_emitted is False
    assert retest_only.steps[-1].candidate_emitted is False

    caplog.clear()
    with caplog.at_level("WARNING"):
        result = generate_opening_range_retest_candidates(_current_snapshot_context(), _regime())
    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=opening_range_retest_v1 missing_fields=completed_bar_history invalid_fields=- reason=missing_required_temporal_evidence"
    ]


def test_orb_mismatch_is_blocked_and_supplied_orb_never_overrides_completed_history(caplog: pytest.LogCaptureFixture) -> None:
    trace = _trace(
        case_id="orb_mismatch",
        completed_rows=OPENING_RANGE_ROWS + CALL_VALID_ROWS,
        regime_builder=lambda _state: _regime(up=0.8, down=0.0),
    )

    assert trace.emission_count == 1
    assert trace.first_emission_checkpoint == "2026-07-14T09:34:00+05:30"
    assert trace.steps[15].candidate_fingerprints == ()
    assert trace.steps[18].candidate_emitted is True

    caplog.clear()
    with caplog.at_level("WARNING"):
        result = generate_opening_range_retest_candidates(
            _current_snapshot_context(
                completed_bar_history=_opening_range_bars() + _bars(CALL_VALID_ROWS[:4]),
                orb_high=OPENING_RANGE_HIGH + 5.0,
                orb_low=OPENING_RANGE_LOW - 5.0,
            ),
            _regime(),
        )
    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=opening_range_retest_v1 missing_fields=- invalid_fields=orb_high,orb_low reason=invalid_orb_reconciliation"
    ]


def test_malformed_history_controls_fail_closed_before_strategy_execution() -> None:
    with pytest.raises(SessionBarHistoryError):
        build_session_bar_history_state(
            symbol=SYMBOL,
            bars=[
                _bar(0, 22540.0, 22558.0, 22532.0, 22550.0),
                _bar(1, 22549.0, 22560.0, 22535.0, 22545.0),
                _bar(1, 22545.0, 22558.0, 22534.0, 22544.0),
            ],
            cutoff_timestamp="2026-07-14T09:18:00+05:30",
            segment=SEGMENT,
            source="unit_test",
            timeframe="1m",
        )

    with pytest.raises(SessionBarHistoryError):
        build_session_bar_history_state(
            symbol=SYMBOL,
            bars=[
                {
                    **_bar(0, 22540.0, 22558.0, 22532.0, 22550.0),
                    "high": 22520.0,
                    "low": 22530.0,
                },
                _bar(1, 22549.0, 22560.0, 22535.0, 22545.0),
            ],
            cutoff_timestamp="2026-07-14T09:18:00+05:30",
            segment=SEGMENT,
            source="unit_test",
            timeframe="1m",
        )
