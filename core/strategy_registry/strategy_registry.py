from typing import Dict, List, Optional
from core.strategy_registry.strategy_manifest import StrategyManifest
from core.strategy_registry.registry_errors import DuplicateStrategyIdError


class StrategyRegistry:
    def __init__(self):
        self._strategies: Dict[str, StrategyManifest] = {}

    def register(self, manifest: StrategyManifest) -> None:
        if manifest.contract.strategy_id in self._strategies:
            raise DuplicateStrategyIdError(
                f"Strategy ID {manifest.contract.strategy_id} is already registered."
            )

        self._strategies[manifest.contract.strategy_id] = manifest

    def get_strategy(self, strategy_id: str) -> Optional[StrategyManifest]:
        return self._strategies.get(strategy_id)

    def get_all_strategies(self) -> List[StrategyManifest]:
        return list(self._strategies.values())

    def clear(self) -> None:
        self._strategies.clear()
