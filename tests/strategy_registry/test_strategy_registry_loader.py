import os
from core.strategy_registry.strategy_registry import StrategyRegistry
from core.strategy_registry.registry_loader import RegistryLoader


def test_registry_loader():
    registry = StrategyRegistry()
    mock_path = os.path.join(os.path.dirname(__file__), "fixtures")
    loader = RegistryLoader(registry=registry, strategies_path=mock_path)

    count, errors = loader.load_all()

    assert count == 1
    assert not errors

    loaded_manifest = registry.get_strategy("mock_001")
    assert loaded_manifest
    assert loaded_manifest.contract.strategy_name == "Mock Strategy 1"


def test_registry_duplicate_registration():
    registry = StrategyRegistry()
    mock_path = os.path.join(os.path.dirname(__file__), "fixtures")
    loader = RegistryLoader(registry=registry, strategies_path=mock_path)

    count, errors = loader.load_all()
    assert count == 1

    # Try to load again to trigger duplicate ID detection
    count2, errors2 = loader.load_all()

    # We should have a validation error for the duplicate
    assert errors2
    assert "already registered" in errors2[0] or "already registered" in str(errors2)


def test_registry_clear():
    registry = StrategyRegistry()
    mock_path = os.path.join(os.path.dirname(__file__), "fixtures")
    loader = RegistryLoader(registry=registry, strategies_path=mock_path)

    loader.load_all()
    assert registry.get_all_strategies()

    registry.clear()
    assert not registry.get_all_strategies()
