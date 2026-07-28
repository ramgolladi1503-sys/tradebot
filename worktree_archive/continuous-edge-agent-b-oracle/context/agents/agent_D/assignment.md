# Agent D: Microstructure Suitability Auditor

Your objective is to perform a read-only microstructure suitability audit on the accepted quote/depth corpus.
Do NOT abort because the source is "uncertified"—it has been certified. 

## Accepted Source Manifest
- Path: `research/continuous_structural_edge_discovery_v1/handoffs/source_inventory.json`
- Source Root: `runtime/market_data/upstox`

## Required Actions

You must determine support for the following features:
- bid/ask spread
- top-of-book imbalance
- multi-level depth imbalance
- quote update intensity
- staleness
- gap detection
- liquidity depletion
- replenishment
- trade-sign imbalance
- actual add/cancel/replace semantics (depth snapshots alone do not prove cancellation)

## Required Outputs
You must generate the following files in your handoffs directory:
- `microstructure_source_inventory.json`
- `timestamp_ordering_report.json`
- `staleness_gap_report.json`
- `event_semantics_report.json`
- `supported_feature_contract.json`
- `prohibited_pseudo_features.json`
- `coverage_by_session.json`
- `commands.txt`
- `tests.txt`
- `artifact_hashes.json`
- `result.json`

## Prohibited
- Accessing production paths (`core.*`, `strategies.*`, `runtime.live*`).
- Accessing locked holdout or fresh confirmation outcomes.
- Escaping the worktree.
