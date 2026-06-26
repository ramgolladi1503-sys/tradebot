import re
from typing import Dict, List
from dataclasses import dataclass
from core.strategy_registry.strategy_registry import StrategyRegistry
from core.strategy_registry.registry_loader import RegistryLoader
from core.strategy_registry.strategy_manifest import StrategyManifest


@dataclass
class BridgeResult:
    manifests: Dict[str, StrategyManifest]
    incomplete_strategies: List[str]  # List of strategy IDs


def load_registry_bridge(strategies_path: str = "strategies") -> BridgeResult:
    registry = StrategyRegistry()
    loader = RegistryLoader(registry, strategies_path=strategies_path)
    loaded_count, errors = loader.load_all()

    manifests = {m.contract.strategy_id: m for m in registry.get_all_strategies()}
    incomplete_strategies = []

    # Parse errors to find incomplete strategies
    # Error format: "Validation error in {module_name} for strategy {obj.strategy_id}: {str(e)}"
    # Example: "Validation error in strategies.foo for strategy my_strat: Strategy my_strat is missing critical metadata: entry_rules_summary"
    error_pattern = re.compile(r"Validation error in .* for strategy (.*?):")

    for error in errors:
        match = error_pattern.search(error)
        if match:
            strategy_id = match.group(1).strip()
            incomplete_strategies.append(strategy_id)

    return BridgeResult(manifests=manifests, incomplete_strategies=incomplete_strategies)
