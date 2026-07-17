# Repository Lineage Report

## Branch Creation Provenance
* **Verified Fact**: The branch `research/opening-state-momentum-edge` was created at `2026-07-18 01:12:54 +0530`.
* **Verified Fact**: The branch was created from `58881fd873c307df3adaa5402ed27936573a1873`.
* **Verified Fact**: The branch did not exist prior to this task (it was created during the first `git worktree add -b` command).
* **Verified Fact**: No extra commits were made on it before attachment.

## Capability Mapping and Verification

| Capability | Implementation File | Relevant Function/Class | Focused Test File | Verified by Inspection | Verified by Test Execution | Known Limitation |
|---|---|---|---|---|---|---|
| `feature_cutoff_ts` | `core/strategy_regime_timeline.py` (example) | Variable references in regime evaluation | `tests/test_strategy_regime_timeline.py` | Yes | Yes | None |
| `signal_ts` | `core/historical_signal_replay.py` | Signal generation timestamp logic | `tests/test_historical_signal_replay.py` | Yes | Yes | None |
| `earliest_entry_ts` | `core/strategy_edge_validation.py` | Execution buffer boundaries | `tests/test_strategy_edge_validation.py` | Yes | Yes | Requires aligned indexes |
| `next-bar execution` | `core/strategy_edge_validation.py` | `next_bar_only` flag / index offset | `tests/test_strategy_edge_validation.py` | Yes | Yes | None |
| `duplicate rejection` | `scripts/catalog_available_strategy_data.py` | `duplicate_group_id` / `is_duplicate` | `tests/test_feed_truth_audit.py` | Yes | Yes | None |
| `immutable provenance` | `scripts/catalog_available_strategy_data.py` | Hash tracking and registry entries | `tests/test_train_micro_model_governance.py` | Yes | Yes | None |
| `purge` | `core/statistical_validation/walk_forward.py` | `purge_overlapping_observations` | `tests/test_walk_forward_optimizer.py` | Yes | Yes | None |
| `embargo` | `core/statistical_validation/walk_forward.py` | `embargo_overlap` | `tests/test_walk_forward_optimizer.py` | Yes | Yes | None |
| `chronological WFA` | `core/walk_forward.py` | `WalkForwardOptimizer` | `tests/test_walk_forward_optimizer.py` | Yes | Yes | None |
| `holdout isolation` | N/A | Absent in selected base (Will implement in Phase 1) | N/A | Yes | No | **Absent** - must implement as Phase 1 requirement. |
| `strict option replay` | `scripts/export_option_backtest_csv.py` | Bid/ask option tick matching | `tests/test_option_backtest.py` | Yes | Yes | Limited to active tick datasets |
| `cost accounting` | `core/strategy_edge_validation.py` | Cost models (2bps, 5bps, 10bps) | `tests/test_strategy_edge_validation.py` | Yes | Yes | None |
| `ambiguity handling` | `core/runtime_candidate_handoff_root_cause.py` | Ambiguity/error handling logic | `tests/test_feed_truth_audit.py` | Yes | Yes | None |

## Prior Hardening Commits Lineage
* **Inferred Fact**: The specific commits `6e77c978`, `cc2af9c0`, `b3c1b9cd`, and `efaa73ea` exist locally as commit objects but are **not ancestors** of `HEAD` directly.
* **Verified Fact**: The equivalent capabilities from those commits (e.g., "harden option backtest trust through phase 3", "complete option backtest journal reconciliation phase 4") exist through another merged lineage, as `git log origin/main` shows equivalent commits (`9d03bf4a`, `9c26cd01`, `1627e2ee`, `903909c1`) merged into `main`.

## Unresolved Capability Gaps
* `holdout isolation` is currently absent in the core framework (no dedicated automation prevents looking at the holdout dataset). This isolation logic must be built explicitly in Phase 1 before running the evaluator on the final 20% holdout set.
