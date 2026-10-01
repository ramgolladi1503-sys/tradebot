# Change summary

## Change boundary

Implementation branch: `fix/mros-live-runtime-truth-reliability-v1` in the isolated Codex worktree. No commit was created. Only offline code, tests, design notes, and this evidence package are in scope.

## Files changed and why

- `config/config.py` — explicit environment bounds for the runtime queue and 500 ms default tick-snapshot cadence, WS recovery gap, MEG completion grace/freshness; fixed depth mode label.
- `core/feed_health_truth.py` — evaluate explicitly requested symbols independently from aggregate optional-symbol degradation, retain global/websocket blockers, expose monitored domain states, and prevent overall HEALTHY when transport or monitored dependencies degrade.
- `core/feed/runtime_store.py` — throttle same-identity tick snapshot admission to the configured cadence, coalesce pending latest-state snapshots, preserve lifecycle and safety identity transitions immediately, and expose separate producer request/coalescing plus queue requested/coalesced/enqueued/persisted/rejected/high-water/lag/in-flight accounting.
- `core/kite_depth_ws.py` — apply a producer-side identity-aware cadence gate before DB/depth/status collection; retain immediate lifecycle and safety transitions and suppress same-state direct artifacts within cadence. Raw tick/depth writes are not coalesced by this gate.
- `core/kite_depth_ws.py` — emit structured five-domain feed health from explicit underlying/option maps, leave unsupported futures and stock-spot identities UNKNOWN, and keep tick verification from clearing recovery without causal proof.
- `core/depth_store.py` — label capture `SAMPLED_DEPTH` and expose raw updates, accepted samples, coalesced updates, persistence, rejection, interval, and unavailable duplicate identity status.
- `core/feed_recovery_coordinator.py` — require token reconciliation, per-identity gap evidence, rebuilt state, and a health window before clearing; retain accepted/rejected resolution records in memory.
- `core/kite_depth_ws.py` — prevent restart subscription/tick verification and partial-activity stable ticks from clearing a restart-required blocker without causal coordinator proof; guard the shared clear helper and keep blocked runtime/telemetry states truthful.
- `core/market_event_graph_live_runtime_bridge.py` — retry assembly within bounded completion grace, reject timeout/stale snapshots, and expose cycle/missing/latency metrics.
- `core/observability/sidecar_reporter.py` — require explicit subsystem states for overall HEALTHY; every required but missing subsystem is emitted explicitly as UNKNOWN, and blocked/degraded/unsafe states propagate.
- `tests/core/test_runtime_snapshot_store.py`, `tests/test_depth_store_accounting.py`, `tests/test_edge43_feed_health_truth.py`, `tests/test_edge45_symbol_execution_safety.py`, `tests/test_feed_recovery_coordinator.py`, `tests/test_kite_depth_restart.py`, `tests/test_kite_depth_ws_observation_on_ticks.py`, `tests/test_kite_depth_ws_stability.py`, `tests/test_market_event_graph_live_runtime_bridge.py` — preserve existing assertions and append behavior coverage; restart and local partial-activity verification prove incomplete evidence cannot clear a restart-required blocker.
- `tests/test_sidecar_reporter_status_aggregation.py` — new overall status truth table and safety boundary assertions.
- `tests/test_feed_runtime_states.py` — isolate token-count expectations from process-global launch-plan state left by earlier tests; production launch-plan precedence is unchanged.
- `docs/agent_reviews/MROS_LIVE_RUNTIME_TRUTH_REPAIR_HERMES_STAGE1_20260930.md` — Stage 1 design contracts and acceptance gates.

No T-1 heritage implementation path changed. Existing immutable verifier/publisher remains fail-closed.


## Final continuation repair

- `core/trade_truth/prospective_capture_engine.py` — resolve guarded modules from `importlib.import_module` so guard spies attach to the exact module classes callers obtain from `sys.modules`, even after package/module reload divergence.
- `tests/test_trade_truth_prospective_repair.py` — deliberately bind a stale `core.execution_engine` package attribute and prove the active module class is intercepted; cleanup runs in `finally`.
- `docs/agent_reviews/MROS_BROKER_WRITE_GUARD_MODULE_IDENTITY_HERMES_20260930.md` and `docs/agent_reviews/MROS_BROKER_WRITE_GUARD_MODULE_IDENTITY_GSD_20260930.md` — record the invariant, scope, risk, implementation, and acceptance evidence.
- `tests/test_four_strategy_dataset_manifest.py` — recognize a Git LFS pointer rather than parsing it as Parquet, then try the existing local canonical copy; explicitly skip when only a pointer is available. Two helper tests cover both fallback and pointer-only behavior. The tracked data file remains the 132-byte pointer.

Focused guard/observer/torture/dataset command: **44 passed**; pointer-safe dataset helper suite: **7 passed, 1 skipped**. Latest full-repository command: **8,484 passed, 0 failed, 9 skipped, 28 deselected**, exit 0. See `WHOLE_REPO_REGRESSION_POINTER_SAFE_20261001.log`. Candidate dependency authority and T-1 provenance remain blocked; no rollout is supported.

## Configuration keys

- `FEED_RUNTIME_SNAPSHOT_QUEUE_MAXSIZE` (default 2048): bounded pending state queue.
- `FEED_RUNTIME_SNAPSHOT_INTERVAL_SEC` (default 0.5): minimum interval between tick-source snapshots; non-tick transition snapshots remain immediate.
- `FEED_RECOVERY_MAX_GAP_SEC` (default 3.0): maximum allowed per-required-identity recovery gap.
- `MEG_COMPLETION_GRACE_MS` (default 800; runtime clamp 0–2000): maximum synchronous event-time assembly grace.
- `MEG_MAX_DECISION_FRESHNESS_SEC` (default 15.0): maximum accepted age from bar completion to observed time.
- `DEPTH_CAPTURE_MODE` is a fixed code/config label `SAMPLED_DEPTH`; it is not an operator switch to lossless capture.

The existing `DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC` remains the sampled-depth cadence.

## Migration and run notes

No database schema migration. Runtime snapshot coalescing/accounting and sidecar `SUBSYSTEM_STATES` are additive. Sidecar callers must supply required subsystem truth to receive HEALTHY; missing truth now yields UNKNOWN. Invalid MEG freshness configuration rejects snapshots. Recovery callers that cannot provide the complete proof remain blocked. Run the focused test command recorded in `TEST_RESULTS.md` from this worktree with `/opt/anaconda3/bin/pytest`.


## Candidate dependency authority continuation (2026-10-01)

- `core/candidate_feed_dependencies.py` and `tests/test_candidate_feed_dependencies.py` — added two discovered day-to-night shadow candidate IDs as partial/blocked declarations, with source hash bindings. The contract now distinguishes unknown optional/fallback/breadth/freshness (`None`) from a proven empty list and includes those fields in the fail-closed resolution payload. No candidate became execution-eligible.
- Candidate authority report and registry JSON now cover 14 exact IDs and 23 remaining unknown/unverified family labels. The focused dependency/feed/symbol-safety/T-1 suite passed **115 tests** after the C1/C2 continuation. The pointer-safe whole suite remains prior evidence (8,484 passed); it was not rerun after this metadata/contract-surface continuation.
