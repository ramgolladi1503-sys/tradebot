# Strategy Registry Architecture

## Overview

The Strategy Registry is the single source of truth describing every strategy inside TradeBot. It defines the metadata, validation lifecycle, and operational parameters for all strategies without containing execution logic or trading behavior.

It forms the foundational layer upon which the strategy truth engine, backtesting engine, and real-time execution safety mechanisms rely.

## Architecture Flow

The registry system feeds into downstream truth engines to validate and deploy strategies safely:

```text
Strategy Registry
        ↓
Strategy Truth Engine
        ↓
Replay Truth Engine
        ↓
Statistical Validation
        ↓
Certification
        ↓
Paper Validation
        ↓
Production Decision
```

## Core Components

- **Strategy Contract (`strategy_contract.py`)**: An immutable model defining the strategy metadata, assumptions, and required indicators.
- **Strategy Manifest (`strategy_manifest.py`)**: Wraps the `StrategyContract` with source path information and validates the integrity of the provided metadata.
- **Strategy Registry (`strategy_registry.py`)**: An in-memory key-value store holding the canonical map of `strategy_id -> StrategyManifest`.
- **Registry Loader (`registry_loader.py`)**: Traverses the `strategies/` directory tree, dynamically imports modules, and extracts valid `StrategyContract` instances.

## Design Philosophy

- **Decoupled**: Strategy logic (execution, sizing, signaling) remains entirely separated from strategy description (registry).
- **Immutable**: Once a strategy manifest is loaded, it cannot be modified at runtime.
- **Typed**: The registry avoids implicit mappings, employing `pydantic` or strictly typed `dataclasses` and Enums for safe contract resolution.
- **Validation First**: Loading strategies with missing critical metadata or duplicate IDs results in strict validation failures rather than silent runtime errors.