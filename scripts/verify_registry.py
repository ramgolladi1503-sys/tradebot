#!/usr/bin/env python3
import sys
import importlib
import pkgutil
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import strategies
from core.strategy_spec import StrategySpec, build_strategy_spec_registry

def get_all_subclasses(cls):
    all_subclasses = []
    for subclass in cls.__subclasses__():
        all_subclasses.append(subclass)
        all_subclasses.extend(get_all_subclasses(subclass))
    return all_subclasses

def main():
    # Dynamically import all modules in the strategies package
    package_path = strategies.__path__
    prefix = strategies.__name__ + "."
    for _, module_name, _ in pkgutil.walk_packages(package_path, prefix):
        try:
            importlib.import_module(module_name)
        except Exception as e:
            print(f"Warning: Failed to import {module_name}: {e}")

    # Find all subclasses of StrategySpec
    subclasses = get_all_subclasses(StrategySpec)

    # Get active strategy registry
    registry = build_strategy_spec_registry()
    registered_modules = {spec.module_path for spec in registry.specs}

    missing = False
    for subclass in subclasses:
        mod = subclass.__module__
        if mod not in registered_modules:
            print(f"Error: Subclass {subclass.__name__} in module {mod} is missing from the active strategy registry.")
            missing = True

    if missing:
        sys.exit(1)
    
    print("Verification passed: All StrategySpec subclasses are registered.")
    sys.exit(0)

if __name__ == "__main__":
    main()
