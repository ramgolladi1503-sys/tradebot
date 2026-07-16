from __future__ import annotations

import logging
import socket
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.candidate_pool_orchestrator import build_candidate_pool_report, get_default_candidate_generators
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from core.orchestrator import _snapshot_symbol_payload
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from strategies.movement.option_pressure import generate_option_pressure_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates
from tests.test_opening_range_retest_temporal_fixture_contract import (
    CALL_VALID_ROWS,
    OPENING_RANGE_ROWS,
    _history_state_for_rows,
)


IST = ZoneInfo("Asia/Kolkata")


def _trend_pullback_history() -> list[dict[str, object]]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    closes = (22590.0, 22630.0, 22615.0, 22635.0)
    bars: list[dict[str, object]] = []
    for index, close in enumerate(closes):
        bar_start = start + timedelta(minutes=index)
        bar_end = bar_start + timedelta(minutes=1)
        bars.append(
            {
                "symbol": "NIFTY",
                "session_date": "2026-07-14",
                "timeframe": "1m",
                "bar_start_timestamp": bar_start.isoformat(),
                "bar_end_timestamp": bar_end.isoformat(),
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


def _regime(primary: str = "TREND_UP", **scores: float) -> MovementRegimeResult:
    base = {
        "TREND_UP": 0.8,
        "TREND_DOWN": 0.0,
        "RANGE": 0.0,
        "CHOP": 0.0,
        "COMPRESSION": 0.8,
        "VOLATILITY_EXPANSION": 0.45,
        "TRAP_RISK": 0.0,
        "EXHAUSTION_RISK": 0.0,
        "EXPIRY_CONTEXT": 0.0,
        "INCONCLUSIVE": 0.0,
    }
    base.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime=primary, scores=base)


def _full_context(**overrides: object) -> StrategyContext:
    payload = {
        "symbol": "NIFTY",
        "ts_epoch": 1721028600.0,
        "spot_ltp": 22620.0,
        "open_price": 22500.0,
        "vwap": 22540.0,
        "day_high": 22620.0,
        "day_low": 22460.0,
        "nearest_support": 22590.0,
        "nearest_resistance": 22600.0,
        "orb_high": 22600.0,
        "orb_low": 22460.0,
        "range_width_pct": 0.14,
        "atr": 70.0,
        "atr_short": 35.0,
        "atr_long": 100.0,
        "volume_z": 1.5,
        "vwap_slope": 0.03,
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
        "minutes_since_open": 35,
        "minutes_to_close": 280,
        "completed_bar_history": _trend_pullback_history(),
        "metadata": {
            "previous_spot_ltp": 22590.0,
            "price_reentered_range": True,
            "previous_break_high": 22685.0,
            "previous_break_low": 22430.0,
        },
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def _opening_range_context(**overrides: object) -> StrategyContext:
    state = _history_state_for_rows(OPENING_RANGE_ROWS + CALL_VALID_ROWS[:4])
    payload = {
        "symbol": "NIFTY",
        "ts_epoch": 1721028600.0,
        "spot_ltp": 22608.0,
        "open_price": 22500.0,
        "vwap": 22550.0,
        "day_high": 22620.0,
        "day_low": 22460.0,
        "nearest_support": 22590.0,
        "nearest_resistance": 22600.0,
        "orb_high": 22600.0,
        "orb_low": 22500.0,
        "range_width_pct": 0.14,
        "atr": 70.0,
        "atr_short": 35.0,
        "atr_long": 100.0,
        "volume_z": 1.5,
        "vwap_slope": 0.03,
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
        "minutes_since_open": 35,
        "minutes_to_close": 280,
        "completed_bar_history": state.history_payload(),
        "metadata": {
            "previous_spot_ltp": 22590.0,
            "price_reentered_range": True,
            "previous_break_high": 22685.0,
            "previous_break_low": 22430.0,
        },
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def _runtime_truth_payload() -> dict:
    warnings: list[str] = []
    return _snapshot_symbol_payload(
        {
            "symbol": "NIFTY",
            "spot": 22620.0,
            "ltp": 22620.0,
            "prev_ltp": 22590.0,
            "vwap": 22540.0,
            "atr": 70.0,
            "vol_z": 1.5,
            "vwap_slope": 0.03,
            "minutes_since_open": 35,
            "market_open": True,
            "segment": "NSE_FNO",
            "timestamp_ist": "2026-07-14T10:15:00+05:30",
            "ltp_ts_epoch": 1721028600.0,
            "orb_high": 22600.0,
            "orb_low": 22460.0,
            "completed_bar_history": _trend_pullback_history(),
            "completed_bar_history_provenance": {
                "source_component": "tests.test_candidate_phase2_ownership",
                "source_field": "completed_bar_history",
                "status": "TRUTHFUL",
            },
            "orb_state": {"status": "NEUTRAL"},
            "option_chain_health": {"quote_age_sec": 0.4},
            "quote_source": "live_option_tick",
            "option_chain": [
                {"strike": 22600.0, "type": "CE", "ltp": 120.0, "spread_pct": 0.8, "bid_qty": 600.0, "ask_qty": 600.0, "ltp_change": 12.0},
                {"strike": 22600.0, "type": "PE", "ltp": 90.0, "spread_pct": 0.8, "bid_qty": 600.0, "ask_qty": 600.0, "ltp_change": 0.0},
            ],
        },
        warnings,
    )


def _raw_setup_fingerprint() -> list[tuple[str, str, float, str, str, str]]:
    opening_ctx = _opening_range_context()
    directional_ctx = _full_context()
    regime = _regime()
    emitted = (
        generate_opening_range_retest_candidates(opening_ctx, regime)
        + generate_compression_breakout_candidates(directional_ctx, regime)
        + generate_trend_pullback_candidates(directional_ctx, regime)
    )
    return [
        (
            candidate.strategy_id,
            candidate.direction,
            round(candidate.raw_score, 6),
            candidate.entry_trigger,
            candidate.invalid_if,
            candidate.rank_reason,
        )
        for candidate in emitted
    ]


def _ownership_fingerprint(report) -> list[tuple[str, str, float | None, float | None, float | None, bool]]:
    return [
        (
            candidate.strategy_id,
            candidate.status,
            candidate.option_confirmation_score,
            candidate.liquidity_score,
            candidate.freshness_score,
            candidate.executable_eligible,
        )
        for candidate in report.candidates
        if candidate.direction in {"BUY_CALL", "BUY_PUT"}
    ]


def _blocked_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.message for record in caplog.records if "event=CANDIDATE_OWNERSHIP_BLOCKED" in record.message]


def test_directional_generators_emit_raw_candidates_with_unset_phase2_fields():
    candidates = (
        generate_opening_range_retest_candidates(_opening_range_context(), _regime())
        + generate_compression_breakout_candidates(_full_context(), _regime())
        + generate_trend_pullback_candidates(_full_context(), _regime())
    )

    assert [candidate.strategy_id for candidate in candidates] == [
        "opening_range_retest_v1",
        "compression_breakout_v1",
        "trend_pullback_v1",
    ]
    assert all(candidate.status == "RAW_CANDIDATE" for candidate in candidates)
    assert all(candidate.option_confirmation_score is None for candidate in candidates)
    assert all(candidate.liquidity_score is None for candidate in candidates)
    assert all(candidate.freshness_score is None for candidate in candidates)
    assert all(candidate.executable_eligible is False for candidate in candidates)


def test_generators_preserve_setup_identity_and_pattern_scores():
    assert _raw_setup_fingerprint() == [
        (
            "opening_range_retest_v1",
            "BUY_CALL",
            0.451504,
            "opening_range_breakout_retest_hold",
            "price_returns_inside_opening_range",
            "opening range breakout retest held",
        ),
        (
            "compression_breakout_v1",
            "BUY_CALL",
            0.470676,
            "compression_range_breakout_release",
            "price_returns_inside_compression_range",
            "range and ATR compression released into a directional breakout",
        ),
        (
            "trend_pullback_v1",
            "BUY_CALL",
            0.648584,
            "trend_pullback_hold_resume",
            "pullback_breaks_anchor",
            "established trend resumed after a controlled pullback",
        ),
    ]


def test_make_candidate_does_not_fabricate_downstream_truth():
    candidate = generate_opening_range_retest_candidates(_opening_range_context(), _regime())[0]

    assert candidate.status == "RAW_CANDIDATE"
    assert candidate.option_confirmation_score is None
    assert candidate.liquidity_score is None
    assert candidate.freshness_score is None
    assert candidate.lineage["params_hash"]
    assert candidate.lineage["promotion_state"] == "READY_FOR_PUBLICATION"


def test_candidate_pool_enriches_directional_candidates_from_real_downstream_quote_truth():
    report = build_candidate_pool_report(
        _full_context(),
        _regime(),
        candidate_generators=get_default_candidate_generators(),
    )

    strategy_ids = [candidate.strategy_id for candidate in report.candidates if candidate.direction in {"BUY_CALL", "BUY_PUT"}]
    assert strategy_ids == [
        "compression_breakout_v1",
        "trend_pullback_v1",
    ]
    assert len(report.option_confirmations) == 2
    assert report.metadata["raw_candidate_count_before_phase2_enrichment"] == 2
    assert all(candidate.status == "VALIDATED_CANDIDATE" for candidate in report.candidates if candidate.direction in {"BUY_CALL", "BUY_PUT"})
    assert all(candidate.option_confirmation_score is not None for candidate in report.candidates if candidate.direction in {"BUY_CALL", "BUY_PUT"})
    assert all(candidate.liquidity_score is not None for candidate in report.candidates if candidate.direction in {"BUY_CALL", "BUY_PUT"})
    assert all(candidate.freshness_score is not None for candidate in report.candidates if candidate.direction in {"BUY_CALL", "BUY_PUT"})


def test_option_confirmation_is_not_counted_as_directional_market_thesis_strategy():
    assert generate_option_pressure_candidates(_full_context(), _regime()) == ()

    report = build_candidate_pool_report(
        _full_context(),
        _regime(),
        candidate_generators=get_default_candidate_generators(),
    )

    assert "option_pressure_confirmation_v1" not in {
        candidate.strategy_id for candidate in report.candidates
    }
    assert len(report.option_confirmations) == 2
    assert all(confirmation.candidate_strategy_id != "option_pressure_confirmation_v1" for confirmation in report.option_confirmations)


def test_no_directional_generator_marks_itself_tradable_or_executable():
    raw_candidates = (
        generate_opening_range_retest_candidates(_opening_range_context(), _regime())
        + generate_compression_breakout_candidates(_full_context(), _regime())
        + generate_trend_pullback_candidates(_full_context(), _regime())
    )

    assert all(candidate.executable_eligible is False for candidate in raw_candidates)
    assert all(candidate.status == "RAW_CANDIDATE" for candidate in raw_candidates)


def test_compliant_raw_candidate_passes_boundary_and_violation_is_blocked(caplog: pytest.LogCaptureFixture):
    good_candidate = generate_opening_range_retest_candidates(_opening_range_context(), _regime())[0]

    violating_candidate = StrategyCandidate(
        schema_version=1,
        strategy_id="bad_strategy_v1",
        movement_type="COMPRESSION_BREAKOUT",
        symbol="NIFTY",
        direction="BUY_CALL",
        status="VALIDATED_CANDIDATE",
        raw_score=0.7,
        confidence_score=0.7,
        price_structure_score=0.7,
        option_confirmation_score=0.9,
        liquidity_score=0.8,
        freshness_score=0.9,
        volatility_score=0.4,
        regime_alignment_score=0.6,
        timing_score=0.5,
        trap_risk_score=0.1,
        confluence_score=0.7,
        entry_trigger="bad",
        invalid_if="bad",
        rank_reason="bad",
        blockers=(),
        warnings=(),
    )

    def violating_generator(ctx, regime):
        return (violating_candidate,)

    def compliant_generator(ctx, regime):
        return (good_candidate,)

    with caplog.at_level(logging.WARNING):
        report = build_candidate_pool_report(
            _full_context(),
            _regime(),
            candidate_generators=[violating_generator, compliant_generator],
        )

    assert [candidate.strategy_id for candidate in report.candidates if candidate.direction in {"BUY_CALL", "BUY_PUT"}] == ["opening_range_retest_v1"]
    assert _blocked_messages(caplog) == [
        "event=CANDIDATE_OWNERSHIP_BLOCKED runtime_strategy_id=bad_strategy_v1 violating_fields=freshness_score,liquidity_score,option_confirmation_score,status reason=strategy_candidate_claims_phase2_owned_truth"
    ]
    assert report.failed_generator_count == 0


def test_ownership_fingerprint_changes_are_truthful_and_setup_identity_is_preserved():
    report = build_candidate_pool_report(
        _full_context(),
        _regime(),
        candidate_generators=get_default_candidate_generators(),
    )

    assert _ownership_fingerprint(report) == [
        ("compression_breakout_v1", "VALIDATED_CANDIDATE", 0.81475, 0.8599999999999999, 0.84, True),
        ("trend_pullback_v1", "VALIDATED_CANDIDATE", 0.81475, 0.8599999999999999, 0.84, True),
    ]


def test_phase2a_truth_phase2b_missing_evidence_and_observability_remain_intact(caplog: pytest.LogCaptureFixture):
    ctx = _strategy_context_from_market_symbol("NIFTY", _runtime_truth_payload())
    assert ctx.vwap == 22540.0
    assert ctx.orb_high == 22600.0
    assert ctx.option_ce_ltp == 120.0

    with caplog.at_level(logging.WARNING):
        report = build_candidate_pool_report(
            _full_context(vwap=None),
            _regime(),
            candidate_generators=get_default_candidate_generators(),
        )

    assert report.failed_generator_count == 0
    assert any("event=STRATEGY_EVIDENCE_BLOCKED" in record.message for record in caplog.records)


def test_no_trade_role_and_runtime_identity_remain_unchanged():
    report = build_candidate_pool_report(
        _full_context(),
        _regime(primary="CHOP", CHOP=0.9),
        candidate_generators=get_default_candidate_generators(),
    )

    no_trade_candidates = [candidate for candidate in report.candidates if candidate.direction == "NO_TRADE"]
    assert len(no_trade_candidates) == 1
    assert no_trade_candidates[0].strategy_id == "no_trade_engine_v1"
    assert no_trade_candidates[0].movement_type == "NO_TRADE_CHOP"


def test_no_network_or_thread_activity_occurs_during_candidate_pool_build(monkeypatch: pytest.MonkeyPatch):
    thread_starts: list[str] = []

    def _fail_connection(*_args, **_kwargs):
        raise AssertionError("candidate pool build must not open network connections")

    original_thread_start = threading.Thread.start

    def _record_thread_start(self: threading.Thread):
        thread_starts.append(self.name)
        raise AssertionError("candidate pool build must not start threads")

    monkeypatch.setattr(socket, "create_connection", _fail_connection)
    monkeypatch.setattr(threading.Thread, "start", _record_thread_start)

    try:
        report = build_candidate_pool_report(
            _full_context(),
            _regime(),
            candidate_generators=get_default_candidate_generators(),
        )
    finally:
        monkeypatch.setattr(threading.Thread, "start", original_thread_start)

    assert report.failed_generator_count == 0
    assert thread_starts == []
