from __future__ import annotations

import json

from core.regime_state import REGIME_BULL_TREND, REGIME_RANGE_BOUND
from core.strategy_candidate_pool import (
    CANDIDATE_POOL_ELIGIBILITY_INVALID,
    CANDIDATE_POOL_EMPTY,
    CANDIDATE_POOL_INPUT_MISSING,
    CANDIDATE_POOL_REGISTRY_INVALID,
    CANDIDATE_POOL_STRATEGY_INELIGIBLE,
    STRATEGY_CANDIDATE_POOL_SOURCE,
    build_strategy_candidate_pool,
)
from core.strategy_eligibility import evaluate_strategy_eligibility
from core.strategy_hypothesis_contracts import StrategyHypothesisContract, build_strategy_hypothesis_registry
from core.strategy_spec import DIRECTION_BUY_CALL, DIRECTION_BUY_PUT, FAMILY_VWAP, StrategySpec


def _spec(strategy_id="sample_strategy", instruments=("NIFTY",)):
    return StrategySpec(
        strategy_id=strategy_id,
        name="Sample Strategy",
        family=FAMILY_VWAP,
        module_path="strategies.sample",
        callable_name="generate_signal",
        instruments=instruments,
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
        "thesis": "Sample strategy candidate pool requires eligibility proof.",
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


def test_candidate_pool_builds_one_candidate_per_eligible_strategy_instrument():
    report = build_strategy_candidate_pool(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec(instruments=("BANKNIFTY", "NIFTY"))],
    )

    assert report.valid is True
    assert report.blockers == ()
    assert report.candidate_ids == (
        "sample_strategy:banknifty:buy_call:bull_trend",
        "sample_strategy:nifty:buy_call:bull_trend",
    )
    assert report.excluded_strategy_ids == ()
    assert report.get("sample-strategy:nifty:buy-call:bull-trend").strategy_id == "sample_strategy"


def test_candidate_pool_payload_is_read_only_non_action_and_not_ranked():
    report = build_strategy_candidate_pool(
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
    assert payload["source"] == STRATEGY_CANDIDATE_POOL_SOURCE
    assert payload["metadata"]["does_not_import_strategy_modules"] is True
    assert payload["metadata"]["does_not_execute_strategy_callables"] is True
    assert payload["metadata"]["does_not_rank_candidates"] is True
    assert payload["metadata"]["does_not_score_edge"] is True
    assert payload["candidates"][0]["is_order_action"] is False
    assert payload["candidates"][0]["broker_api_called"] is False


def test_candidate_pool_excludes_ineligible_strategies_without_creating_candidates():
    report = build_strategy_candidate_pool(
        regime=REGIME_RANGE_BOUND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec("first_strategy"), _spec("second_strategy")],
        hypothesis_registry=build_strategy_hypothesis_registry(
            [_spec("first_strategy"), _spec("second_strategy")],
            [
                _contract(strategy_id="first_strategy", hypothesis_id="first_strategy_hypothesis_v1"),
                _contract(
                    strategy_id="second_strategy",
                    hypothesis_id="second_strategy_hypothesis_v1",
                    expected_regimes=(REGIME_BULL_TREND,),
                ),
            ],
        ),
    )

    assert report.valid is True
    assert report.candidate_ids == ("first_strategy:nifty:buy_call:range_bound",)
    assert report.excluded_strategy_ids == ("second_strategy",)
    assert CANDIDATE_POOL_STRATEGY_INELIGIBLE in report.warnings


def test_candidate_pool_blocks_when_eligibility_report_is_invalid():
    eligibility = evaluate_strategy_eligibility(
        regime="",
        direction="",
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
    )

    report = build_strategy_candidate_pool(
        regime="",
        direction="",
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
        eligibility_report=eligibility,
    )

    assert report.valid is False
    assert report.candidate_ids == ()
    assert CANDIDATE_POOL_INPUT_MISSING in report.blockers
    assert CANDIDATE_POOL_ELIGIBILITY_INVALID in report.blockers


def test_candidate_pool_blocks_invalid_strategy_registry():
    report = build_strategy_candidate_pool(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[_spec("duplicate"), _spec("duplicate")],
    )

    assert report.valid is False
    assert report.candidate_ids == ()
    assert CANDIDATE_POOL_REGISTRY_INVALID in report.blockers
    assert CANDIDATE_POOL_ELIGIBILITY_INVALID in report.blockers


def test_candidate_pool_warns_when_no_strategy_is_eligible_but_report_is_valid():
    report = build_strategy_candidate_pool(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=("market_state",),
        market_state_confidence=0.75,
        strategy_registry=[_spec()],
    )

    assert report.valid is True
    assert report.candidate_ids == ()
    assert report.excluded_strategy_ids == ("sample_strategy",)
    assert CANDIDATE_POOL_EMPTY in report.warnings
    assert CANDIDATE_POOL_STRATEGY_INELIGIBLE in report.warnings


def test_candidate_pool_does_not_import_strategy_modules_or_execute_callables():
    report = build_strategy_candidate_pool(
        regime=REGIME_BULL_TREND,
        direction=DIRECTION_BUY_CALL,
        evidence_keys=_evidence_keys(),
        market_state_confidence=0.75,
        strategy_registry=[
            _spec().__class__(
                strategy_id="dangerous_strategy",
                name="Dangerous Strategy",
                family=FAMILY_VWAP,
                module_path="strategies.module_that_must_not_be_imported",
                callable_name="function_that_must_not_run",
                instruments=("NIFTY",),
                declared_regimes=(REGIME_BULL_TREND,),
                blocked_regimes=("UNKNOWN", "OUT_OF_SESSION", "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"),
                required_market_state_dimensions=("trend", "volatility", "breadth", "liquidity", "session"),
                required_evidence_keys=("market_state", "regime_state", "feed_health_truth", "quote_truth"),
                direction_capabilities=(DIRECTION_BUY_CALL,),
                min_market_state_confidence=0.6,
            )
        ],
    )

    assert report.valid is True
    candidate = report.get("dangerous_strategy:nifty:buy_call:bull_trend")
    assert candidate.module_path == "strategies.module_that_must_not_be_imported"
    assert candidate.callable_name == "function_that_must_not_run"
    assert candidate.is_order_action is False
    assert candidate.broker_api_called is False
