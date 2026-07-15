from __future__ import annotations

import logging
import socket
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from config import config as cfg
from core.candidate_pool_orchestrator import build_candidate_pool_report, get_default_candidate_generators
from core.execution_guard import ExecutionGuard, must_have_valid_approval
from core.movement_contract import StrategyContext
from core.movement_regime import MovementRegimeResult
from core.runtime_snapshot_producer import _strategy_context_from_market_symbol
from core.option_confirmation import CandidateOptionConfirmation
from core.orchestrator import _snapshot_symbol_payload
from strategies.movement._utils import regime_alignment_score, side_evidence
from strategies.movement.compression_breakout import generate_compression_breakout_candidates
from strategies.movement.event_volatility_expansion import generate_event_volatility_expansion_candidates
from strategies.movement.exhaustion_reversal import generate_exhaustion_reversal_candidates
from strategies.movement.failed_breakout_trap import generate_failed_breakout_trap_candidates
from strategies.movement.late_day_momentum import generate_late_day_momentum_candidates
from strategies.movement.mean_reversion_extension import generate_mean_reversion_extension_candidates
from strategies.movement.opening_drive import generate_opening_drive_candidates
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates
from strategies.movement.trend_pullback import generate_trend_pullback_candidates
from strategies.movement.vwap_reclaim import generate_vwap_reclaim_rejection_candidates


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


def _primary_context(**overrides: object) -> StrategyContext:
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


def _event_context(**overrides: object) -> StrategyContext:
    payload = {
        "symbol": "NIFTY",
        "spot_ltp": 22700.0,
        "open_price": 22500.0,
        "vwap": 22600.0,
        "vwap_slope": 0.04,
        "day_high": 22720.0,
        "day_low": 22480.0,
        "nearest_resistance": 22740.0,
        "nearest_support": 22580.0,
        "range_width_pct": 0.80,
        "atr_short": 150.0,
        "atr_long": 90.0,
        "volume_z": 2.2,
        "volatility_state": "EXPANDING",
        "option_ce_ltp": 135.0,
        "option_pe_ltp": 92.0,
        "ce_premium_change": 16.0,
        "pe_premium_change": 0.0,
        "ce_spread_pct": 0.9,
        "pe_spread_pct": 0.9,
        "ce_depth": 1400.0,
        "pe_depth": 1400.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
        "minutes_since_open": 260,
        "minutes_to_close": 70,
        "expiry_context": False,
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def _all_semantic_candidates():
    return (
        generate_opening_drive_candidates(
            _primary_context(minutes_since_open=8),
            _regime(TREND_UP=0.8, VOLATILITY_EXPANSION=0.4),
        )
        + generate_opening_range_retest_candidates(_primary_context(), _regime())
        + generate_compression_breakout_candidates(_primary_context(), _regime())
        + generate_trend_pullback_candidates(_primary_context(), _regime())
        + generate_vwap_reclaim_rejection_candidates(
            _primary_context(
                spot_ltp=22620.0,
                vwap=22600.0,
                vwap_slope=0.04,
                metadata={"previous_spot_ltp": 22590.0},
            ),
            _regime(TREND_UP=0.6, CHOP=0.1),
        )
        + generate_failed_breakout_trap_candidates(
            _primary_context(
                spot_ltp=22645.0,
                orb_high=22660.0,
                day_high=22690.0,
                ce_premium_change=0.0,
                pe_premium_change=12.0,
                metadata={"previous_break_high": 22685.0, "price_reentered_range": True},
            ),
            _regime(primary="TRAP_RISK", TRAP_RISK=0.75),
        )
        + generate_exhaustion_reversal_candidates(
            _primary_context(
                spot_ltp=22740.0,
                vwap=22580.0,
                nearest_resistance=22760.0,
                nearest_support=22490.0,
                range_width_pct=0.50,
                atr_short=80.0,
                atr_long=100.0,
                volume_z=0.35,
                ce_premium_change=0.0,
                pe_premium_change=10.0,
                minutes_since_open=110,
            ),
            _regime(primary="EXHAUSTION_RISK", EXHAUSTION_RISK=0.75, TREND_UP=0.35),
        )
        + generate_mean_reversion_extension_candidates(
            _primary_context(
                spot_ltp=22710.0,
                vwap=22580.0,
                nearest_resistance=22720.0,
                ce_premium_change=0.0,
                pe_premium_change=10.0,
                range_width_pct=0.50,
                atr_short=80.0,
                atr_long=100.0,
                volume_z=0.35,
                minutes_since_open=110,
            ),
            _regime(primary="RANGE", RANGE=0.72, TREND_UP=0.15, VOLATILITY_EXPANSION=0.05),
        )
        + generate_event_volatility_expansion_candidates(
            _event_context(),
            _regime(primary="VOLATILITY_EXPANSION", VOLATILITY_EXPANSION=0.82, TREND_UP=0.55),
        )
        + generate_late_day_momentum_candidates(
            _event_context(),
            _regime(primary="TREND_UP", TREND_UP=0.76, CHOP=0.1),
        )
    )


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
                "source_component": "tests.test_candidate_phase2_semantic_ownership",
                "source_field": "completed_bar_history",
                "status": "TRUTHFUL",
            },
            "orb_state": {"status": "NEUTRAL"},
            "option_chain_health": {"quote_age_sec": 0.4},
            "quote_source": "live_option_tick",
            "option_chain": [
                {
                    "strike": 22600.0,
                    "type": "CE",
                    "ltp": 120.0,
                    "spread_pct": 0.8,
                    "bid_qty": 600.0,
                    "ask_qty": 600.0,
                    "ltp_change": 12.0,
                },
                {
                    "strike": 22600.0,
                    "type": "PE",
                    "ltp": 90.0,
                    "spread_pct": 0.8,
                    "bid_qty": 600.0,
                    "ask_qty": 600.0,
                    "ltp_change": 0.0,
                },
            ],
        },
        warnings,
    )


def _legacy_mixed_score(candidate, regime: MovementRegimeResult) -> tuple[float, dict[str, float]]:
    side = side_evidence(_primary_context(), candidate.direction)
    align_score = regime_alignment_score(regime, candidate.direction)
    components = {
        "price_structure_weighted": 0.25 * candidate.price_structure_score,
        "option_confirmation_weighted": 0.25 * side.option_confirmation_score,
        "liquidity_weighted": 0.20 * side.liquidity_score,
        "freshness_weighted": 0.15 * side.freshness_score,
        "regime_alignment_weighted": 0.15 * align_score,
    }
    return sum(components.values()), components


def test_raw_directional_candidates_keep_setup_owned_semantics():
    candidates = _all_semantic_candidates()
    assert [candidate.strategy_id for candidate in candidates] == [
        "opening_drive_v1",
        "opening_range_retest_v1",
        "compression_breakout_v1",
        "trend_pullback_v1",
        "vwap_reclaim_rejection_v1",
        "failed_breakout_trap_v1",
        "exhaustion_reversal_v1",
        "mean_reversion_extension_v1",
        "event_volatility_expansion_v1",
        "late_day_momentum_v1",
    ]

    forbidden_text = (
        "option_confirmation",
        "option-side confirmation",
        "liquidity",
        "freshness",
        "tradable",
        "executable",
        "execution approval",
        "validated",
        "quote_degrades",
    )
    for candidate in candidates:
        payload = " ".join(
            [
                candidate.entry_trigger.lower(),
                candidate.invalid_if.lower(),
                candidate.rank_reason.lower(),
                " ".join(tag.lower() for tag in candidate.confluence_tags),
                " ".join(warning.lower() for warning in candidate.warnings),
            ]
        )
        assert all(fragment not in payload for fragment in forbidden_text), candidate.strategy_id

    orb = candidates[1]
    compression = candidates[2]
    trend = candidates[3]
    assert (orb.entry_trigger, orb.invalid_if, orb.rank_reason) == (
        "opening_range_breakout_retest_hold",
        "price_returns_inside_opening_range",
        "opening range breakout retest held",
    )
    assert (compression.entry_trigger, compression.invalid_if, compression.rank_reason) == (
        "compression_range_breakout_release",
        "price_returns_inside_compression_range",
        "range and ATR compression released into a directional breakout",
    )
    assert (trend.entry_trigger, trend.invalid_if, trend.rank_reason) == (
        "trend_pullback_hold_resume",
        "pullback_breaks_anchor",
        "established trend resumed after a controlled pullback",
    )


def test_enriched_phase2_artifacts_keep_real_confirmation_separate_from_raw_thesis():
    report = build_candidate_pool_report(
        _primary_context(),
        _regime(),
        candidate_generators=get_default_candidate_generators(),
    )

    directional = [candidate for candidate in report.candidates if candidate.direction in {"BUY_CALL", "BUY_PUT"}]
    assert [candidate.strategy_id for candidate in directional] == [
        "opening_range_retest_v1",
        "compression_breakout_v1",
        "trend_pullback_v1",
    ]
    assert len(report.option_confirmations) == 3
    assert all(isinstance(item, CandidateOptionConfirmation) for item in report.option_confirmations)
    assert all(item.confirmation_score == pytest.approx(0.81475) for item in report.option_confirmations)
    assert all("option" not in candidate.rank_reason.lower() for candidate in directional)
    assert all(candidate.evidence["option_confirmation_truth"]["confirmation_score"] == pytest.approx(0.81475) for candidate in directional)
    assert all(candidate.option_confirmation_score == pytest.approx(0.81475) for candidate in directional)
    assert all(candidate.liquidity_score == pytest.approx(0.86) for candidate in directional)
    assert all(candidate.freshness_score == pytest.approx(0.84) for candidate in directional)


def test_primary_strategy_score_reconciliation_is_exact():
    regime = _regime()
    candidates = (
        generate_opening_range_retest_candidates(_primary_context(), regime)
        + generate_compression_breakout_candidates(_primary_context(), regime)
        + generate_trend_pullback_candidates(_primary_context(), regime)
    )
    expected = {
        "opening_range_retest_v1": {
            "setup_score": 0.328053,
            "legacy_score": 0.639513,
            "removed_downstream": 0.448,
            "legacy_setup_slice": 0.191513,
            "delta": 0.31146,
        },
        "compression_breakout_v1": {
            "setup_score": 0.470676,
            "legacy_score": 0.675169,
            "removed_downstream": 0.448,
            "legacy_setup_slice": 0.227169,
            "delta": 0.204493,
        },
        "trend_pullback_v1": {
            "setup_score": 0.648584,
            "legacy_score": 0.719646,
            "removed_downstream": 0.448,
            "legacy_setup_slice": 0.271646,
            "delta": 0.071062,
        },
    }

    for candidate in candidates:
        legacy_score, components = _legacy_mixed_score(candidate, regime)
        values = expected[candidate.strategy_id]
        assert candidate.raw_score == pytest.approx(candidate.price_structure_score)
        assert round(candidate.raw_score, 6) == values["setup_score"]
        assert round(legacy_score, 6) == values["legacy_score"]
        assert round(
            components["option_confirmation_weighted"]
            + components["liquidity_weighted"]
            + components["freshness_weighted"],
            6,
        ) == values["removed_downstream"]
        assert round(
            components["price_structure_weighted"] + components["regime_alignment_weighted"],
            6,
        ) == values["legacy_setup_slice"]
        assert round(legacy_score - candidate.raw_score, 6) == values["delta"]


def test_execution_eligibility_does_not_bypass_manual_approval_or_risk() -> None:
    report = build_candidate_pool_report(
        _primary_context(),
        _regime(),
        candidate_generators=get_default_candidate_generators(),
    )
    candidate = next(item for item in report.candidates if item.strategy_id == "opening_range_retest_v1")
    assert candidate.executable_eligible is True

    original_manual = cfg.MANUAL_APPROVAL
    original_mode = cfg.EXECUTION_MODE
    try:
        cfg.MANUAL_APPROVAL = True
        cfg.EXECUTION_MODE = "PAPER"
        approved, reason = must_have_valid_approval("phase2-eligible-without-approval")
    finally:
        cfg.MANUAL_APPROVAL = original_manual
        cfg.EXECUTION_MODE = original_mode

    assert approved is False
    assert reason.startswith("manual_approval_required:")

    class _RiskState:
        def approve(self, _trade):
            return False, "risk_blocked_for_test"

    class _Survival:
        def evaluate(self, **_kwargs):
            return type("Decision", (), {"allowed_entries": True, "context": {}, "size_multiplier": 1.0})()

    trade = type(
        "TradeStub",
        (),
        {
            "execution_allowed": True,
            "tradable": True,
            "tradable_reasons_blocking": [],
            "planning_only": False,
            "confidence": 0.95,
            "capital_at_risk": 10.0,
            "strategy": "opening_range_retest_v1",
        },
    )()
    decision = ExecutionGuard(risk_state=_RiskState(), survival_gates=_Survival()).evaluate(
        trade,
        {"capital": 1_000.0},
        regime="TREND_UP",
        mode="SIM",
        market_data={"market_context": {"execution_mode": "SIM"}, "market_open": True},
    )
    assert decision.allowed is False
    assert decision.reason == "RiskState: risk_blocked_for_test"


def test_regression_boundaries_remain_intact(caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch):
    ctx = _strategy_context_from_market_symbol("NIFTY", _runtime_truth_payload())
    assert ctx.vwap == 22540.0
    assert ctx.orb_high == 22600.0
    assert ctx.option_ce_ltp == 120.0

    thread_starts: list[str] = []

    def _fail_connection(*_args, **_kwargs):
        raise AssertionError("semantic ownership checks must not open network connections")

    original_thread_start = threading.Thread.start

    def _record_thread_start(self: threading.Thread):
        thread_starts.append(self.name)
        raise AssertionError("semantic ownership checks must not start threads")

    monkeypatch.setattr(socket, "create_connection", _fail_connection)
    monkeypatch.setattr(threading.Thread, "start", _record_thread_start)

    try:
        with caplog.at_level(logging.WARNING):
            report = build_candidate_pool_report(
                _primary_context(vwap=None),
                _regime(),
                candidate_generators=get_default_candidate_generators(),
            )
    finally:
        monkeypatch.setattr(threading.Thread, "start", original_thread_start)

    assert report.failed_generator_count == 0
    assert any("event=STRATEGY_EVIDENCE_BLOCKED" in record.message for record in caplog.records)
    assert thread_starts == []
