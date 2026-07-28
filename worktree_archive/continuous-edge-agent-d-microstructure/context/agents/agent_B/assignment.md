# Agent B: Pipeline and Temporal Oracle

Your objective is to perform a full pipeline and temporal audit against the accepted Upstox parquet source.

## Accepted Source Manifest
- Path: `research/continuous_structural_edge_discovery_v1/handoffs/source_inventory.json`
- Source Root: `runtime/market_data/upstox`

## Required Actions

1. **Static Checks**: Verify loader ownership, timestamp normalization, session reset, completed-candle semantics, next-bar entry, outcome calculation, MFE/MAE, deterministic serialization.
2. **Synthetic Checks**: Verify future mutation prevention, cross-session prevention, duplicate timestamps, missing bars, stale quote handling, no legal entry, insufficient horizon, deterministic fixtures.
3. **Real-Data Checks**: Load the certified files, reconcile session counts with Agent A, check timestamp order, verify no future joins, check first/last bar handling, ensure candle reconstruction is causal, check completed-candle cutoff, check next-bar entry, check outcome horizons, and run deterministic A/B replay on a fixed sample.

## Required Outputs
You must generate the following files in your handoffs directory:
- `pipeline_candidate_inventory.json`
- `pipeline_static_audit.json`
- `synthetic_temporal_test_report.json`
- `real_data_temporal_audit.json`
- `session_reconciliation.json`
- `oracle_scaffold_report.json`
- `commands.txt`
- `tests.txt`
- `artifact_hashes.json`
- `result.json`

## Prohibited
- Accessing production paths (`core.*`, `strategies.*`, `runtime.live*`).
- Accessing locked holdout or fresh confirmation outcomes.
- Escaping the worktree.
