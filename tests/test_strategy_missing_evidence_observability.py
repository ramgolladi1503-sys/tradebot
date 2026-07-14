from __future__ import annotations

import logging
import socket
import threading

import pytest

from core.candidate_pool_orchestrator import build_candidate_pool_report, get_default_candidate_generators
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.orchestrator import _snapshot_symbol_payload
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from core.strategy_parameter_profiles import COMPATIBILITY_PROFILE_ALIASES
from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from strategies.movement.event_volatility_expansion import generate_event_volatility_expansion_candidates
from strategies.movement.mean_reversion_extension import generate_mean_reversion_extension_candidates
from strategies.movement.late_day_momentum import generate_late_day_momentum_candidates
from strategies.movement.opening_drive import generate_opening_drive_candidates
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from strategies.movement.option_pressure import generate_option_pressure_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates


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


def _blocked_messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.message for record in caplog.records if "event=STRATEGY_EVIDENCE_BLOCKED" in record.message]


def test_missing_compression_fields_emit_one_deterministic_blocked_event(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        result = generate_compression_breakout_candidates(
            _full_context(range_width_pct=None, atr_short=None, atr_long=None),
            _regime(primary="COMPRESSION", COMPRESSION=0.9),
        )

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=compression_breakout_v1 missing_fields=atr_long,atr_short,range_width_pct invalid_fields=- reason=missing_required_thesis_evidence"
    ]


def test_missing_trend_anchor_identifies_correct_missing_side(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        result = generate_trend_pullback_candidates(
            _full_context(spot_ltp=22615.0, vwap=22600.0, nearest_support=None),
            _regime(primary="TREND_UP", TREND_UP=0.72),
        )

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=trend_pullback_v1 missing_fields=nearest_support invalid_fields=- reason=missing_required_structure_anchor"
    ]


def test_missing_orb_fields_identify_orb_evidence(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        result = generate_opening_range_retest_candidates(
            _full_context(orb_high=None, orb_low=None),
            _regime(primary="TREND_UP", TREND_UP=0.8),
        )

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=opening_range_retest_v1 missing_fields=orb_high,orb_low invalid_fields=- reason=missing_required_orb_evidence"
    ]


def test_missing_session_open_identifies_open_price(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        result = generate_opening_drive_candidates(
            _full_context(open_price=None, minutes_since_open=10),
            _regime(primary="TREND_UP", TREND_UP=0.8),
        )

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=opening_drive_v1 missing_fields=open_price invalid_fields=- reason=missing_required_thesis_evidence"
    ]


def test_missing_session_timing_identifies_missing_timing_fields(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        result = generate_late_day_momentum_candidates(
            _full_context(minutes_since_open=None, minutes_to_close=None),
            _regime(primary="TREND_UP", TREND_UP=0.8, CHOP=0.1),
        )

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=late_day_momentum_v1 missing_fields=minutes_since_open,minutes_to_close invalid_fields=- reason=missing_required_session_timing"
    ]


def test_missing_vwap_identifies_vwap(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        result = generate_vwap_reclaim_rejection_candidates(
            _full_context(vwap=None, metadata={"previous_spot_ltp": 22520.0}),
            _regime(primary="TREND_UP", TREND_UP=0.6, CHOP=0.1),
        )

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=vwap_reclaim_rejection_v1 missing_fields=vwap invalid_fields=- reason=missing_required_thesis_evidence"
    ]


def test_missing_mean_reversion_boundary_identifies_absent_anchor_condition(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        result = generate_mean_reversion_extension_candidates(
            _full_context(
                spot_ltp=22710.0,
                vwap=22580.0,
                nearest_resistance=None,
                day_high=None,
                pe_premium_change=10.0,
                ce_premium_change=0.0,
            ),
            _regime(primary="RANGE", RANGE=0.72, TREND_UP=0.15, VOLATILITY_EXPANSION=0.05),
        )

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=mean_reversion_extension_v1 missing_fields=day_high,nearest_resistance invalid_fields=- reason=missing_required_structure_anchor"
    ]


def test_missing_atr_or_volume_for_volatility_expansion_identifies_exact_fields(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        result = generate_event_volatility_expansion_candidates(
            _full_context(spot_ltp=22690.0, vwap=22540.0, atr_short=None, atr_long=100.0, volume_z=None, ce_premium_change=14.0),
            _regime(primary="VOLATILITY_EXPANSION", VOLATILITY_EXPANSION=0.9, TREND_UP=0.5),
        )

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=event_volatility_expansion_v1 missing_fields=atr_short,volume_z invalid_fields=- reason=missing_required_thesis_evidence"
    ]


def test_missing_same_side_option_evidence_identifies_quote_fields(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        result = generate_option_pressure_candidates(
            _full_context(
                option_ce_ltp=None,
                ce_premium_change=None,
                ce_spread_pct=None,
                ce_depth=None,
                option_pe_ltp=None,
                pe_premium_change=None,
                pe_spread_pct=None,
                pe_depth=None,
                option_ltp_age_sec=None,
            ),
            _regime(),
    )

    assert result == ()
    assert _blocked_messages(caplog) == []


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), -float("inf")])
def test_none_nan_and_infinity_are_identified_as_invalid_where_applicable(
    caplog: pytest.LogCaptureFixture,
    bad_value: float,
):
    with caplog.at_level(logging.WARNING):
        result = generate_opening_drive_candidates(
            _full_context(open_price=bad_value, vwap=bad_value, minutes_since_open=10),
            _regime(primary="TREND_UP", TREND_UP=0.8),
        )

    assert result == ()
    assert _blocked_messages(caplog) == [
        "event=STRATEGY_EVIDENCE_BLOCKED runtime_strategy_id=opening_drive_v1 missing_fields=- invalid_fields=open_price,vwap reason=missing_required_thesis_evidence"
    ]


def test_field_names_are_sorted_deterministically(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        generate_compression_breakout_candidates(
            _full_context(atr_long=None, range_width_pct=None, atr_short=None),
            _regime(primary="COMPRESSION", COMPRESSION=0.9),
        )

    assert _blocked_messages(caplog)[0].split(" missing_fields=")[1].split(" invalid_fields=")[0] == "atr_long,atr_short,range_width_pct"


def test_repeated_identical_calls_produce_identical_blocked_evidence(caplog: pytest.LogCaptureFixture):
    ctx = _full_context(range_width_pct=None, atr_short=None, atr_long=None)
    regime = _regime(primary="COMPRESSION", COMPRESSION=0.9)

    with caplog.at_level(logging.WARNING):
        generate_compression_breakout_candidates(ctx, regime)
        first = list(_blocked_messages(caplog))
        caplog.clear()
        generate_compression_breakout_candidates(ctx, regime)
        second = list(_blocked_messages(caplog))

    assert first == second


def test_one_blocked_component_does_not_abort_other_generators(caplog: pytest.LogCaptureFixture):
    ctx = _full_context(nearest_support=None, minutes_since_open=35, minutes_to_close=280)
    with caplog.at_level(logging.WARNING):
        report = build_candidate_pool_report(ctx, _regime(), candidate_generators=get_default_candidate_generators())

    strategy_ids = [candidate.strategy_id for candidate in report.candidates]
    assert "trend_pullback_v1" not in strategy_ids
    assert "opening_range_retest_v1" in strategy_ids
    assert any("runtime_strategy_id=trend_pullback_v1" in message for message in _blocked_messages(caplog))
    assert report.failed_generator_count == 0


def test_no_rejected_or_synthetic_candidate_is_created_for_observability(caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        report = build_candidate_pool_report(
            _full_context(range_width_pct=None, atr_short=None, atr_long=None),
            _regime(primary="COMPRESSION", COMPRESSION=0.9),
            candidate_generators=get_default_candidate_generators(),
        )

    strategy_ids = [candidate.strategy_id for candidate in report.candidates]
    assert "compression_breakout_v1" not in strategy_ids
    assert any("runtime_strategy_id=compression_breakout_v1" in message for message in _blocked_messages(caplog))


def test_complete_context_candidate_fingerprint_remains_exact():
    assert _fingerprint(_full_context()) == [
        ("opening_range_retest_v1", 0.328053, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("compression_breakout_v1", 0.470676, "BUY_CALL", "VALIDATED_CANDIDATE"),
        ("trend_pullback_v1", 0.648584, "BUY_CALL", "VALIDATED_CANDIDATE"),
    ]


def test_raw_scores_remain_exact():
    fingerprint = _fingerprint(_full_context())
    assert [score for _, score, _, _ in fingerprint] == [0.328053, 0.470676, 0.648584]


def test_optional_missing_evidence_retains_phase_2b_zero_contribution_behavior():
    favorable = generate_vwap_reclaim_rejection_candidates(
        _full_context(spot_ltp=22610.0, metadata={"previous_spot_ltp": 22520.0}, vwap_slope=0.04, ce_premium_change=12.0),
        _regime(primary="TREND_UP", TREND_UP=0.6, CHOP=0.1),
    )
    missing = generate_vwap_reclaim_rejection_candidates(
        _full_context(spot_ltp=22610.0, metadata={"previous_spot_ltp": 22520.0}, vwap_slope=None, ce_premium_change=12.0),
        _regime(primary="TREND_UP", TREND_UP=0.6, CHOP=0.1),
    )

    assert len(favorable) == 1
    assert len(missing) == 1
    assert missing[0].raw_score < favorable[0].raw_score
    assert "missing_optional_evidence:vwap_reclaim_rejection_v1:vwap_slope" in missing[0].warnings


def test_phase_1c_profile_blocking_remains_unchanged(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    aliases = dict(COMPATIBILITY_PROFILE_ALIASES)
    aliases["opening_range_retest_v1"] = "missing_profile_v1"
    monkeypatch.setattr("core.strategy_parameter_profiles.COMPATIBILITY_PROFILE_ALIASES", aliases)
    monkeypatch.setattr(
        "core.strategy_parameter_profiles.VALIDATED_COMPATIBILITY_PROFILE_ALIASES",
        aliases,
    )

    with caplog.at_level(logging.WARNING):
        result = generate_opening_range_retest_candidates(_full_context(), _regime())

    assert result == ()
    assert any("event=PROFILE_RESOLUTION_BLOCKED runtime_strategy_id=opening_range_retest_v1" in record.message for record in caplog.records)


def test_phase_2a_context_truth_remains_unchanged():
    ctx = _strategy_context_from_market_symbol("NIFTY", _runtime_truth_payload())

    assert ctx.vwap == 22540.0
    assert ctx.orb_high == 22600.0
    assert ctx.option_ce_ltp == 120.0


def test_no_network_broker_order_execution_or_thread_action_occurs(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch):
    thread_starts: list[str] = []

    def _fail_connection(*_args, **_kwargs):
        raise AssertionError("candidate generation must not open network connections")

    original_thread_start = threading.Thread.start

    def _record_thread_start(self: threading.Thread):
        thread_starts.append(self.name)
        raise AssertionError("candidate generation must not start threads")

    monkeypatch.setattr(socket, "create_connection", _fail_connection)
    monkeypatch.setattr(threading.Thread, "start", _record_thread_start)

    try:
        with caplog.at_level(logging.WARNING):
            report = build_candidate_pool_report(
                _full_context(range_width_pct=None, atr_short=None, atr_long=None),
                _regime(primary="COMPRESSION", COMPRESSION=0.9),
                candidate_generators=get_default_candidate_generators(),
            )
    finally:
        monkeypatch.setattr(threading.Thread, "start", original_thread_start)

    assert report.failed_generator_count == 0
    assert thread_starts == []
