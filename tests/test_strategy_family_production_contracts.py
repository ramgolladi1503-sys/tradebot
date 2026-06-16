from core.strategy_spec import build_strategy_spec_registry


def test_all_strategy_families_have_production_contracts():
    registry = build_strategy_spec_registry()
    assert registry.valid is True

    for strategy_id in registry.strategy_ids():
        spec = registry.get(strategy_id)
        assert spec is not None
        assert spec.read_only is True
        assert spec.append is False
        assert spec.is_order_action is False
        assert spec.broker_api_called is False
        assert spec.declared_regimes
        assert spec.blocked_regimes
        assert spec.required_evidence_keys
        assert spec.required_market_state_dimensions
        assert spec.min_market_state_confidence > 0.0
        assert spec.module_path.startswith("strategies.")
        assert spec.callable_name


def test_all_strategy_families_fail_closed_on_unsafe_regimes():
    registry = build_strategy_spec_registry()
    unsafe_regimes = {
        "UNKNOWN",
        "OUT_OF_SESSION",
        "LIQUIDITY_STRESSED",
        "VOLATILITY_STRESSED",
    }

    for strategy_id in registry.strategy_ids():
        spec = registry.get(strategy_id)
        assert spec is not None
        for regime in unsafe_regimes:
            assert regime in spec.blocked_regimes
