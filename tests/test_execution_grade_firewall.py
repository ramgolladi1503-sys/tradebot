from __future__ import annotations

from core.execution_grade_firewall import assess_execution_grade
from core.movement_contract import StrategyCandidate, StrategyContext


def _candidate(**overrides):
    payload = {
        "schema_version": 1,
        "strategy_id": "candidate",
        "movement_type": "COMPRESSION_BREAKOUT",
        "symbol": "NIFTY",
        "direction": "BUY_CALL",
        "status": "VALIDATED_CANDIDATE",
        "raw_score": 0.75,
        "confidence_score": 0.75,
        "price_structure_score": 0.8,
        "option_confirmation_score": 0.8,
        "liquidity_score": 0.8,
        "freshness_score": 0.9,
        "volatility_score": 0.5,
        "regime_alignment_score": 0.8,
        "timing_score": 0.7,
        "trap_risk_score": 0.05,
        "confluence_score": 0.6,
        "entry_trigger": "unit",
        "invalid_if": "unit",
        "rank_reason": "unit",
        "blockers": (),
        "warnings": (),
    }
    payload.update(overrides)
    return StrategyCandidate(**payload)


def _context(**overrides):
    payload = {
        "symbol": "NIFTY",
        "spot_ltp": 22550.0,
        "option_ce_ltp": 120.0,
        "option_pe_ltp": 90.0,
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


def _exact_contract(**overrides):
    payload = {
        "instrument_token": 12345,
        "tradingsymbol": "NIFTY26MAR22550CE",
        "exchange": "NFO",
        "segment": "NFO-OPT",
        "resolution_path": "exact_contract_match",
        "fallback_candidate": False,
        "candidate_origin": "exact_contract",
        "execution_grade": True,
        "advisory_only": False,
    }
    payload.update(overrides)
    return payload


def test_exact_contract_with_clean_context_is_execution_grade():
    decision = assess_execution_grade(_candidate(), _context(), contract_resolution=_exact_contract())

    assert decision.execution_grade is True
    assert decision.allowed_for_execution is True
    assert decision.allowed_for_paper_execution is True
    assert decision.advisory_only is False
    assert decision.state == "EXECUTION_GRADE"
    assert decision.blockers == ()
    assert decision.is_order_action is False
    assert decision.append is False


def test_safe_nearest_fallback_is_visible_but_advisory_only():
    decision = assess_execution_grade(
        _candidate(),
        _context(),
        contract_resolution=_exact_contract(
            resolution_path="safe_nearest_contract_fallback",
            fallback_candidate=True,
            candidate_origin="fallback",
            execution_grade=False,
            advisory_only=True,
        ),
    )

    assert decision.execution_grade is False
    assert decision.allowed_for_execution is False
    assert decision.allowed_for_paper_execution is False
    assert decision.advisory_only is True
    assert decision.state == "ADVISORY_ONLY"
    assert "FALLBACK_QUOTE_ONLY" in decision.blockers
    assert "safe_nearest_contract_fallback_visible_but_advisory_only" in decision.warnings


def test_unresolved_contract_blocks_fail_closed():
    decision = assess_execution_grade(_candidate(), _context(), contract_resolution=None)

    assert decision.execution_grade is False
    assert decision.allowed_for_execution is False
    assert decision.state == "BLOCKED"
    assert "UNRESOLVED_CONTRACT" in decision.blockers


def test_candidate_hard_blocker_blocks_execution():
    decision = assess_execution_grade(
        _candidate(status="BLOCKED_CANDIDATE", blockers=("WIDE_SPREAD",)),
        _context(),
        contract_resolution=_exact_contract(),
    )

    assert decision.execution_grade is False
    assert decision.state == "BLOCKED"
    assert "WIDE_SPREAD" in decision.blockers
    assert "CANDIDATE_NOT_EXECUTION_ELIGIBLE" in decision.blockers


def test_stale_option_ltp_blocks_execution():
    decision = assess_execution_grade(
        _candidate(),
        _context(option_ltp_age_sec=9.0),
        contract_resolution=_exact_contract(),
        max_option_ltp_age_sec=2.5,
    )

    assert decision.execution_grade is False
    assert decision.state == "BLOCKED"
    assert "STALE_OPTION_LTP" in decision.blockers


def test_wide_spread_blocks_selected_leg():
    decision = assess_execution_grade(
        _candidate(direction="BUY_CALL"),
        _context(ce_spread_pct=9.5, pe_spread_pct=0.5),
        contract_resolution=_exact_contract(),
        max_spread_pct=3.0,
    )

    assert decision.execution_grade is False
    assert "WIDE_SPREAD" in decision.blockers


def test_missing_depth_blocks_selected_leg():
    decision = assess_execution_grade(
        _candidate(direction="BUY_PUT"),
        _context(pe_depth=0.0, ce_depth=1000.0),
        contract_resolution=_exact_contract(),
        min_depth=1.0,
    )

    assert decision.execution_grade is False
    assert "MISSING_DEPTH" in decision.blockers


def test_untrusted_quote_source_is_advisory_only_not_execution_grade():
    decision = assess_execution_grade(
        _candidate(),
        _context(quote_source="recovered_fallback"),
        contract_resolution=_exact_contract(),
    )

    assert decision.execution_grade is False
    assert decision.advisory_only is True
    assert decision.state == "ADVISORY_ONLY"
    assert "QUOTE_SOURCE_UNTRUSTED" in decision.blockers


def test_context_fallback_used_blocks_execution_even_with_exact_contract():
    decision = assess_execution_grade(
        _candidate(),
        _context(fallback_used=True),
        contract_resolution=_exact_contract(),
    )

    assert decision.execution_grade is False
    assert decision.advisory_only is True
    assert "FALLBACK_QUOTE_ONLY" in decision.blockers


def test_to_dict_is_json_friendly_and_stable():
    decision = assess_execution_grade(_candidate(), _context(), contract_resolution=_exact_contract())

    payload = decision.to_dict()

    assert payload["schema_version"] == 1
    assert payload["strategy_id"] == "candidate"
    assert payload["symbol"] == "NIFTY"
    assert payload["state"] == "EXECUTION_GRADE"
    assert payload["blockers"] == []
    assert payload["is_order_action"] is False
    assert payload["append"] is False
