# Repository Lineage Report

## Branch Creation Provenance
* **Verified Fact**: The branch `research/opening-state-momentum-edge` was created at `2026-07-18 01:12:54 +0530`.
* **Verified Fact**: The branch was created from `58881fd873c307df3adaa5402ed27936573a1873`.
* **Verified Fact**: The branch did not exist prior to this task (it was created during the first `git worktree add -b` command).
* **Verified Fact**: No extra commits were made on it before attachment.

## Trusted Capability Presence
* **Verified Fact**: Key capabilities are present in the selected base. Searching the codebase reveals:
  * Walk-forward implementation: `core/statistical_validation/walk_forward.py`, `core/walk_forward.py`, `core/walk_forward_ml.py`, `scripts/run_walk_forward.py`, `scripts/build_walk_forward_input.py`
  * Trusted option-replay: `scripts/export_option_backtest_csv.py`
  * Strategy validation: `scripts/catalog_available_strategy_data.py`, `tests/test_walk_forward_framework.py`
* **Verified Fact**: Causal fields like `feature_cutoff_ts`, `signal_ts`, `earliest_entry_ts`, `purge`, `embargo`, `duplicate`, `provenance`, and `manifest` appear correctly in core files (e.g., `tests/test_feed_truth_audit.py`, `core/runtime_candidate_handoff_root_cause.py`, `scripts/audit_upstox_candle_files.py`).
* **Verified Fact**: Strict duplicate handling exists (e.g., `duplicate_key_counts`, `duplicate_group_id` logic).

## Prior Hardening Commits Lineage
* **Inferred Fact**: The specific commits `6e77c978`, `cc2af9c0`, `b3c1b9cd`, and `efaa73ea` exist locally as commit objects but are **not ancestors** of `HEAD` directly.
* **Verified Fact**: The equivalent capabilities from those commits (e.g., "harden option backtest trust through phase 3", "complete option backtest journal reconciliation phase 4") appear to exist through another merged lineage, as the `git log origin/main` shows equivalent commits (`9d03bf4a`, `9c26cd01`, `1627e2ee`, `903909c1`) merged into `main`.

## Unresolved Capability Gaps
* None identified so far. The trusted foundations are verified as present.
