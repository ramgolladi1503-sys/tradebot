# GSD Implementation Changeset — Session Continuity

- source_agent: gsd
- action: GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
- title: Session continuity heritage graph, CAS lineage, and read-only runtime integration
- scope: immutable graph/verifier; strict CAS event binding and same-session restart lineage; verified per-strategy readiness wired into the read-only observer/candidate shadow registry
- requested_paths: `core/kite_depth_ws.py`, `core/cas_primitive_producer.py`, `core/market_heritage_graph.py`, `core/market_heritage_verifier.py`, `core/kite_read_only_observation_runtime.py`, `core/runtime_snapshot_producer.py`, `core/canonical_cycle_coordinator.py`, `core/paper_shadow/strategy_shadow_adapter.py`, scoped tests, and `docs/agent_reviews/`
- allowed_paths: these scoped paths in isolated branch `ram/mros-session-continuity-20260929`
- forbidden_paths: broker/order/risk/feed authority changes, strategy thresholds/contracts, credentials, raw protected runtime evidence, paper/live or entry-authority changes
- expected_tests: new graph, CAS evaluation idempotency, coverage ledger tests; existing consumer and V23 harness regressions
- acceptance_proof: exact commands/results recorded below; synthetic runtime wiring is tested, while historical source and fresh-session gates remain separate

## Starting state

- Base HEAD: `ab229d3e32f5f6ceb02c476efdd53253aa55ee83`
- Branch: `ram/mros-session-continuity-20260929`
- Worktree: `/Users/madhuram/.codex/worktrees/mros-session-continuity/tradebot`
- Canonical checkout: dirty before work; not modified.
- New worktree: clean at creation; no pre-existing work was overwritten.

## Required task contract

- source_agent: gsd (executing the preceding frozen Hermes contract, with user-authorized read-only runtime integration)
- action: GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
- title: Session continuity heritage graph, CAS lineage, and read-only runtime integration
- scope: lineage primitives, event-bound CAS evidence, read-only runtime/candidate readiness wiring, fixtures, and this evidence packet
- requested_paths: listed under `requested_paths` above
- allowed_paths: only the isolated worktree scoped source/tests and `docs/agent_reviews/` evidence files
- forbidden_paths: broker/order/risk/feed authority changes, strategy threshold/contract changes, credentials, raw runtime evidence, paper/live and entry-authority changes
- expected_tests: focused CAS, graph, consumer, V23, read-only observer and callback regression suite
- acceptance_proof: focused tests across continuity graph, CAS, coverage, runtime, adapter, consumer and V23 harness; independent serialized-manifest verifier fixtures, compileall and diff checks; real source/runtime acceptance reported separately

## Changes by file

- `core/kite_read_only_observation_runtime.py`: replace production trust in naked launch-plan/disk/environment T1 values with pinned, hash-verified heritage readiness; pass only per-strategy READY facts to the shadow registry; resolve/publish same-session CAS ancestry after safe drain. This is the approved read-only runtime integration point.
- `core/runtime_snapshot_producer.py`: prefer a verified merge of current-run and same-session inherited CAS primitives, using the run-owned immutable CAS path; retain current-run-only behavior when no heritage context exists.
- `core/canonical_cycle_coordinator.py`: carry immutable session identity, inherited references, and current CAS path into canonical snapshots so process restarts do not silently lose same-day context.
- `core/paper_shadow/strategy_shadow_adapter.py`: enable each shadow adapter only when its own heritage report is READY; persist the verification report. Opening Drive late-start observations now expire at the frozen 11:01 boundary and cannot create a late shadow entry. No readiness result authorizes entry or execution.
- `core/market_heritage_graph.py`: content-addressed immutable evidence nodes; dependency edges with exact parent hash; deterministic topological ordering; fail-closed cycles, unresolved ancestors, logical-key conflicts, non-verified dependencies and future information; fsync + no-clobber publication with target trading-session identity; bounded same-session manifest index with lock, hash closure, root confinement, and directory fsync; bounded node, graph, and manifest inputs; injected-authority previous-session resolver; per-strategy field readiness; exact expected-session rolling-close recomputation. No candidate/strategy imports.
- `core/kite_depth_ws.py`: normalized tick sink now receives source-event ID and canonical payload SHA computed at the source callback boundary. Accepted callback identity and timestamp provenance reach the in-memory read-only market snapshot through an opt-in internal accessor. Public legacy tick-reader shape, SQLite schema and 12-field row bounds, feed selection, and trading gates remain unchanged; DB-only callback identity is explicitly unavailable.
- `core/cas_primitive_producer.py`: require a hashed normalized-source-event envelope; bind selected exchange time to source-event time and payload, while retaining distinct local receive time; recompute target identity and lateness; verify persisted identity; lock and merge per-run snapshots atomically; preserve captures, block competing values, and allow a valid capture after an earlier blocked attempt. Adds stable evaluation identity from strategy/spec/source/session/event hashes. Cross-run discovery remains a separate graph-index concern.
- `core/read_only_coverage_ledger.py`: bounded per-token callback coverage counts, source-event hash verification and interarrival maxima; explicitly does not infer scheduler cadence. Process-gap output now requires exact current-session identity and verifies prior report hash, source run, and manifest digest metadata.
- `core/observation_lineage.py`: read-only per-cycle hash envelope joins callback-derived tick identity in the consumed snapshot, bounded source payload hash, snapshot/feed hashes, full NativePulse identity, strategy result, candidate bindings, selected/rejected decisions, and canonical trade-truth trace. Independent record verification rejects payload or join mutations; absent callback IDs remain explicitly unknown. `core/kite_read_only_observation_runtime.py` includes snapshot/tick/feed identity in the native pulse input and writes `causal_observation_lineage.jsonl`; frozen contract files resolve from the repository root and the approved evidence root derives from established storage authority.
- `core/cas_evaluation_ledger.py`: process-safe claim/completion receipt for CAS event-pair identity, bounded and atomic; completed source pairs are blocked before repeat evaluation across restart.
- `core/market_heritage_verifier.py`: independently recomputes manifest/node/source hashes, edge closure, DAG, session identity, decision-time admissibility, and run-coverage node identity/hash/session/timing/authority without importing the producer graph module.
- `tests/core/test_runtime_snapshot_producer.py`, `tests/test_kite_read_only_observation_runtime.py`, `tests/test_cas_coordinator_lifecycle.py`, `tests/paper_shadow/test_strategy_shadow_adapters.py`: prove pinned-manifest handoff, per-strategy gating, current/inherited snapshot wiring, and per-observation/checkpoint provenance hashes and blockers.
- `tests/test_market_heritage_graph.py`: includes concurrent index writers and a three-process same-day split-target chain with cross-day isolation.
- `tests/test_cas_primitive_producer.py`, `tests/test_read_only_consumer_cycle.py`, `tests/test_v23_production_equivalent_harness.py`, `tests/test_kite_depth_ws_observation_on_ticks.py`, `tests/test_causal_strategy_and_truth.py`: cover event identity, CAS persistence/merge and affected consumer regressions. V23 fixture now carries explicit synthetic session identity and verifies duplicate replay blocks.
- `tests/test_cas_evaluation_ledger.py`, `tests/core/test_read_only_coverage_ledger.py`: prove receipt recovery/idempotency and conservative per-token coverage behavior.
- `docs/agent_reviews/HERMES_SESSION_CONTINUITY_HERITAGE_CONTRACT.md`: frozen contracts and source findings.
- `docs/agent_reviews/HERITAGE_DEPENDENCY_GRAPH.json`: explicit evidence/dependency graph with blocked edges.
- `docs/agent_reviews/SOURCE_AND_HERITAGE_MANIFEST.json`: original evidence paths, hashes, status, authority boundary and hashed external inventories. Expanded read-only legacy inventories: 2026-09-28 (29 files, 2 runs, 98,923,969 bytes) and 2026-09-29 (30 files, 2 runs, 91,783,034 bytes). Both remain explicitly unverified and outside protected source trees. A process check found PID 82150 active in one 2026-09-29 run; files changed during bounded inventory/measurement, so no stable full-run claim is made. No signal/stop action or post-discovery raw-file read occurred.
- `tests/test_market_heritage_graph.py`: graph, separate-verifier, session-index, previous-session calendar, readiness isolation, temporal leakage, exact frozen 15:29 futures bar and event epoch, strict prior/current futures contract-key equality, and exact 200-row independently recomputed rolling-SMA mutation cases with canonical daily-row content digests. The synthetic 199-row and stale digest cases fail closed.
- `tests/test_cas_primitive_producer.py`: event hash binding, late whole-second source, blocked-then-valid, stale restart, concurrent distinct-target merge and competing-capture conflict.
- `tests/test_read_only_consumer_cycle.py`, `tests/test_v23_production_equivalent_harness.py`: fixtures now provide explicit normalized source-event envelopes for valid synthetic source events; negative controls remain blocked.
- Acceptance matrix, independent verifier report, source manifest, read-only operator runbook and final verdict are present in this evidence root.

## Verification results

- `pytest -q tests/test_cas_primitive_producer.py tests/test_cas_evaluation_ledger.py tests/test_market_heritage_graph.py tests/test_kite_read_only_observation_runtime.py tests/core/test_runtime_snapshot_producer.py tests/core/test_read_only_coverage_ledger.py tests/paper_shadow/test_strategy_shadow_adapters.py tests/test_causal_strategy_and_truth.py tests/test_read_only_consumer_cycle.py tests/test_v23_production_equivalent_harness.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_cas_coordinator_lifecycle.py tests/core/test_observation_lineage.py tests/core/test_tick_store_db_truth.py tests/core/test_market_snapshot_builder.py tests/test_tick_store.py tests/test_ws_tick_ingestion_updates_tick_store.py`: **241 passed**.
- `python -m compileall -q core/kite_depth_ws.py core/market_heritage_graph.py core/market_heritage_verifier.py core/cas_primitive_producer.py core/cas_evaluation_ledger.py core/read_only_coverage_ledger.py core/kite_read_only_observation_runtime.py core/runtime_snapshot_producer.py core/canonical_cycle_coordinator.py core/read_only_consumer_cycle.py core/paper_shadow/strategy_shadow_adapter.py`: passed.
- `git diff --check`: passed.
- Acceptance-matrix, verifier, graph and source manifest JSON parse: passed.
- Separate verifier fixture: valid graph PASS; changed availability fails node hash and future-time checks.
- Regression fixtures include equal-clock baseline events and delayed local receipt. The frozen contract is unchanged: source and selected exchange timestamps must bind exactly; local receive time is separately retained. Source/selected mismatches remain blocked.
- The actual WebSocket callback-to-process-local tick-cache event identity is regression-tested; process-local cache and strategy snapshot correlation is measured separately by exact shared event IDs. Pulse-to-candidate/decision/trade-truth identity is fixture-tested through `causal_observation_lineage.jsonl`. SQLite-only rows do not claim callback identity; real feed coverage, fresh-session lineage, and any strategy snapshot correlation without shared IDs remain unproven.

## Explicitly blocked integration

The source callback identity is carried only in process-local accepted-tick cache and the read-only snapshot. Existing SQLite rows use the unchanged 12-field contract, so DB-only callback identity is null/unknown. This remains fixture evidence; it is not a claim of durable feed-to-consumer correlation.

The normalized tick callback now emits an ID/hash over the source event envelope; an offline regression invokes the actual callback and verifies that envelope reaches the process-local tick cache. CAS binds the recorded price to the envelope. It does not archive or independently authenticate broker-origin bytes. The historical 10:00 source/selected mismatch remains invalid because the event envelope was not recorded then. Runtime wiring is scoped, read-only, and fixture-tested; authoritative calendar/T−1 source integration and promotion of historical values remain blocked.

Historical diagnostic telemetry found in the approved roots is summarized in the source manifest. On a stable 2026-09-28 run, 8,971 pulse IDs validated and 5,916 selected-tick references covered 51 tokens (116 each); the maximum observed per-token receipt interval was 347.947 seconds. A second 2026-09-28 run had 1,326 selected references across 51 tokens (26 each), maximum 324.294 seconds. A stable earlier 2026-09-29 run had 1,530 references (51×30). These rows do not contain exchange event time/price and cannot establish intended cadence, missed-feed detection, or downstream correlation. The other 2026-09-29 run was being written by PID 82150 during measurement; unstable files were marked, and no more raw reads occurred after process discovery. At resume recheck PID 82150 was absent. A later broad read-only process listing observed canonical checkout `run_all.sh`, `watchdog.sh`, and `scheduler.py` (PIDs 1403, 1469, 67023); their relation to the recorded external run directory is unknown. No process was signaled, restarted, or launched by this task, and no protected run files were read.

## Migration and configuration

- New config keys: none.
- Schema migration: graph manifest schema v1 is additive and rejects unknown versions. No raw historical files are rewritten.
- CAS legacy JSON remains readable. CAS rows remain in the existing per-run JSON schema. Writers now serialize through a process lock, merge under lock, and atomically replace the per-run materialized snapshot; graph/session manifests use immutable content-addressed files and the explicit bounded session index.
- Rollout: implementation is offline by default. The observer now consumes only a pinned, independently verified heritage manifest and keeps missing fields blocked. A fresh runtime session remains operator-controlled; do not promote paper/live or entry authority. Historical source/calendar gates must pass before any strategy prerequisite becomes READY.

## Run instructions

From the isolated worktree, run the focused acceptance set:

```bash
pytest -q tests/test_cas_primitive_producer.py tests/test_cas_evaluation_ledger.py tests/test_market_heritage_graph.py tests/test_kite_read_only_observation_runtime.py tests/core/test_runtime_snapshot_producer.py tests/core/test_read_only_coverage_ledger.py tests/paper_shadow/test_strategy_shadow_adapters.py tests/test_causal_strategy_and_truth.py tests/test_read_only_consumer_cycle.py tests/test_v23_production_equivalent_harness.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_cas_coordinator_lifecycle.py tests/core/test_observation_lineage.py tests/core/test_tick_store_db_truth.py tests/core/test_market_snapshot_builder.py tests/test_tick_store.py tests/test_ws_tick_ingestion_updates_tick_store.py
python -m compileall -q core/kite_depth_ws.py core/market_heritage_graph.py core/market_heritage_verifier.py core/cas_primitive_producer.py core/cas_evaluation_ledger.py core/read_only_coverage_ledger.py core/observation_lineage.py core/kite_read_only_observation_runtime.py core/runtime_snapshot_producer.py core/canonical_cycle_coordinator.py core/read_only_consumer_cycle.py core/paper_shadow/strategy_shadow_adapter.py
git diff --check
```

## What did not change

No broker API calls, orders, live/paper authorization, strategy entry windows/thresholds, candidate decisions, execution eligibility, credentials, runtime lifecycle controls or raw evidence files changed. The observer-to-shadow adapter data path was wired to verified per-strategy readiness; it does not grant entry or execution authority. Callback identity is additive read-only provenance; the SQLite contract, feed selection and freshness behavior were not changed. Synthetic tests prove code properties only; they do not establish historical source authority, market coverage, trading readiness, or live verification.

## Continuation on the user-designated branch

- Source branch: `fix/runtime-pulse-and-feed-consistency-v1` at `12d01da414d9a1ffc13718390e2c950c9f621bfd`.
- Implementation branch: `ram/mros-session-continuity-live-integration` in `/Users/madhuram/.codex/worktrees/mros-live-branch-continuity/tradebot`, created from that exact source SHA. The supplied worktree and its untracked prerequisite manifest were not modified.
- The architecture implementation was applied as a scoped cherry-pick and reconciled with the two feed commits. In `core/kite_read_only_observation_runtime.py`, the branch's canonical CAS token resolver and the architecture's same-day heritage plus pinned T-1 readiness paths are both retained. In `core/tick_store.py`, the branch's typed queue and configurable 50,000 default remain; the older 10,000 default was not restored.
- `core/paper_shadow/strategy_shadow_adapter.py`: the old convenience loader now returns null prerequisite values and explicit blocked provenance. It no longer trusts plain launch-plan facts, current-contract fallback, arbitrary JSON, or environment overrides. Production observation uses `load_verified_t1_prerequisites` with a pinned digest, approved root, exact target session/instrument, frozen contract digests, and the independent verifier.
- Tests prove unpinned values remain blocked and do not enable adapters: `tests/paper_shadow/test_strategy_shadow_adapters.py` and `tests/test_pulse_issues_and_feed_consistency.py`.
- The supplied untracked manifest remains untouched; its exact hash and `BLOCKED_SOURCE_EVIDENCE` disposition are recorded in `SOURCE_AND_HERITAGE_MANIFEST.json`.
- Verification: focused continuity, feed-consistency, candidate/authority and T-1 source-gate suite: **252 passed, 2 dependency warnings**. Warnings are pandas' optional `numexpr` and `bottleneck` version notices. The first run exposed two stale acceptance assertions and one missing test import; those were corrected and the full command then passed.
- No configuration keys were added. The configured queue capacity from the supplied branch remains unchanged. Migration remains additive and offline; historical inputs without pinned provenance remain blocked. No runtime was launched, stopped or signaled.
