# Edge-purpose tests for candidate-pool orchestrator truth preservation.
from __future__ import annotations

import pytest

from core.candidate_pool_orchestrator import build_candidate_pool_report
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult


pytestmark = [pytest.mark.behavior, pytest.mark.edge, pytest.mark.regression]


def _regime(primary="TREND_UP", **scores):
    base = {
        "TREND_UP": 0.0,
        "TREND_DOWN": 0.0,
        "RANGE": 0.0,
        "CHOP": 0.0,
        "COMPRESSION": 0.0,
        "VOLATILITY_EXPANSION": 0.0,
        "TRAP_RISK": 0.0,
        "EXHAUSTION_RISK": 0.0,
        "EXPIRY_CONTEXT": 0.0,
        "INCONCLUSIVE": 0.0,
    }
    base.update(scores)
    return MovementRegimeResult(schema_version=1, primary_regime=primary, scores=base)


def _context(**overrides):
    payload = {
        "symbol": "NIFTY",
        "spot_ltp": 22550.0,
        "vwap": 22500.0,
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
        "ce_premium_change": 14.0,
        "pe_premium_change": -2.0,
        "ce_spread_pct": 0.8,
        "pe_spread_pct": 0.9,
        "ce_depth": 1200.0,
        "pe_depth": 1000.0,
        "option_ltp_age_sec": 0.4,
        "quote_source": "live_option_tick",
        "fallback_used": False,
    }
    payload.update(overrides)
    return StrategyContext(**payload)


def _candidate(
    *,
    strategy_id: str,
    direction: str,
    status: str = "VALIDATED_CANDIDATE",
    blockers=(),
    warnings=(),
):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=strategy_id,
        movement_type="COMPRESSION_BREAKOUT",
        symbol="NIFTY",
        direction=direction,
        status=status,
        raw_score=0.7,
        confidence_score=0.7,
        price_structure_score=0.7,
        option_confirmation_score=0.7,
        liquidity_score=0.8,
        freshness_score=0.9,
        volatility_score=0.5,
        regime_alignment_score=0.7,
        entry_trigger="unit",
        invalid_if="unit",
        rank_reason="unit",
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


def test_candidate_pool_orchestrator_preserves_validated_and_blocked_candidates():
    """
    Edge purpose:
    Proves the orchestrator keeps visible truth for both usable and blocked candidates.
    Bug/risk protected:
    Rejected candidates disappearing before no-trade and dashboard evidence can explain why.
    Expected behavior:
    Blocked rows remain in the report and feed blocker metadata.
    """

    def generator(ctx, regime):
        return (
            _candidate(strategy_id="validated_breakout", direction="BUY_CALL"),
            _candidate(
                strategy_id="blocked_breakout",
                direction="BUY_PUT",
                status="BLOCKED_CANDIDATE",
                blockers=("FALLBACK_QUOTE_ONLY", "STALE_OPTION_LTP"),
                warnings=("needs_live_depth",),
            ),
        )

    report = build_candidate_pool_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[generator],
    )

    assert report.read_only is True
    assert report.is_order_action is False
    assert report.candidate_count == 2
    assert report.validated_candidate_count == 1
    assert report.blocked_candidate_count == 1
    assert "FALLBACK_QUOTE_ONLY" in report.blockers
    assert "STALE_OPTION_LTP" in report.blockers
    assert "needs_live_depth" in report.warnings


def test_candidate_pool_orchestrator_warns_on_non_candidate_generator_output():
    """
    Edge purpose:
    Proves malformed strategy output becomes a warning instead of fake candidate truth.
    Bug/risk protected:
    Arbitrary generator payloads masquerading as real strategy candidates.
    Expected behavior:
    Non-candidate returns are ignored and explicitly warned.
    """

    def generator(ctx, regime):
        return (
            _candidate(strategy_id="validated_breakout", direction="BUY_CALL"),
            {"not": "a_strategy_candidate"},
        )

    report = build_candidate_pool_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[generator],
    )

    assert report.candidate_count == 1
    assert report.movement_candidate_count == 1
    assert "strategy_generator_returned_non_candidate:generator" in report.warnings


def test_candidate_pool_orchestrator_can_suppress_without_inventing_no_trade_row():
    """
    Edge purpose:
    Proves report-level suppression can happen without fabricating a synthetic no-trade candidate.
    Bug/risk protected:
    Downstream consumers misreading a synthetic row as a real executable setup.
    Expected behavior:
    Executable count is zero when no-trade is active, even if the synthetic row is omitted.
    """

    def generator(ctx, regime):
        return (_candidate(strategy_id="validated_breakout", direction="BUY_CALL"),)

    report = build_candidate_pool_report(
        _context(quote_source="recovered_fallback", fallback_used=True),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[generator],
        include_no_trade_candidate=False,
    )

    assert report.no_trade_assessment.no_trade is True
    assert report.no_trade_candidate_count == 0
    assert report.eligible_candidate_count_before_suppression == 1
    assert report.report_executable_eligible_count == 0
    assert report.metadata["no_trade_primary_reason"] == report.no_trade_assessment.primary_reason
