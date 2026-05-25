from __future__ import annotations

import json

from core.regime_state import REGIME_BULL_TREND, REGIME_OUT_OF_SESSION, REGIME_UNKNOWN
from core.strategy_spec import (
    DIRECTION_BUY_CALL,
    DIRECTION_BUY_PUT,
    FAMILY_VWAP,
    STRATEGY_SPEC_DUPLICATE_ID,
    STRATEGY_SPEC_EMPTY_REGISTRY,
    STRATEGY_SPEC_MISSING_FIELD,
    STRATEGY_SPEC_UNKNOWN_REGIME,
    STRATEGY_SPEC_UNSAFE_EVIDENCE,
    STRATEGY_SPEC_UNSAFE_REGIME,
    StrategySpec,
    build_default_strategy_specs,
    build_strategy_spec_registry,
    get_strategy_spec,
)


def _valid_spec(strategy_id="sample_strategy"):
    return StrategySpec(
        strategy_id=strategy_id,
        name="Sample Strategy",
        family=FAMILY_VWAP,
        module_path="strategies.sample",
        callable_name="generate_signal",
        instruments=("NIFTY",),
        declared_regimes=(REGIME_BULL_TREND,),
        blocked_regimes=(REGIME_UNKNOWN, REGIME_OUT_OF_SESSION, "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"),
        required_market_state_dimensions=("trend", "volatility", "breadth", "liquidity", "session"),
        required_evidence_keys=("market_state", "regime_state", "feed_health_truth", "quote_truth"),
        direction_capabilities=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
        min_market_state_confidence=0.6,
        description="Test-only metadata",
    )


def test_default_strategy_spec_registry_is_read_only_and_valid():
    registry = build_strategy_spec_registry()

    assert registry.read_only is True
    assert registry.append is False
    assert registry.is_order_action is False
    assert registry.broker_api_called is False
    assert registry.valid is True
    assert registry.blockers == ()
    assert registry.specs
    assert "ensemble" in registry.strategy_ids()
    assert "nifty_intraday" in registry.strategy_ids()
    assert "banknifty_intraday" in registry.strategy_ids()
    assert registry.metadata["scope"] == "read_only_strategy_spec_registry_no_eligibility_replacement"
    assert registry.metadata["does_not_import_strategy_modules"] is True


def test_strategy_spec_lookup_normalizes_ids_without_executing_strategy_code():
    registry = build_strategy_spec_registry()

    spec = get_strategy_spec("NIFTY-INTRADAY", registry)

    assert spec is not None
    assert spec.strategy_id == "nifty_intraday"
    assert spec.module_path == "strategies.nifty_intraday"
    assert spec.callable_name == "generate_signal"


def test_strategy_spec_registry_serializes_non_action_contract():
    registry = build_strategy_spec_registry([_valid_spec()])
    payload = json.loads(registry.to_json())

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["valid"] is True
    assert payload["spec_count"] == 1
    assert payload["specs"][0]["read_only"] is True
    assert payload["specs"][0]["is_order_action"] is False
    assert "selected_strategy" not in payload
    assert "eligible_strategies" not in payload


def test_strategy_spec_registry_blocks_duplicate_strategy_ids():
    registry = build_strategy_spec_registry([_valid_spec("dup"), _valid_spec("dup")])

    assert registry.valid is False
    assert STRATEGY_SPEC_DUPLICATE_ID in registry.blockers
    assert any(issue.strategy_id == "dup" for issue in registry.issues)


def test_strategy_spec_registry_blocks_empty_and_missing_required_fields():
    empty = build_strategy_spec_registry([])
    missing = build_strategy_spec_registry(
        [
            {
                "strategy_id": "broken",
                "name": "Broken",
                "family": "VWAP",
                "module_path": "",
                "callable_name": "",
                "instruments": [],
                "declared_regimes": [],
                "direction_capabilities": [],
            }
        ]
    )

    assert empty.valid is False
    assert STRATEGY_SPEC_EMPTY_REGISTRY in empty.blockers
    assert missing.valid is False
    assert STRATEGY_SPEC_MISSING_FIELD in missing.blockers


def test_strategy_spec_registry_blocks_unknown_and_unsafe_declared_regimes():
    unknown = build_strategy_spec_registry(
        [
            _valid_spec(),
            {
                "strategy_id": "bad_regime",
                "name": "Bad Regime",
                "family": "VWAP",
                "module_path": "strategies.bad",
                "callable_name": "generate_signal",
                "instruments": ["NIFTY"],
                "declared_regimes": ["NOT_A_REAL_REGIME"],
                "blocked_regimes": [REGIME_UNKNOWN, REGIME_OUT_OF_SESSION, "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"],
                "direction_capabilities": [DIRECTION_BUY_CALL],
            },
        ]
    )
    unsafe = build_strategy_spec_registry(
        [
            {
                "strategy_id": "unsafe_regime",
                "name": "Unsafe Regime",
                "family": "VWAP",
                "module_path": "strategies.unsafe",
                "callable_name": "generate_signal",
                "instruments": ["NIFTY"],
                "declared_regimes": [REGIME_UNKNOWN],
                "blocked_regimes": [REGIME_UNKNOWN, REGIME_OUT_OF_SESSION, "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"],
                "direction_capabilities": [DIRECTION_BUY_CALL],
            }
        ]
    )

    assert STRATEGY_SPEC_UNKNOWN_REGIME in unknown.blockers
    assert STRATEGY_SPEC_UNSAFE_REGIME in unsafe.blockers


def test_strategy_spec_registry_warns_when_unsafe_regimes_are_not_explicitly_blocked():
    spec = _valid_spec()
    weak_spec = StrategySpec(
        strategy_id=spec.strategy_id,
        name=spec.name,
        family=spec.family,
        module_path=spec.module_path,
        callable_name=spec.callable_name,
        instruments=spec.instruments,
        declared_regimes=spec.declared_regimes,
        blocked_regimes=(),
        required_market_state_dimensions=spec.required_market_state_dimensions,
        required_evidence_keys=spec.required_evidence_keys,
        direction_capabilities=spec.direction_capabilities,
        min_market_state_confidence=spec.min_market_state_confidence,
    )

    registry = build_strategy_spec_registry([weak_spec])

    assert registry.valid is True
    assert STRATEGY_SPEC_UNSAFE_REGIME in registry.warnings
    assert registry.blockers == ()


def test_strategy_spec_registry_blocks_missing_market_state_dimensions_and_warns_on_evidence_keys():
    spec = StrategySpec(
        strategy_id="weak_evidence",
        name="Weak Evidence",
        family=FAMILY_VWAP,
        module_path="strategies.weak",
        callable_name="generate_signal",
        instruments=("NIFTY",),
        declared_regimes=(REGIME_BULL_TREND,),
        blocked_regimes=(REGIME_UNKNOWN, REGIME_OUT_OF_SESSION, "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"),
        required_market_state_dimensions=("trend", "volatility"),
        required_evidence_keys=("market_state",),
        direction_capabilities=(DIRECTION_BUY_CALL,),
    )

    registry = build_strategy_spec_registry([spec])

    assert registry.valid is False
    assert STRATEGY_SPEC_UNSAFE_EVIDENCE in registry.blockers
    assert STRATEGY_SPEC_UNSAFE_EVIDENCE in registry.warnings


def test_default_specs_are_metadata_only_and_cover_known_strategy_modules():
    specs = build_default_strategy_specs()
    payloads = [spec.to_payload() for spec in specs]

    assert {payload["module_path"] for payload in payloads} >= {
        "strategies.ensemble",
        "strategies.nifty_intraday",
        "strategies.banknifty_intraday",
        "strategies.sensex_intraday",
        "strategies.zero_hero",
    }
    assert all(payload["read_only"] is True for payload in payloads)
    assert all(payload["broker_api_called"] is False for payload in payloads)
