from __future__ import annotations

import json

from core.regime_state import REGIME_BULL_TREND, REGIME_RANGE_BOUND
from core.strategy_hypothesis_contracts import (
    HYPOTHESIS_DIRECTION_MISMATCH,
    HYPOTHESIS_DUPLICATE_ID,
    HYPOTHESIS_INVALID_THRESHOLD,
    HYPOTHESIS_MISSING_CONTRACT,
    HYPOTHESIS_MISSING_EVIDENCE,
    HYPOTHESIS_MISSING_INVALIDATION_RULE,
    HYPOTHESIS_MISSING_OUTCOME_METRIC,
    HYPOTHESIS_REGIME_MISMATCH,
    HYPOTHESIS_STATUS_BLOCK,
    STRATEGY_HYPOTHESIS_SOURCE,
    StrategyHypothesisContract,
    build_default_strategy_hypothesis_contracts,
    build_strategy_hypothesis_registry,
    get_strategy_hypothesis_contract,
)
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
        description="Sample quality metadata",
    )


def _contract(**overrides):
    values = {
        "strategy_id": "sample_strategy",
        "hypothesis_id": "sample_strategy_hypothesis_v1",
        "title": "Sample hypothesis",
        "thesis": "Sample strategy needs paper-truth proof before promotion.",
        "expected_regimes": (REGIME_BULL_TREND, REGIME_RANGE_BOUND),
        "direction_capabilities": (DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
        "required_evidence_keys": (
            "market_state",
            "regime_state",
            "feed_health_truth",
            "quote_truth",
            "strategy_quality_audit",
            "paper_outcome_journal",
        ),
        "outcome_metrics": ("expectancy_r", "sample_size", "win_rate"),
        "invalidation_reasons": ("negative_expectancy", "insufficient_sample_size"),
        "min_sample_size": 30,
        "min_expectancy_r": 0.05,
        "max_drawdown_r": 3.0,
    }
    values.update(overrides)
    return StrategyHypothesisContract(**values)


def test_default_hypothesis_registry_is_read_only_and_non_action():
    registry = build_strategy_hypothesis_registry([_spec()])
    payload = json.loads(registry.to_json())

    assert registry.valid is True
    assert registry.read_only is True
    assert registry.append is False
    assert registry.is_order_action is False
    assert registry.broker_api_called is False
    assert registry.source == STRATEGY_HYPOTHESIS_SOURCE
    assert registry.blockers == ()
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["does_not_import_strategy_modules"] is True
    assert payload["metadata"]["does_not_execute_strategy_callables"] is True
    assert "selected_strategy" not in payload
    assert "eligible_strategies" not in payload


def test_default_contracts_are_derived_from_strategy_specs_without_execution():
    contracts = build_default_strategy_hypothesis_contracts([_spec(strategy_id="derived_strategy")])

    assert sum(1 for contract in contracts if contract.strategy_id == "derived_strategy") == 1
    contract = contracts[0]
    assert contract.hypothesis_id == "derived_strategy_hypothesis_v1"
    assert contract.is_order_action is False
    assert contract.broker_api_called is False
    assert "paper_outcome_journal" in contract.required_evidence_keys
    assert "strategy_quality_audit" in contract.required_evidence_keys


def test_hypothesis_lookup_normalizes_ids():
    registry = build_strategy_hypothesis_registry([_spec(strategy_id="sample_strategy")])

    assert get_strategy_hypothesis_contract("sample-strategy", registry).strategy_id == "sample_strategy"
    assert get_strategy_hypothesis_contract("missing", registry) is None


def test_hypothesis_registry_blocks_missing_contract_for_strategy():
    registry = build_strategy_hypothesis_registry([_spec()], contracts=[])

    assert registry.valid is False
    assert HYPOTHESIS_MISSING_CONTRACT in registry.blockers


def test_hypothesis_registry_blocks_duplicate_hypothesis_and_strategy_ids():
    registry = build_strategy_hypothesis_registry([_spec()], contracts=[_contract(), _contract()])

    assert registry.valid is False
    assert HYPOTHESIS_DUPLICATE_ID in registry.blockers


def test_hypothesis_registry_blocks_regime_direction_and_evidence_mismatch():
    registry = build_strategy_hypothesis_registry(
        [_spec()],
        contracts=[
            _contract(
                expected_regimes=("BEAR_TREND",),
                direction_capabilities=("PUT",),
                required_evidence_keys=("market_state",),
            )
        ],
    )

    assert registry.valid is False
    assert HYPOTHESIS_REGIME_MISMATCH in registry.blockers
    assert HYPOTHESIS_DIRECTION_MISMATCH in registry.blockers
    assert HYPOTHESIS_MISSING_EVIDENCE in registry.blockers


def test_hypothesis_registry_blocks_missing_outcome_metric_and_invalidation_rule():
    registry = build_strategy_hypothesis_registry(
        [_spec()],
        contracts=[
            _contract(
                outcome_metrics=("expectancy_r",),
                invalidation_reasons=(),
            )
        ],
    )

    assert registry.valid is False
    assert HYPOTHESIS_MISSING_OUTCOME_METRIC in registry.blockers
    assert HYPOTHESIS_MISSING_INVALIDATION_RULE in registry.blockers


def test_hypothesis_registry_blocks_invalid_thresholds():
    registry = build_strategy_hypothesis_registry(
        [_spec()],
        contracts=[_contract(min_sample_size=0, min_expectancy_r=99.0, max_drawdown_r=0.0)],
    )

    assert registry.valid is False
    assert HYPOTHESIS_INVALID_THRESHOLD in registry.blockers


def test_hypothesis_contract_payload_is_non_action():
    contract = _contract()
    payload = contract.to_payload()

    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["read_only"] is True
    assert payload["append"] is False


def test_hypothesis_registry_marks_blocking_issues_with_contract_context():
    registry = build_strategy_hypothesis_registry(
        [_spec()],
        contracts=[_contract(outcome_metrics=("win_rate",))],
    )

    assert registry.valid is False
    assert any(issue.severity == HYPOTHESIS_STATUS_BLOCK for issue in registry.issues)
    assert any(issue.hypothesis_id == "sample_strategy_hypothesis_v1" for issue in registry.issues)
