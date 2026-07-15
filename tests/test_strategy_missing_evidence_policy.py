from __future__ import annotations

import socket
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.candidate_pool_orchestrator import build_candidate_pool_report, get_default_candidate_generators
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.option_confirmation import assess_option_pressure
from core.orchestrator import _snapshot_symbol_payload
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from strategies.movement.event_volatility_expansion import generate_event_volatility_expansion_candidates
from strategies.movement.exhaustion_reversal import generate_exhaustion_reversal_candidates
from strategies.movement.failed_breakout_trap import generate_failed_breakout_trap_candidates
from strategies.movement.late_day_momentum import generate_late_day_momentum_candidates
from strategies.movement.mean_reversion_extension import generate_mean_reversion_extension_candidates
from strategies.movement.option_pressure import generate_option_pressure_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates
import strategies.strategy_registry as strategy_registry


IST = ZoneInfo("Asia/Kolkata")


def _trend_pullback_history() -> list[dict[str, object]]:
    start = datetime(2026, 7, 14, 9, 15, tzinfo=IST)
    closes = (22510.0, 22535.0, 22560.0)
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


def _fingerprint(ctx: StrategyContext) -> list[tuple[str, float, str, str]]:
    report = build_candidate_pool_report(
        ctx,
        _regime(),
        candidate_generators=get_default_candidate_generators(),
    )
    return [
        (candidate.strategy_id, round(candidate.raw_score, 6), candidate.direction, candidate.status)
        for candidate in report.candidates
        if candidate.direction in {"BUY_CALL", "BUY_PUT"}
    ]


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
                "source_component": "tests.test_strategy_missing_evidence_policy",
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


def test_complete_direct_context_fingerprint_is_unchanged():
    assert _fingerprint(_full_context()) == [
        ("opening_range_retest_v1", 0.328053, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("compression_breakout_v1", 0.470676, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("trend_pullback_v1", 0.648584, "BUY_CALL", "VALIDATED_CANDIDATE"),
    ]


def test_runtime_truth_mapping_and_profile_fail_closed_stay_intact():
    ctx = _strategy_context_from_market_symbol("NIFTY", _runtime_truth_payload())

    assert ctx.vwap == 22540.0
    assert ctx.orb_high == 22600.0
    assert ctx.option_ce_ltp == 120.0
    assert ctx.metadata["previous_spot_ltp"] == 22590.0
    assert ctx.quote_source == "live_option_tick"


def test_missing_required_evidence_blocks_only_affected_generators_and_pool_continues():
    report = build_candidate_pool_report(
        _full_context(vwap=None),
        _regime(),
        candidate_generators=get_default_candidate_generators(),
    )

    strategy_ids = [candidate.strategy_id for candidate in report.candidates]
    assert report.failed_generator_count == 0
    assert strategy_ids == []
    assert report.report_executable_eligible_count == 0


def test_missing_trend_pullback_anchor_blocks_candidate():
    assert generate_trend_pullback_candidates(
        _full_context(
            spot_ltp=22615.0,
            vwap=22600.0,
            nearest_support=None,
            ce_premium_change=11.0,
        ),
        _regime(primary="TREND_UP", TREND_UP=0.72),
    ) == ()


def test_missing_trend_pullback_temporal_history_blocks_candidate():
    assert generate_trend_pullback_candidates(
        _full_context(
            spot_ltp=22615.0,
            vwap=22600.0,
            nearest_support=22590.0,
            completed_bar_history=None,
        ),
        _regime(primary="TREND_UP", TREND_UP=0.72),
    ) == ()


def test_missing_compression_measurements_do_not_satisfy_compression():
    assert generate_compression_breakout_candidates(
        _full_context(
            range_width_pct=None,
            atr_short=None,
            atr_long=None,
            spot_ltp=22650.0,
            vwap=22600.0,
            nearest_resistance=22620.0,
        ),
        _regime(primary="COMPRESSION", COMPRESSION=0.95, VOLATILITY_EXPANSION=0.45, TREND_UP=0.35),
    ) == ()


def test_missing_atr_or_volume_do_not_confirm_volatility_expansion():
    missing_atr = generate_event_volatility_expansion_candidates(
        _full_context(
            spot_ltp=22690.0,
            vwap=22540.0,
            atr_short=None,
            atr_long=100.0,
            volume_z=1.8,
            ce_premium_change=14.0,
        ),
        _regime(primary="VOLATILITY_EXPANSION", VOLATILITY_EXPANSION=0.9, TREND_UP=0.5),
    )
    missing_volume = generate_event_volatility_expansion_candidates(
        _full_context(
            spot_ltp=22690.0,
            vwap=22540.0,
            atr_short=150.0,
            atr_long=100.0,
            volume_z=None,
            ce_premium_change=14.0,
        ),
        _regime(primary="VOLATILITY_EXPANSION", VOLATILITY_EXPANSION=0.9, TREND_UP=0.5),
    )

    assert missing_atr == ()
    assert missing_volume == ()


def test_missing_range_boundary_blocks_mean_reversion_extension():
    assert generate_mean_reversion_extension_candidates(
        _full_context(
            spot_ltp=22710.0,
            vwap=22580.0,
            nearest_resistance=None,
            day_high=None,
            pe_premium_change=10.0,
            ce_premium_change=0.0,
        ),
        _regime(primary="RANGE", RANGE=0.72, TREND_UP=0.15, VOLATILITY_EXPANSION=0.05),
    ) == ()


def test_missing_failed_breakout_premium_is_weaker_than_explicit_stall():
    explicit_stall = generate_failed_breakout_trap_candidates(
        _full_context(
            spot_ltp=22505.0,
            orb_low=22490.0,
            day_low=22460.0,
            ce_premium_change=12.0,
            pe_premium_change=0.0,
        ),
        _regime(primary="TRAP_RISK", TRAP_RISK=0.75),
    )
    missing_premium = generate_failed_breakout_trap_candidates(
        _full_context(
            spot_ltp=22505.0,
            orb_low=22490.0,
            day_low=22460.0,
            ce_premium_change=12.0,
            pe_premium_change=None,
        ),
        _regime(primary="TRAP_RISK", TRAP_RISK=0.75),
    )

    assert len(explicit_stall) == 1
    assert len(missing_premium) <= 1
    if missing_premium:
        assert missing_premium[0].raw_score < explicit_stall[0].raw_score


def test_missing_exhaustion_volume_is_weaker_than_explicit_volume_fade():
    explicit_fade = generate_exhaustion_reversal_candidates(
        _full_context(
            spot_ltp=22740.0,
            vwap=22580.0,
            volume_z=0.0,
            ce_premium_change=0.0,
            pe_premium_change=10.0,
        ),
        _regime(primary="EXHAUSTION_RISK", EXHAUSTION_RISK=0.75, TREND_UP=0.35),
    )
    missing_volume = generate_exhaustion_reversal_candidates(
        _full_context(
            spot_ltp=22740.0,
            vwap=22580.0,
            volume_z=None,
            ce_premium_change=0.0,
            pe_premium_change=10.0,
        ),
        _regime(primary="EXHAUSTION_RISK", EXHAUSTION_RISK=0.75, TREND_UP=0.35),
    )

    assert len(explicit_fade) == 1
    assert len(missing_volume) <= 1
    if missing_volume:
        assert missing_volume[0].raw_score < explicit_fade[0].raw_score


def test_missing_exhaustion_premium_is_weaker_than_explicit_stall():
    explicit_stall = generate_exhaustion_reversal_candidates(
        _full_context(
            spot_ltp=22740.0,
            vwap=22580.0,
            volume_z=0.35,
            ce_premium_change=0.0,
            pe_premium_change=10.0,
        ),
        _regime(primary="EXHAUSTION_RISK", EXHAUSTION_RISK=0.75, TREND_UP=0.35),
    )
    missing_premium = generate_exhaustion_reversal_candidates(
        _full_context(
            spot_ltp=22740.0,
            vwap=22580.0,
            volume_z=0.35,
            ce_premium_change=None,
            pe_premium_change=10.0,
        ),
        _regime(primary="EXHAUSTION_RISK", EXHAUSTION_RISK=0.75, TREND_UP=0.35),
    )

    assert len(explicit_stall) == 1
    assert len(missing_premium) <= 1
    if missing_premium:
        assert missing_premium[0].raw_score < explicit_stall[0].raw_score


def test_missing_vwap_slope_does_not_raise_vwap_reclaim_score():
    favorable = generate_vwap_reclaim_rejection_candidates(
        _full_context(
            spot_ltp=22610.0,
            metadata={"previous_spot_ltp": 22520.0},
            vwap_slope=0.04,
            ce_premium_change=12.0,
        ),
        _regime(primary="TREND_UP", TREND_UP=0.6, CHOP=0.1),
    )
    missing = generate_vwap_reclaim_rejection_candidates(
        _full_context(
            spot_ltp=22610.0,
            metadata={"previous_spot_ltp": 22520.0},
            vwap_slope=None,
            ce_premium_change=12.0,
        ),
        _regime(primary="TREND_UP", TREND_UP=0.6, CHOP=0.1),
    )

    assert len(favorable) == 1
    assert len(missing) == 1
    assert missing[0].raw_score < favorable[0].raw_score
    assert "missing_optional_evidence:vwap_reclaim_rejection_v1:vwap_slope" in missing[0].warnings


def test_missing_opposite_premium_does_not_confirm_option_pressure():
    missing_opposite = assess_option_pressure(
        _full_context(
            ce_premium_change=14.0,
            pe_premium_change=None,
            option_ce_ltp=120.0,
            option_pe_ltp=90.0,
        )
    )
    explicit_opposite_weakness = assess_option_pressure(
        _full_context(
            ce_premium_change=14.0,
            pe_premium_change=0.0,
            option_ce_ltp=120.0,
            option_pe_ltp=90.0,
        )
    )

    assert missing_opposite.bullish_score < explicit_opposite_weakness.bullish_score


def test_option_pressure_candidate_blocks_when_quote_age_or_side_ltp_are_missing():
    missing_age = generate_option_pressure_candidates(
        _full_context(option_ltp_age_sec=None),
        _regime(primary="TREND_UP", TREND_UP=0.7, VOLATILITY_EXPANSION=0.3),
    )
    missing_ltp_assessment = assess_option_pressure(
        _full_context(
            option_ce_ltp=None,
            ce_premium_change=14.0,
            pe_premium_change=0.0,
        )
    )

    assert missing_age == ()
    assert "OPTION_CONFIRMATION_MISSING" in missing_ltp_assessment.ce.blockers


def test_field_specific_zero_values_remain_valid_without_becoming_positive_evidence():
    assessment = assess_option_pressure(
        _full_context(
            ce_premium_change=0.0,
            pe_premium_change=10.0,
            ce_spread_pct=0.0,
            pe_spread_pct=0.0,
        )
    )

    assert assessment.ce.premium_change == 0.0
    assert assessment.ce.spread_pct == 0.0
    assert "OPTION_CONFIRMATION_MISSING" in assessment.ce.blockers


@pytest.mark.parametrize("invalid_value", [None, float("nan"), float("inf"), -float("inf")])
def test_none_nan_and_infinity_are_invalid_for_required_market_fields(invalid_value: float | None):
    assert generate_vwap_reclaim_rejection_candidates(
        _full_context(vwap=invalid_value, metadata={"previous_spot_ltp": 22520.0}),
        _regime(primary="TREND_UP", TREND_UP=0.6, CHOP=0.1),
    ) == ()


def test_missing_optional_evidence_never_increases_score():
    complete = generate_late_day_momentum_candidates(
        _full_context(
            spot_ltp=22680.0,
            vwap=22540.0,
            volume_z=2.0,
            minutes_since_open=300,
            minutes_to_close=90,
            ce_premium_change=14.0,
        ),
        _regime(primary="TREND_UP", TREND_UP=0.8, CHOP=0.1),
    )
    missing_optional = generate_late_day_momentum_candidates(
        _full_context(
            spot_ltp=22680.0,
            vwap=22540.0,
            volume_z=None,
            minutes_since_open=300,
            minutes_to_close=90,
            ce_premium_change=14.0,
        ),
        _regime(primary="TREND_UP", TREND_UP=0.8, CHOP=0.1),
    )

    assert len(complete) == 1
    assert len(missing_optional) == 1
    assert missing_optional[0].raw_score <= complete[0].raw_score


def test_runtime_context_construction_opens_no_network_threads_or_source_parsing(
    monkeypatch: pytest.MonkeyPatch,
):
    thread_starts: list[str] = []

    def _fail_connection(*_args, **_kwargs):
        raise AssertionError("runtime context construction must not open network connections")

    original_thread_start = threading.Thread.start

    def _record_thread_start(self: threading.Thread):
        thread_starts.append(self.name)
        raise AssertionError("runtime context construction must not start threads")

    def _fail_source_parse(*_args, **_kwargs):
        raise AssertionError("source parsing must stay offline only")

    monkeypatch.setattr(socket, "create_connection", _fail_connection)
    monkeypatch.setattr(threading.Thread, "start", _record_thread_start)
    monkeypatch.setattr(strategy_registry, "_extract_embedded_profile_defaults", _fail_source_parse)

    try:
        ctx = _strategy_context_from_market_symbol("NIFTY", _runtime_truth_payload())
    finally:
        monkeypatch.setattr(threading.Thread, "start", original_thread_start)

    assert ctx.symbol == "NIFTY"
    assert thread_starts == []
