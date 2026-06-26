import os
import sys
import importlib
import inspect
from typing import List, Tuple
from core.strategy_registry.strategy_registry import StrategyRegistry
from core.strategy_registry.strategy_manifest import StrategyManifest
from core.strategy_registry.strategy_contract import StrategyContract
from core.strategy_registry.registry_errors import RegistryError


class RegistryLoader:
    def __init__(self, registry: StrategyRegistry, strategies_path: str = "strategies"):
        self.registry = registry
        self.strategies_path = strategies_path
        self.validation_errors: List[str] = []

    def _get_module_name(self, file_path: str) -> str:
        # Convert path to module format (e.g. strategies/nifty_intraday.py -> strategies.nifty_intraday)
        clean_path = file_path
        if clean_path.startswith("./"):
            clean_path = clean_path[2:]
        if clean_path.endswith(".py"):
            clean_path = clean_path[:-3]
        return clean_path.replace(os.sep, ".")

    def load_all(self) -> Tuple[int, List[str]]:
        """
        Discovers and loads all strategies.
        Returns a tuple of (number of successfully loaded strategies, list of validation errors).
        """
        self.validation_errors.clear()
        base_dir = os.path.abspath(self.strategies_path)

        if not os.path.exists(base_dir):
            self.validation_errors.append(f"Strategies directory not found: {base_dir}")
            return 0, self.validation_errors

        # Add the parent directory to sys.path so 'strategies' can be imported if it's the root
        parent_dir = os.path.dirname(base_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        loaded_count = 0

        for root, _, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, parent_dir)
                    module_name = self._get_module_name(rel_path)

                    try:
                        module = importlib.import_module(module_name)
                    except Exception as e:
                        # Continue trying to load others
                        self.validation_errors.append(
                            f"Failed to import module {module_name}: {str(e)}"
                        )
                        continue

                    # Search for StrategyContract instances in the module
                    for name, obj in inspect.getmembers(module):
                        if isinstance(obj, StrategyContract):
                            try:
                                manifest = StrategyManifest(
                                    contract=obj,
                                    file_path=file_path,
                                    module_path=module_name,
                                )
                                self.registry.register(manifest)
                                loaded_count += 1
                            except RegistryError as e:
                                self.validation_errors.append(
                                    f"Validation error in {module_name} for strategy {obj.strategy_id}: {str(e)}"
                                )
                            except Exception as e:
                                self.validation_errors.append(
                                    f"Unexpected error wrapping strategy {obj.strategy_id} in {module_name}: {str(e)}"
                                )

        return loaded_count, self.validation_errors
