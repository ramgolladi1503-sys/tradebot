from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.strategy_temporal_harness import TemporalSetupConformanceCase, run_temporal_setup_conformance
from strategies.movement.opening_drive import generate_opening_drive_candidates
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates
from strategies.strategy_registry import load_strategy_registry


IST = ZoneInfo("Asia/Kolkata")

BASE_RAW_SCORE = 0.45150442477876107
BASE_FINGERPRINT = (
    1,
    "opening_range_retest_v1",
    "BUY_CALL",
    BASE_RAW_SCORE,
    "opening_range_breakout_retest_hold",
    "price_returns_inside_opening_range",
    "opening range breakout retest held",
    None,
)


def _bars(
    closes: tuple[float, ...],
    *,
    session_date: str = "2026-07-14",
    symbol: str = "NIFTY",
    timeframe: str = "1m",
    minute_step: int = 1,
) -> list[dict[str, object]]:
    start = datetime.fromisoformat(f"{session_date}T09:15:00+05:30")
    bars: list[dict[str, object]] = []
    for index, close in enumerate(closes):
        bar_start = start + timedelta(minutes=index * minute_step)
        bar_end = bar_start + timedelta(minutes=1)
        bars.append(
            {
                "symbol": symbol,
                "session_date": session_date,
                "timeframe": timeframe,
                "bar_start_timestamp": bar_start.isoformat(),
                "bar_end_timestamp": bar_end.isoformat(),
                "ts": bar_start.isoformat(),
                "open": close - 5.0,
                "high": close + 10.0,
                "low": close - 10.0,
                "close": close,
                "volume": 1000.0 + (index * 100.0),
                "source": "unit_test",
                "source_timestamp": bar_end.isoformat(),
                "receipt_timestamp": (bar_end + timedelta(seconds=1)).isoformat(),
                "is_complete": True,
            }
        )
    return bars


def _regime(*, up: float = 0.0, down: float = 0.0) -> MovementRegimeResult:
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


def _snapshot_context(**overrides: object) -> StrategyContext:
    payload = {
        "symbol": "NIFTY",
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


def _summary(result: tuple) -> tuple:
    assert len(result) in {0, 1}
    if not result:
        return ()
    candidate = result[0]
    return (
        len(result),
        candidate.strategy_id,
        candidate.direction,
        candidate.raw_score,
        candidate.entry_trigger,
        candidate.invalid_if,
        candidate.rank_reason,
        candidate.evidence.get("setup_identity") if isinstance(candidate.evidence, dict) else None,
    )


def _harness_case(
    *,
    case_id: str,
    completed_bars: tuple[dict[str, object], ...],
    context_builder,
):
    return TemporalSetupConformanceCase(
        case_id=case_id,
        strategy_id="opening_range_retest_v1",
        symbol="NIFTY",
        segment="NSE_FNO",
        session_id="NIFTY:2026-07-14",
        completed_bars=completed_bars,
        context_builder=context_builder,
        regime_builder=lambda _state: _regime(),
        evaluator=lambda ctx, regime: generate_opening_range_retest_candidates(ctx, regime),
    )


def _fixed_prefix_context(state) -> StrategyContext:
    return _snapshot_context(
        completed_bar_history=state.history_payload(),
        metadata={"prefix_index": state.completed_bar_count, "history_hash": state.history_hash},
    )


def _gate_then_fixed_context(state) -> StrategyContext:
    return _snapshot_context(
        minutes_since_open=8 if state.completed_bar_count < 3 else 35,
        completed_bar_history=state.history_payload(),
        metadata={"prefix_index": state.completed_bar_count, "history_hash": state.history_hash},
    )


def _evolving_favorable_context(state) -> StrategyContext:
    return _snapshot_context(
        open_price=22500.0 + state.completed_bar_count,
        day_high=22620.0 + state.completed_bar_count,
        day_low=22460.0 - state.completed_bar_count,
        completed_bar_history=state.history_payload(),
        metadata={"prefix_index": state.completed_bar_count, "history_hash": state.history_hash},
    )


def _call_snapshot(**overrides: object) -> tuple:
    return _summary(generate_opening_range_retest_candidates(_snapshot_context(**overrides), _regime()))


def _repeat_trace(*, context_builder, completed_bars: tuple[dict[str, object], ...], case_id: str):
    return run_temporal_setup_conformance(
        _harness_case(
            case_id=case_id,
            completed_bars=completed_bars,
            context_builder=context_builder,
        )
    )


def test_opening_range_retest_is_wired_to_the_real_production_callable() -> None:
    registry = load_strategy_registry()
    entry = registry["OPENING_RANGE_BREAKOUT"]

    assert entry.runtime_strategy_id == "opening_range_retest_v1"
    assert entry.callable_name == "generate_opening_range_retest_candidates"
    assert entry.module_path == "strategies/movement/opening_range_breakout.py"
    assert generate_opening_range_retest_candidates.__module__ == "strategies.movement.opening_range_breakout"


@pytest.mark.parametrize(
    ("case_name", "history"),
    [
        ("absent", None),
        ("empty", []),
        ("one_valid", _bars((22590.0,))),
        ("multiple_valid", _bars((22590.0, 22630.0, 22615.0, 22635.0))),
        ("different_order", list(reversed(_bars((22590.0, 22630.0, 22615.0, 22635.0))))),
        ("different_values", _bars((22490.0, 22520.0, 22580.0, 22640.0))),
        (
            "mixed_session",
            [
                *_bars((22590.0, 22630.0, 22615.0)),
                {
                    **_bars((22635.0,))[0],
                    "session_date": "2026-07-15",
                },
            ],
        ),
        (
            "mixed_symbol",
            [
                *_bars((22590.0, 22630.0, 22615.0)),
                {
                    **_bars((22635.0,))[0],
                    "symbol": "BANKNIFTY",
                },
            ],
        ),
        (
            "duplicate_timestamps",
            [
                *_bars((22590.0, 22630.0, 22615.0)),
                {
                    **_bars((22635.0,))[0],
                    "bar_start_timestamp": _bars((22590.0,))[0]["bar_start_timestamp"],
                    "ts": _bars((22590.0,))[0]["ts"],
                },
            ],
        ),
        (
            "non_1m_timestamps",
            _bars((22590.0, 22630.0, 22615.0, 22635.0), minute_step=5, timeframe="5m"),
        ),
    ],
)
def test_completed_history_non_dependence_across_materially_different_histories(case_name: str, history) -> None:
    result = generate_opening_range_retest_candidates(
        _snapshot_context(completed_bar_history=history),
        _regime(),
    )

    assert _summary(result) == BASE_FINGERPRINT


def test_history_collapse_false_positives_share_the_same_fingerprint() -> None:
    no_breakout = generate_opening_range_retest_candidates(
        _snapshot_context(completed_bar_history=_bars((22502.0, 22503.0, 22504.0))),
        _regime(),
    )
    breakout_without_retest = generate_opening_range_retest_candidates(
        _snapshot_context(completed_bar_history=_bars((22590.0, 22640.0, 22642.0, 22644.0))),
        _regime(),
    )
    breakout_then_failure = generate_opening_range_retest_candidates(
        _snapshot_context(completed_bar_history=_bars((22590.0, 22640.0, 22530.0, 22520.0))),
        _regime(),
    )

    fingerprints = {_summary(no_breakout), _summary(breakout_without_retest), _summary(breakout_then_failure)}
    assert fingerprints == {BASE_FINGERPRINT}


def test_future_mutation_paths_collapse_to_same_production_candidate() -> None:
    prefix = (
        {"ts": "2026-07-14T09:15:00+05:30", "open": 22500.0, "high": 22510.0, "low": 22490.0, "close": 22505.0, "volume": 1000.0},
        {"ts": "2026-07-14T09:16:00+05:30", "open": 22501.0, "high": 22511.0, "low": 22491.0, "close": 22506.0, "volume": 1010.0},
        {"ts": "2026-07-14T09:17:00+05:30", "open": 22502.0, "high": 22512.0, "low": 22492.0, "close": 22507.0, "volume": 1020.0},
    )
    path_a = prefix + (
        {"ts": "2026-07-14T09:18:00+05:30", "open": 22498.0, "high": 22500.0, "low": 22440.0, "close": 22455.0, "volume": 1030.0},
        {"ts": "2026-07-14T09:19:00+05:30", "open": 22450.0, "high": 22470.0, "low": 22420.0, "close": 22430.0, "volume": 1040.0},
    )
    path_b = prefix + (
        {"ts": "2026-07-14T09:18:00+05:30", "open": 22600.0, "high": 22635.0, "low": 22595.0, "close": 22628.0, "volume": 1030.0},
        {"ts": "2026-07-14T09:19:00+05:30", "open": 22628.0, "high": 22655.0, "low": 22620.0, "close": 22650.0, "volume": 1040.0},
    )
    path_c = prefix + (
        {"ts": "2026-07-14T09:18:00+05:30", "open": 22460.0, "high": 22470.0, "low": 22395.0, "close": 22405.0, "volume": 1030.0},
        {"ts": "2026-07-14T09:19:00+05:30", "open": 22395.0, "high": 22410.0, "low": 22370.0, "close": 22380.0, "volume": 1040.0},
    )

    result_a = generate_opening_range_retest_candidates(_snapshot_context(completed_bar_history=path_a), _regime())
    result_b = generate_opening_range_retest_candidates(_snapshot_context(completed_bar_history=path_b), _regime())
    result_c = generate_opening_range_retest_candidates(_snapshot_context(completed_bar_history=path_c), _regime())

    assert _summary(result_a) == _summary(result_b) == _summary(result_c) == BASE_FINGERPRINT


def test_physical_truncation_matches_prefix_limited_result() -> None:
    full_history = (
        {"ts": "2026-07-14T09:15:00+05:30", "open": 22500.0, "high": 22510.0, "low": 22490.0, "close": 22505.0, "volume": 1000.0},
        {"ts": "2026-07-14T09:16:00+05:30", "open": 22501.0, "high": 22511.0, "low": 22491.0, "close": 22506.0, "volume": 1010.0},
        {"ts": "2026-07-14T09:17:00+05:30", "open": 22502.0, "high": 22512.0, "low": 22492.0, "close": 22507.0, "volume": 1020.0},
        {"ts": "2026-07-14T09:18:00+05:30", "open": 22498.0, "high": 22500.0, "low": 22440.0, "close": 22455.0, "volume": 1030.0},
        {"ts": "2026-07-14T09:19:00+05:30", "open": 22450.0, "high": 22470.0, "low": 22420.0, "close": 22430.0, "volume": 1040.0},
    )
    truncated_history = full_history[:3]

    full_trace = _repeat_trace(
        context_builder=_gate_then_fixed_context,
        completed_bars=full_history,
        case_id="physical_truncation_full",
    )
    truncated_trace = _repeat_trace(
        context_builder=_gate_then_fixed_context,
        completed_bars=truncated_history,
        case_id="physical_truncation_truncated",
    )

    assert full_trace.steps[:3] == truncated_trace.steps
    assert [step.candidate_semantic_fingerprint for step in full_trace.steps[:3]] == [
        step.candidate_semantic_fingerprint for step in truncated_trace.steps
    ]


def test_future_mutation_by_path_remains_non_causal() -> None:
    trace_a = _repeat_trace(
        context_builder=_gate_then_fixed_context,
        completed_bars=(
            *_bars((22590.0, 22630.0, 22615.0)),
            {"ts": "2026-07-14T09:18:00+05:30", "open": 22498.0, "high": 22500.0, "low": 22440.0, "close": 22455.0, "volume": 1030.0},
            {"ts": "2026-07-14T09:19:00+05:30", "open": 22450.0, "high": 22470.0, "low": 22420.0, "close": 22430.0, "volume": 1040.0},
        ),
        case_id="future_path_a",
    )
    trace_b = _repeat_trace(
        context_builder=_gate_then_fixed_context,
        completed_bars=(
            *_bars((22590.0, 22630.0, 22615.0)),
            {"ts": "2026-07-14T09:18:00+05:30", "open": 22600.0, "high": 22635.0, "low": 22595.0, "close": 22628.0, "volume": 1030.0},
            {"ts": "2026-07-14T09:19:00+05:30", "open": 22628.0, "high": 22655.0, "low": 22620.0, "close": 22650.0, "volume": 1040.0},
        ),
        case_id="future_path_b",
    )
    trace_c = _repeat_trace(
        context_builder=_gate_then_fixed_context,
        completed_bars=(
            *_bars((22590.0, 22630.0, 22615.0)),
            {"ts": "2026-07-14T09:18:00+05:30", "open": 22460.0, "high": 22470.0, "low": 22395.0, "close": 22405.0, "volume": 1030.0},
            {"ts": "2026-07-14T09:19:00+05:30", "open": 22395.0, "high": 22410.0, "low": 22370.0, "close": 22380.0, "volume": 1040.0},
        ),
        case_id="future_path_c",
    )

    assert [step.candidate_semantic_fingerprint for step in trace_a.steps] == [
        step.candidate_semantic_fingerprint for step in trace_b.steps
    ] == [step.candidate_semantic_fingerprint for step in trace_c.steps]
    assert trace_a.emission_count == trace_b.emission_count == trace_c.emission_count == 3
    assert trace_a.first_emission_checkpoint == trace_b.first_emission_checkpoint == trace_c.first_emission_checkpoint


def test_repeated_emission_scenarios_are_observable_and_distinct() -> None:
    frozen_trace = _repeat_trace(
        context_builder=_fixed_prefix_context,
        completed_bars=_bars((22590.0, 22630.0, 22615.0, 22635.0, 22638.0)),
        case_id="repeated_frozen_snapshot",
    )
    evolving_trace = _repeat_trace(
        context_builder=_evolving_favorable_context,
        completed_bars=_bars((22590.0, 22630.0, 22615.0, 22635.0, 22638.0)),
        case_id="repeated_evolving_snapshot",
    )

    assert frozen_trace.emission_count == 5
    assert frozen_trace.first_emission_checkpoint == "2026-07-14T09:16:00+05:30"
    assert frozen_trace.repeated_semantic_fingerprint_count == 4
    assert [step.candidate_semantic_fingerprint.raw_score for step in frozen_trace.steps] == [0.451504] * 5
    assert all(step.candidate_semantic_fingerprint is not None for step in frozen_trace.steps)
    assert all(step.candidate_semantic_fingerprint.strategy_id == "opening_range_retest_v1" for step in frozen_trace.steps)
    assert all(step.setup_state_after == "EMITTED" for step in frozen_trace.steps)

    assert evolving_trace.emission_count == 5
    assert evolving_trace.first_emission_checkpoint == "2026-07-14T09:16:00+05:30"
    assert evolving_trace.repeated_semantic_fingerprint_count == 4
    assert [step.candidate_semantic_fingerprint.raw_score for step in evolving_trace.steps] == [0.451504] * 5
    assert all(step.candidate_semantic_fingerprint is not None for step in evolving_trace.steps)
    assert all(step.candidate_semantic_fingerprint.strategy_id == "opening_range_retest_v1" for step in evolving_trace.steps)


def test_invalidation_is_metadata_only_and_has_no_revival_memory() -> None:
    baseline = generate_opening_range_retest_candidates(_snapshot_context(), _regime())
    inside_range = generate_opening_range_retest_candidates(
        _snapshot_context(completed_bar_history=_bars((22590.0, 22640.0, 22530.0, 22520.0))),
        _regime(),
    )
    revival_like = generate_opening_range_retest_candidates(
        _snapshot_context(completed_bar_history=_bars((22590.0, 22640.0, 22642.0, 22644.0))),
        _regime(),
    )

    assert _summary(baseline) == BASE_FINGERPRINT
    assert _summary(inside_range) == BASE_FINGERPRINT
    assert _summary(revival_like) == BASE_FINGERPRINT
    assert baseline[0].invalid_if == "price_returns_inside_opening_range"
    assert "setup_identity" not in baseline[0].evidence
    assert "setup_identity" not in inside_range[0].evidence
    assert "setup_identity" not in revival_like[0].evidence


def test_directional_contract_is_bidirectional_from_the_same_snapshot_contract() -> None:
    call_result = generate_opening_range_retest_candidates(_snapshot_context(), _regime())
    put_result = generate_opening_range_retest_candidates(
        _snapshot_context(
            spot_ltp=22452.0,
            vwap=22510.0,
            orb_low=22460.0,
            pe_premium_change=11.0,
            ce_premium_change=0.0,
            minutes_since_open=42,
        ),
        _regime(down=0.72),
    )

    assert len(call_result) == 1
    assert call_result[0].direction == "BUY_CALL"
    assert len(put_result) == 1
    assert put_result[0].direction == "BUY_PUT"


def test_unrelated_production_controls_remain_direct_and_stable() -> None:
    opening_drive = generate_opening_drive_candidates(
        _snapshot_context(minutes_since_open=8),
        _regime(up=0.8),
    )
    trend_pullback = generate_trend_pullback_candidates(
        StrategyContext(
            symbol="NIFTY",
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
            completed_bar_history=_bars((22590.0, 22630.0, 22615.0, 22635.0)),
        ),
        _regime(up=0.72),
    )

    assert len(opening_drive) == 1
    assert opening_drive[0].strategy_id == "opening_drive_v1"
    assert len(trend_pullback) == 1
    assert trend_pullback[0].strategy_id == "trend_pullback_v1"


def test_opening_range_retest_negative_control_produces_blocking_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        result = generate_opening_range_retest_candidates(
            _snapshot_context(minutes_since_open=None),
            _regime(),
        )

    assert result == ()
    assert any(
        record.message
        == "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=opening_range_retest_v1 missing_fields=minutes_since_open invalid_fields=- reason=missing_required_session_timing"
        for record in caplog.records
    )
