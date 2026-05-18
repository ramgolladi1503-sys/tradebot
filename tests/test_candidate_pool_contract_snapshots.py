from __future__ import annotations

import json
from pathlib import Path

from core.candidate_pool_orchestrator import build_candidate_pool_report
from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "candidate_pool_contract"


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


def _candidate(direction="BUY_CALL", blockers=(), warnings=()):
    return StrategyCandidate(
        schema_version=1,
        strategy_id=f"unit_{direction.lower()}",
        movement_type="COMPRESSION_BREAKOUT",
        symbol="NIFTY",
        direction=direction,
        status="VALIDATED_CANDIDATE" if not blockers else "BLOCKED_CANDIDATE",
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
        blockers=blockers,
        warnings=warnings,
    )


def _load_snapshot(name: str) -> dict:
    path = FIXTURE_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_summary(candidate) -> dict:
    return {
        "strategy_id": candidate.strategy_id,
        "movement_type": candidate.movement_type,
        "direction": candidate.direction,
        "status": candidate.status,
        "executable_eligible": candidate.executable_eligible,
        "blockers": sorted(candidate.blockers),
        "warnings": sorted(candidate.warnings),
    }


def _confirmation_summary(confirmation) -> dict:
    return {
        "candidate_strategy_id": confirmation.candidate_strategy_id,
        "candidate_direction": confirmation.candidate_direction,
        "suggested_effect": confirmation.suggested_effect,
        "dominant_direction": confirmation.dominant_direction,
        "blockers": sorted(confirmation.blockers),
        "warnings": sorted(confirmation.warnings),
    }


def _stable_report_summary(report) -> dict:
    return {
        "schema_version": report.schema_version,
        "symbol": report.symbol,
        "read_only": report.read_only,
        "is_order_action": report.is_order_action,
        "append": report.append,
        "candidate_count": report.candidate_count,
        "movement_candidate_count": report.movement_candidate_count,
        "no_trade_candidate_count": report.no_trade_candidate_count,
        "validated_candidate_count": report.validated_candidate_count,
        "blocked_candidate_count": report.blocked_candidate_count,
        "eligible_candidate_count_before_suppression": report.eligible_candidate_count_before_suppression,
        "report_executable_eligible_count": report.report_executable_eligible_count,
        "generator_count": report.generator_count,
        "failed_generator_count": report.failed_generator_count,
        "blockers": sorted(report.blockers),
        "warnings": sorted(report.warnings),
        "metadata": {
            "report_type": report.metadata.get("report_type"),
            "scope": report.metadata.get("scope"),
            "primary_regime": report.metadata.get("primary_regime"),
            "dominant_option_direction": report.metadata.get("dominant_option_direction"),
            "no_trade": report.metadata.get("no_trade"),
            "no_trade_primary_reason": report.metadata.get("no_trade_primary_reason"),
        },
        "option_pressure": {
            "dominant_direction": report.option_pressure.dominant_direction,
            "blockers": sorted(report.option_pressure.blockers),
            "warnings": sorted(report.option_pressure.warnings),
        },
        "no_trade_assessment": {
            "no_trade": report.no_trade_assessment.no_trade,
            "primary_reason": report.no_trade_assessment.primary_reason,
            "signal_reasons": sorted(signal.reason for signal in report.no_trade_assessment.signals),
        },
        "candidates": [_candidate_summary(candidate) for candidate in report.candidates],
        "option_confirmations": [
            _confirmation_summary(confirmation) for confirmation in report.option_confirmations
        ],
    }


def _single_candidate_generator(candidate):
    def _generator(ctx, regime):
        return (candidate,)

    return _generator


def test_clean_candidate_pool_contract_snapshot():
    report = build_candidate_pool_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_single_candidate_generator(_candidate("BUY_CALL"))],
    )

    assert _stable_report_summary(report) == _load_snapshot("clean_report.json")


def test_no_trade_candidate_pool_contract_snapshot():
    report = build_candidate_pool_report(
        _context(),
        _regime(primary="CHOP", CHOP=0.85),
        candidate_generators=[_single_candidate_generator(_candidate("BUY_CALL"))],
    )

    summary = _stable_report_summary(report)

    assert summary == _load_snapshot("no_trade_report.json")
    assert summary["eligible_candidate_count_before_suppression"] == 1
    assert summary["report_executable_eligible_count"] == 0
    assert summary["metadata"]["no_trade"] is True


def test_fallback_blocked_candidate_pool_contract_snapshot():
    report = build_candidate_pool_report(
        _context(
            fallback_used=True,
            quote_source="recovered_fallback",
            option_ltp_age_sec=8.0,
            ce_spread_pct=9.0,
            pe_spread_pct=None,
            ce_depth=None,
            pe_depth=0.0,
            ce_premium_change=0.0,
            pe_premium_change=0.0,
        ),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[
            _single_candidate_generator(
                _candidate(
                    "BUY_CALL",
                    blockers=(
                        "FALLBACK_QUOTE_ONLY",
                        "MISSING_DEPTH",
                        "STALE_OPTION_LTP",
                        "WIDE_SPREAD",
                    ),
                    warnings=("depth_missing",),
                )
            )
        ],
    )

    summary = _stable_report_summary(report)

    assert summary == _load_snapshot("fallback_blocked_report.json")
    assert summary["read_only"] is True
    assert summary["is_order_action"] is False
    assert summary["append"] is False
    assert "FALLBACK_QUOTE_ONLY" in summary["blockers"]
    assert summary["report_executable_eligible_count"] == 0


def test_candidate_pool_contract_required_top_level_keys_are_stable():
    report = build_candidate_pool_report(
        _context(),
        _regime(primary="TREND_UP", TREND_UP=0.8),
        candidate_generators=[_single_candidate_generator(_candidate("BUY_CALL"))],
    )

    payload = report.to_dict()

    assert set(payload) >= {
        "schema_version",
        "symbol",
        "read_only",
        "is_order_action",
        "append",
        "regime",
        "option_pressure",
        "no_trade_assessment",
        "candidates",
        "option_confirmations",
        "blockers",
        "warnings",
        "candidate_count",
        "movement_candidate_count",
        "no_trade_candidate_count",
        "eligible_candidate_count_before_suppression",
        "report_executable_eligible_count",
        "metadata",
    }
    assert payload["schema_version"] == 1
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["metadata"]["scope"] == "read_only_no_execution_no_ranking"
