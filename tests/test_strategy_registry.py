import pytest
from strategies.strategy_registry import load_strategy_registry, StrategyRegistryEntry

def test_registry_contains_simple_orb():
    registry = load_strategy_registry()
    assert "SIMPLE_ORB" in registry
    entry = registry["SIMPLE_ORB"]
    assert entry.strategy_kind == "execution_signal_strategy"
    assert entry.certification_track == "phase_1_to_5_execution_replay"
    assert entry.certification_supported is True

def test_registry_contains_movement_strategies():
    registry = load_strategy_registry()
    assert "MEAN_REVERSION_EXTENSION" in registry
    entry = registry["MEAN_REVERSION_EXTENSION"]
    assert entry.strategy_kind == "candidate_generator_strategy"
    assert entry.certification_track == "candidate_generator_contract_only"
    assert entry.callable_name == "generate_mean_reversion_extension_candidates"
    
def test_registry_contains_test_strat_excluded():
    registry = load_strategy_registry()
    assert "TEST_STRAT" in registry
    entry = registry["TEST_STRAT"]
    assert entry.strategy_kind == "test_fixture"
    assert entry.certification_track == "not_certifiable"
    assert entry.certification_supported is False

def test_registry_contains_helper_modules():
    registry = load_strategy_registry()
    assert "RISK_MANAGER" in registry
    entry = registry["RISK_MANAGER"]
    assert entry.strategy_kind == "helper_module"
    assert entry.certification_track == "not_certifiable"

def test_registry_contains_aggregate_engine():
    registry = load_strategy_registry()
    assert "PRO_STRATEGY_ENGINE" in registry
    entry = registry["PRO_STRATEGY_ENGINE"]
    assert entry.strategy_kind == "aggregate_engine"
    assert entry.certification_track == "aggregate_engine_certification"
