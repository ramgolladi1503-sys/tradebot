from __future__ import annotations

import json

from core.regime_state import REGIME_BULL_TREND, REGIME_RANGE_BOUND
from core.strategy_eligibility import (
    ELIGIBILITY_CONFIDENCE_TOO_LOW,
    ELIGIBILITY_DIRECTION_MISMATCH,
    ELIGIBILITY_EVIDENCE_MISSING,
    ELIGIBILITY_HYPOTHESIS_INVALID,
    ELIGIBILITY_INPUT_MISSING,
    ELIGIBILITY_REGIME_MISMATCH,
    ELIGIBILITY_STATUS_ELIGIBLE,
    ELIGIBILITY_STATUS_REJECTED,
    evaluate_strategy_eligibility,
)
from core.strategy_hypothesis_contracts import StrategyHypothesisContract, build_strategy_hypothesis_registry
from core.strategy_spec import DIRECTION_BUY_CALL, DIRECTION_BUY_PUT, FAMILY_VWAP, StrategySpec


def _spec(strategy_id="sample_strategy"):
    return StrategySpec(
        strategy_id=strategy_id,
        name="Sample Strategy",
        family=FAMILY_VWAP,
        module_path="strategies.sample",
        callable_name="generate_signal",
        instruments=("NIFTY",),
        declared_regimes=(REGIME_BULL_TREND, REGIME_RANGE_BOUND),
        blocked_regimes=("UNKNOWN", "OUT_OF_SESSION", "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"),
        required_market_state_dimensions=("trend", "volatility", "breadth", "liquidity", "session"),
        required_evidence_keys=("market_state", "regime_state", "feed_health_truth", "quote_truth"),
        direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
        min_market_state_confidence=0.6,
        description="Sample metadata",
    )


def _evidence_keys():
    return (
        "market_state",
        "regime_state",
        "feed_health_truth",
        "quote_truth",
        "strategy_quality_audit",
        "paper_outcome_journal",
    )


def _contract(**overrides):
    values = {
        "strategy_id": "sample_strategy",
        "hypothesis_id": "sample_strategy_hypothesis_v1",
        "title": "Sample hypothesis",
        "thesis": "Sample strategy eligibility requires matching contracts.",
        "expected_regimes": (REGIME_BULL_TREND, REGIME_RANGE_BOUND),
        "direction_capabilities": (DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
        "required_evidence_keys": _evidence_keys(),
        "outcome_metrics": ("expectancy_r", "sample_size", "win_rate"),
        "invalidation_reasons": ("negative_expectancy", "insufficient_sample_size"),
        "min_sample_size": 30,
        "min_expectancy_r": 0.05,
        "max_drawdown_r": 3.0,
    }
    values.update(overrides)
    return StrategyHypothesisContract(**values)


def test_strategy_eligibility_accepts_contract_matching_strategy():
    report = evaluate_strategy_eligibility(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
    )

    assert report.valid is True
    assert report.blockers == ()
    assert report.eligible_strategy_ids == ("sample_strategy",)
    assert report.get("sample-strategy").status == ELIGIBILITY_STATUS_ELIGIBLE
    assert report.get("sample_strategy").eligible is True


def test_strategy_eligibility_payload_is_read_only_and_non_action():
    report = evaluate_strategy_eligibility(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
    )
    payload = json.loads(report.to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["does_not_import_strategy_modules"] is True
    assert payload["metadata"]["does_not_execute_strategy_callables"] is True
    assert payload["decisions"][0]["is_order_action"] is False
    assert payload["decisions"][0]["broker_api_called"] is False


def test_strategy_eligibility_rejects_regime_mismatch():
    report = evaluate_strategy_eligibility(
        regime="BEAR_TREND",
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
    )

    decision = report.get("sample_strategy")
    assert decision.status == ELIGIBILITY_STATUS_REJECTED
    assert decision.eligible is False
    assert ELIGIBILITY_REGIME_MISMATCH in decision.blockers


def test_strategy_eligibility_rejects_direction_mismatch():
    report = evaluate_strategy_eligibility(
        regime=REGIME_BULL_TREND,
        direction="PUT",
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
    )

    decision = report.get("sample_strategy")
    assert decision.status == ELIGIBILITY_STATUS_REJECTED
    assert ELIGIBILITY_DIRECTION_MISMATCH in decision.blockers


def test_strategy_eligibility_rejects_missing_evidence():
    report = evaluate_strategy_eligibility(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=("market_state",),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
    )

    decision = report.get("sample_strategy")
    assert decision.eligible is False
    assert ELIGIBILITY_EVIDENCE_MISSING in decision.blockers
    assert any(reason == "missing_evidence:quote_truth" for reason in decision.reasons)


def test_strategy_eligibility_rejects_low_market_state_confidence():
    report = evaluate_strategy_eligibility(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.1,
        strategy_registry=[_spec()],
    )

    decision = report.get("sample_strategy")
    assert decision.eligible is False
    assert ELIGIBILITY_CONFIDENCE_TOO_LOW in decision.blockers


def test_strategy_eligibility_blocks_invalid_hypothesis_registry():
    hypothesis_registry = build_strategy_hypothesis_registry(
        [_spec()],
        contracts=[_contract(outcome_metrics=("win_rate",))],
    )
    report = evaluate_strategy_eligibility(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
        hypothesis_registry=hypothesis_registry,
    )

    assert report.valid is False
    assert ELIGIBILITY_HYPOTHESIS_INVALID in report.blockers


def test_strategy_eligibility_blocks_missing_input():
    report = evaluate_strategy_eligibility(
        regime="",
        direction="",
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
    )

    assert report.valid is False
    assert ELIGIBILITY_INPUT_MISSING in report.blockers
    assert ELIGIBILITY_INPUT_MISSING in report.get("sample_strategy").blockers


def test_strategy_eligibility_can_filter_multiple_strategies_without_hardcoded_names():
    first = _spec("first_strategy")
    second = _spec("second_strategy")
    second_contract = _contract(
        strategy_id="second_strategy",
        hypothesis_id="second_strategy_hypothesis_v1",
        expected_regimes=(REGIME_RANGE_BOUND,),
    )
    first_contract = _contract(
        strategy_id="first_strategy",
        hypothesis_id="first_strategy_hypothesis_v1",
    )
    hypothesis_registry = build_strategy_hypothesis_registry([first, second], [first_contract, second_contract])

    report = evaluate_strategy_eligibility(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[first, second],
        hypothesis_registry=hypothesis_registry,
    )

    assert report.eligible_strategy_ids == ("first_strategy",)
    assert report.get("second_strategy").eligible is False
    assert ELIGIBILITY_REGIME_MISMATCH in report.get("second_strategy").blockers
