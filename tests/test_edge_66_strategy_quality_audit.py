from __future__ import annotations

import json

from core.regime_state import REGIME_BULL_TREND, REGIME_OUT_OF_SESSION, REGIME_UNKNOWN
from core.strategy_quality_audit import (
    QUALITY_STATUS_BLOCK,
    QUALITY_STATUS_PASS,
    QUALITY_STATUS_WARN,
    STRATEGY_QUALITY_EMPTY_REGISTRY,
    STRATEGY_QUALITY_LOW_CONFIDENCE,
    STRATEGY_QUALITY_MISSING_DESCRIPTION,
    STRATEGY_QUALITY_MISSING_EVIDENCE,
    STRATEGY_QUALITY_NARROW_REGIME_COVERAGE,
    STRATEGY_QUALITY_SINGLE_DIRECTION,
    STRATEGY_QUALITY_UNSAFE_REGIME_NOT_BLOCKED,
    build_strategy_quality_audit,
)
from core.strategy_spec import (
    DIRECTION_BUY_CALL,
    DIRECTION_BUY_PUT,
    FAMILY_VWAP,
    StrategySpec,
    build_strategy_spec_registry,
)


def _spec(
    *,
    strategy_id="sample_strategy",
    declared_regimes=(REGIME_BULL_TREND, "RANGE_BOUND"),
    blocked_regimes=(REGIME_UNKNOWN, REGIME_OUT_OF_SESSION, "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"),
    evidence_keys=("market_state", "regime_state", "feed_health_truth", "quote_truth"),
    directions=(DIRECTION_BUY_CALL, DIRECTION_BUY_PUT),
    confidence=0.6,
    description="Test quality metadata",
):
    return StrategySpec(
        strategy_id=strategy_id,
        name="Sample Strategy",
        family=FAMILY_VWAP,
        module_path="strategies.sample",
        callable_name="generate_signal",
        instruments=("NIFTY",),
        declared_regimes=declared_regimes,
        blocked_regimes=blocked_regimes,
        required_market_state_dimensions=("trend", "volatility", "breadth", "liquidity", "session"),
        required_evidence_keys=evidence_keys,
        direction_capabilities=directions,
        min_market_state_confidence=confidence,
        description=description,
    )


def test_default_strategy_quality_audit_is_read_only_and_non_action():
    audit = build_strategy_quality_audit()
    payload = json.loads(audit.to_json())

    assert audit.read_only is True
    assert audit.append is False
    assert audit.is_order_action is False
    assert audit.broker_api_called is False
    assert audit.registry_valid is True
    assert audit.blockers == ()
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["metadata"]["does_not_import_strategy_modules"] is True
    assert payload["metadata"]["does_not_execute_strategy_callables"] is True
    assert "selected_strategy" not in payload
    assert "eligible_strategies" not in payload


def test_quality_audit_passes_strong_metadata_record():
    audit = build_strategy_quality_audit([_spec()])

    assert audit.valid is True
    assert audit.blockers == ()
    assert audit.records[0].quality_status == QUALITY_STATUS_PASS
    assert audit.records[0].warning_count == 0
    assert audit.records[0].blocker_count == 0


def test_quality_audit_warns_for_low_confidence_narrow_regime_single_direction_and_missing_description():
    audit = build_strategy_quality_audit(
        [
            _spec(
                declared_regimes=(REGIME_BULL_TREND,),
                directions=(DIRECTION_BUY_CALL,),
                confidence=0.25,
                description="",
            )
        ]
    )

    assert audit.valid is True
    assert audit.blockers == ()
    assert audit.records[0].quality_status == QUALITY_STATUS_WARN
    assert STRATEGY_QUALITY_LOW_CONFIDENCE in audit.warnings
    assert STRATEGY_QUALITY_NARROW_REGIME_COVERAGE in audit.warnings
    assert STRATEGY_QUALITY_SINGLE_DIRECTION in audit.warnings
    assert STRATEGY_QUALITY_MISSING_DESCRIPTION in audit.warnings


def test_quality_audit_blocks_invalid_registry_evidence_contract():
    audit = build_strategy_quality_audit(
        [
            _spec(
                evidence_keys=("market_state",),
            )
        ]
    )

    assert audit.valid is True
    assert audit.registry_valid is True
    assert audit.records[0].quality_status == QUALITY_STATUS_WARN
    assert STRATEGY_QUALITY_MISSING_EVIDENCE in audit.warnings


def test_quality_audit_surfaces_registry_blockers_as_blocking_quality_records():
    registry = build_strategy_spec_registry(
        [
            {
                "strategy_id": "bad_regime",
                "name": "Bad Regime",
                "family": "VWAP",
                "module_path": "strategies.bad",
                "callable_name": "generate_signal",
                "instruments": ["NIFTY"],
                "declared_regimes": [REGIME_UNKNOWN],
                "blocked_regimes": [REGIME_UNKNOWN, REGIME_OUT_OF_SESSION, "LIQUIDITY_STRESSED", "VOLATILITY_STRESSED"],
                "direction_capabilities": [DIRECTION_BUY_CALL],
            }
        ]
    )

    audit = build_strategy_quality_audit(registry)

    assert registry.valid is False
    assert audit.valid is False
    assert audit.registry_valid is False
    assert audit.records[0].quality_status == QUALITY_STATUS_BLOCK
    assert STRATEGY_QUALITY_UNSAFE_REGIME_NOT_BLOCKED in audit.blockers


def test_quality_audit_blocks_empty_registry():
    audit = build_strategy_quality_audit([])

    assert audit.valid is False
    assert audit.registry_valid is False
    assert STRATEGY_QUALITY_EMPTY_REGISTRY in audit.blockers
    assert any(finding.code == STRATEGY_QUALITY_EMPTY_REGISTRY for finding in audit.findings)


def test_quality_audit_accepts_existing_registry_without_rebuilding_or_executing_code():
    registry = build_strategy_spec_registry([_spec(strategy_id="registry_supplied")])

    audit = build_strategy_quality_audit(registry)

    assert audit.valid is True
    assert audit.records[0].strategy_id == "registry_supplied"
    assert audit.records[0].metadata["module_path"] == "strategies.sample"
    assert audit.records[0].is_order_action is False
    assert audit.records[0].broker_api_called is False


def test_quality_audit_records_all_findings_in_payload():
    audit = build_strategy_quality_audit(
        [
            _spec(
                declared_regimes=(REGIME_BULL_TREND,),
                directions=(DIRECTION_BUY_CALL,),
                confidence=0.1,
                description="",
            )
        ]
    )
    payload = audit.to_payload()
    record = payload["records"][0]

    assert record["quality_status"] == QUALITY_STATUS_WARN
    assert record["is_order_action"] is False
    assert record["broker_api_called"] is False
    assert set(payload["warnings"]) >= {
        STRATEGY_QUALITY_LOW_CONFIDENCE,
        STRATEGY_QUALITY_NARROW_REGIME_COVERAGE,
        STRATEGY_QUALITY_SINGLE_DIRECTION,
        STRATEGY_QUALITY_MISSING_DESCRIPTION,
    }
