# GSD Implementation Changeset — Session Continuity

## PR943 CI applicability repair — 2026-10-01

```yaml
source_agent: gsd
action: PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
title: PR943 trusted CI candidate-input and workflow-scope repair
scope: Correct three non-authorized CI failures without weakening required tests, static analysis, or safety certification.
requested_paths: .github/workflows/code-excellence-gates.yml, .github/workflows/pr782-remaining-evidence-contracts.yml, .github/workflows/meg-shadow-system-certification.yml, docs/agent_reviews/MROS_LIVE_RUNTIME_TRUTH_REPAIR_HERMES_STAGE1_20260930.md, docs/agent_reviews/GSD_IMPLEMENTATION_CHANGESET.md
allowed_paths: listed paths only
forbidden_paths: runtime code, strategy/risk/order/broker code, credentials, secrets, live data, branch-protection settings
expected_tests: YAML parse; candidate-source CE gate; focused PR782 suites and applicable-scope validation; exact-SHA hosted required CI
acceptance_proof: required exact-SHA CI success; candidate source is data-only for trusted CE scripts; inapplicable PR-specific scope does not fail unrelated integration changes; no assertions or required checks weakened.
```

Changed the CE workflow to analyze files from a detached exact-head worktree as inert inputs while continuing to execute the trusted base checkout's gate scripts and configuration. Changed PR782's fallback from a stale PR783 baseline to the event's PR base, and made its protected-scope assertion conditional on PR782-owned artifacts while keeping all focused suites unconditional when the workflow runs. Narrowed MEG's trigger away from the broad shared runtime-authority test family and added a dedicated applicability job, so workflow-only or shared-test-only edits do not run or claim an out-of-scope certification; owned certification inputs still run the full guard and suite.

Risks: the CE workflow change is loaded from `main` because this is a `pull_request_target`; therefore this PR cannot use its own change to alter the current trusted workflow run. A separate trusted-base update is necessary before CE can evaluate PR943's candidate source. No new config keys. Validation hooks: local workflow YAML parse and exact-head CE runner exercise; focused hosted suites and exact-SHA checks remain final proof. Rollout: merge the trusted workflow correction to `main`, rerun PR943 checks, then merge PR943 only after required CI is green and only the user's two named exceptions remain.

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
- Supplied branch feed-specific suite: **73 passed, 2 optional dependency warnings**.
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
pytest -q tests/test_cas_primitive_producer.py tests/test_cas_evaluation_ledger.py tests/test_market_heritage_graph.py tests/test_kite_read_only_observation_runtime.py tests/core/test_runtime_snapshot_producer.py tests/core/test_read_only_coverage_ledger.py tests/paper_shadow/test_strategy_shadow_adapters.py tests/test_causal_strategy_and_truth.py tests/test_read_only_consumer_cycle.py tests/test_v23_production_equivalent_harness.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_cas_coordinator_lifecycle.py tests/core/test_observation_lineage.py tests/core/test_tick_store_db_truth.py tests/core/test_market_snapshot_builder.py tests/test_tick_store.py tests/test_ws_tick_ingestion_updates_tick_store.py tests/test_pulse_issues_and_feed_consistency.py tests/paper_shadow/test_t1_prerequisites_authority.py
python -m compileall -q core/kite_depth_ws.py core/market_heritage_graph.py core/market_heritage_verifier.py core/cas_primitive_producer.py core/cas_evaluation_ledger.py core/read_only_coverage_ledger.py core/observation_lineage.py core/kite_read_only_observation_runtime.py core/runtime_snapshot_producer.py core/canonical_cycle_coordinator.py core/read_only_consumer_cycle.py core/paper_shadow/strategy_shadow_adapter.py scripts/generate_t1_prerequisites.py scripts/verify_t1_prerequisites_oracle.py
git diff --check
```

## What did not change

No broker API calls, orders, live/paper authorization, strategy entry windows/thresholds, candidate decisions, execution eligibility, credentials, runtime lifecycle controls or raw evidence files changed. The observer-to-shadow adapter data path was wired to verified per-strategy readiness; it does not grant entry or execution authority. Callback identity is additive read-only provenance; the SQLite contract, feed selection and freshness behavior were not changed. Synthetic tests prove code properties only; they do not establish historical source authority, market coverage, trading readiness, or live verification.

## Continuation on the user-designated branch

- Source branch: `fix/runtime-pulse-and-feed-consistency-v1` at `12d01da414d9a1ffc13718390e2c950c9f621bfd`.
- Implementation branch: `ram/mros-session-continuity-live-integration` in `/Users/madhuram/.codex/worktrees/mros-live-branch-continuity/tradebot`, created from that exact source SHA. Heritage integration commit: `ae303bcc7f1eca6432bee69db8d14006be1a8b2a`; T-1 hardening commit: `df5bb856a` (`fix: fail closed on unverified t1 source inventories`). The supplied worktree and its untracked prerequisite manifest were not modified. T-1 graph assembler commits: `7eacc564716b65229e4ee0681606acbab4d22a7b`, `9c93d5ef2f8a0f1eac83b115d0cd2da47adf022f`; independent runtime re-verification commit: `b04d3764d3b65a329dac14e07ed9e4dab8ba18e0`; future ancestor field-localization commit: `54e7cbd4e6f6393d307371ec0a83b00dde9575b4`.
- The architecture implementation was applied as a scoped cherry-pick and reconciled with the two feed commits. In `core/kite_read_only_observation_runtime.py`, the branch's canonical CAS token resolver and the architecture's same-day heritage plus pinned T-1 readiness paths are both retained. In `core/tick_store.py`, the branch's typed queue and configurable 50,000 default remain; the older 10,000 default was not restored.
- `core/paper_shadow/strategy_shadow_adapter.py`: the old convenience loader now returns null prerequisite values and explicit blocked provenance. It no longer trusts plain launch-plan facts, current-contract fallback, arbitrary JSON, or environment overrides. Production observation uses `load_verified_t1_prerequisites` with a pinned digest, approved root, exact target session/instrument, frozen contract digests, and the independent verifier. `publish_verified_heritage_manifest` now performs graph time-preflight, atomic content-addressed publication, separate semantic verification, then bounded index registration; future or invalid graphs are not indexed.
- Tests prove unpinned values remain blocked and do not enable adapters: `tests/paper_shadow/test_strategy_shadow_adapters.py` and `tests/test_pulse_issues_and_feed_consistency.py`.
- `scripts/generate_t1_prerequisites.py` is now a hash-bound legacy inventory only. It never promotes snapshot LTP, loose futures rows, or unbound daily rows. `scripts/verify_t1_prerequisites_oracle.py` independently verifies source and payload hashes while rejecting any promoted value. The tracked 2026-09-23 preflight file and supplied untracked 2026-09-29 manifest remain unchanged and are recorded as `LEGACY_UNVERIFIED`.
- Verification: focused continuity, feed-consistency, candidate/authority and T-1 source-gate suite: **256 passed, 2 optional dependency warnings**. Warnings are pandas' optional `numexpr` and `bottleneck` version notices. The first run exposed two stale acceptance assertions and one missing test import; those were corrected and the full command then passed. The supplied branch feed-specific command was also rerun separately: **73 passed, 2 optional dependency warnings**.
- No configuration keys were added. The configured queue capacity from the supplied branch remains unchanged. Updated files are `scripts/generate_t1_prerequisites.py` and `scripts/verify_t1_prerequisites_oracle.py`; `core/market_heritage_graph.py` adds the verified T-1 publication/index path. Migration remains additive and offline; historical inputs without pinned provenance remain blocked. No runtime was launched, stopped or signaled.

- Final focused regression after graph publisher, oracle, and decision-time validation changes: **256 passed, 2 optional dependency warnings**.

## T-1 graph assembly seam

- `core/market_heritage_graph.py` now exposes `assemble_t1_heritage_graph`. It accepts only an explicitly verified calendar predecessor, exact required strategy fields, target instruments, source nodes, prerequisite nodes, and a finite decision epoch. It validates session/calendar/instrument/contract identity, unique source ancestry, exact field coverage, and evidence availability before returning a graph with exactly two direct edges per prerequisite (source contract and `PREVIOUS_ELIGIBLE_SESSION`). The API does not discover calendars or certify source data.
- `tests/test_market_heritage_graph.py` adds a positive assemble → independently verified publish test and negative controls for missing/extra prerequisite fields, wrong source session, and future evidence.
- Focused graph suite: **54 passed, 2 optional dependency warnings**. Combined continuity/feed-consistency/candidate/T-1 suite: **261 passed, 2 optional dependency warnings**. Supplied-branch feed regression: **73 passed, 2 optional dependency warnings**.
- These are synthetic implementation proofs. No T-1 source authority or fresh runtime evidence was created; final status remains partial.


## Independent runtime verification hardening

- Audit mutation reproduced a bypass: a T-1 prerequisite node rehashed with `status=OBSERVED` but payload `verification_status=VERIFIED` passed the standalone semantic verifier and the runtime loader exposed its value.
- `core/market_heritage_verifier.py` now rejects non-VERIFIED prerequisite node/payload statuses, unsupported strategy fields, absent/non-finite/future prerequisite or source availability, and absent/non-finite/future calendar availability.
- `core/market_heritage_graph.py` invokes that separate verifier at runtime after pinned hash and structural checks. It localizes semantic errors to the exact requested prerequisite node so unrelated strategy readiness remains independent; structural/hash failures still block the manifest. Runtime row validation preserves precise blocker reasons.
- Added five self-consistent rehashed-manifest negative cases covering derived node status, payload status, future payload availability, missing prerequisite availability, and missing calendar availability. Each is rejected by both the independent verifier and runtime loader.
- Validation at the prior verifier-hardening checkpoint: graph suite **61 passed**; combined scoped campaign **268 passed**; supplied feed regression **73 passed**; compileall and diff check passed. The later V17 update below supersedes graph/campaign counts with **64** and **271**. Synthetic-only; real T-1 sources/calendar and fresh runtime remain blocked/unknown.


## Local source-corpus gate recheck

- Read the current canonical registry at `/Volumes/TradeBotData/NIFTY50_1M_2009_2026_V3_CURRENT/datasets/NIFTY50_1M_CANONICAL.json` (SHA-256 `6af17029074fc130cfb78a83d95bef7f456220d12ed4df4e65e584e9e205b2a5`) and its research-ready parquet (SHA-256 `829f2e72ab3e97b8a9262cee741f738ac62a37d2634fe108886648ff125ffec9`).
- The registered research-ready window ends `2026-09-04 15:29:00+05:30`; `2026-09-07` is provisional. The corpus is spot index, explicitly research-only, and has non-authoritative volume. The registry's declared `MASTER_MANIFEST.json` path is absent.
- This data cannot establish the `2026-09-28` daily close/SMA input or exact NIFTY futures contract/15:29 bar. Added both hashes to the source manifest as rejected research-only candidates; `V09` and real `V12` remain `BLOCKED_SOURCE_EVIDENCE`.

- A seven-case self-consistent rehash mutation campaign now includes absent/future source-ancestor availability. The independent verifier rejects the source; the runtime localizes the future/missing time blocker to the dependent strategy while S1/S4 remain ready on the independent fixture evidence.
- Scoped outcomes before the V17 additions: graph **61 passed**, combined campaign **268 passed**, supplied feed regression **73 passed**, all with two optional pandas dependency warnings.


## V17 crash recovery and multi-process publication proof

- Added `test_manifest_publication_recovers_after_process_death_before_atomic_link`: a child exits immediately after the temporary manifest file is fsynced and before the no-clobber atomic link. The interrupted file is not discoverable as a manifest or indexed head; a retry publishes, independently verifies, registers, and resolves exactly one immutable manifest. The crash may leave a dot-prefixed temporary file, which is non-authoritative.
- Added `test_session_index_recovers_after_process_death_before_atomic_replace`: a child exits immediately before replacing a fully fsynced index temp file. The previously accepted index stays intact without the new row; retry atomically adds it and both entries resolve.
- Added `test_session_index_concurrent_process_writers_preserve_both_manifests`: two independent Python processes concurrently register distinct verified manifests into one session index; both entries must survive and resolve. This covers OS process locking beyond the earlier thread-level fixture.
- All three fault-injection controls pass. The manifest crash leaves no accepted manifest/index head; the index replacement crash preserves the prior valid index and the new row appears only on retry; independent concurrent process writers preserve both entries. Final validation before the added venue mutation: graph suite **64 passed**, combined scoped campaign **271 passed**, and the exact V17 command **5 passed**, each with two optional pandas dependency warnings. The fixtures prove publication recovery and index concurrency only. It does not prove filesystem power-loss guarantees on every mounted volume or source-data authority.


Final commands at the V17 validation checkpoint:

```bash
/opt/anaconda3/bin/pytest -q tests/test_cas_primitive_producer.py tests/test_cas_evaluation_ledger.py tests/test_market_heritage_graph.py tests/test_kite_read_only_observation_runtime.py tests/core/test_runtime_snapshot_producer.py tests/core/test_read_only_coverage_ledger.py tests/paper_shadow/test_strategy_shadow_adapters.py tests/test_causal_strategy_and_truth.py tests/test_read_only_consumer_cycle.py tests/test_v23_production_equivalent_harness.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_cas_coordinator_lifecycle.py tests/core/test_observation_lineage.py tests/core/test_tick_store_db_truth.py tests/core/test_market_snapshot_builder.py tests/test_tick_store.py tests/test_ws_tick_ingestion_updates_tick_store.py tests/test_pulse_issues_and_feed_consistency.py tests/paper_shadow/test_t1_prerequisites_authority.py
/opt/anaconda3/bin/pytest -q tests/test_market_heritage_graph.py
/opt/anaconda3/bin/pytest -q tests/test_market_heritage_graph.py::test_manifest_publication_recovers_after_process_death_before_atomic_link tests/test_market_heritage_graph.py::test_session_index_recovers_after_process_death_before_atomic_replace tests/test_market_heritage_graph.py::test_session_index_concurrent_process_writers_preserve_both_manifests tests/test_market_heritage_graph.py::test_verified_heritage_publisher_independently_checks_then_indexes tests/test_market_heritage_graph.py::test_verified_heritage_publisher_does_not_publish_future_dependency
/opt/anaconda3/bin/python -m compileall -q core/kite_depth_ws.py core/market_heritage_graph.py core/market_heritage_verifier.py core/cas_primitive_producer.py core/cas_evaluation_ledger.py core/read_only_coverage_ledger.py core/observation_lineage.py core/kite_read_only_observation_runtime.py core/runtime_snapshot_producer.py core/canonical_cycle_coordinator.py core/read_only_consumer_cycle.py core/paper_shadow/strategy_shadow_adapter.py scripts/generate_t1_prerequisites.py scripts/verify_t1_prerequisites_oracle.py
git diff --check
```


## Final acceptance-matrix audit

- V03 now includes an explicit wrong prior-source venue mutation in `test_t1_assembler_fails_closed_on_incomplete_or_mismatched_evidence`; the targeted parameterized test passed **5 cases**, including wrong date, wrong venue and future-source controls.
- Corrected V08's stale test reference to `test_claim_completion_and_restart_are_idempotent`.
- V07 is explicitly partial: prior verified process downtime is reported, but intraprocess cadence and continuous-coverage readiness remain `UNKNOWN_EXPECTED_CADENCE_NOT_PROVIDED`. Frozen strategy specs reviewed here do not define a per-token cadence, so no threshold was invented.
- Final rerun after the venue case: graph suite **65 passed**, combined scoped campaign **272 passed**; each reported two optional pandas dependency warnings.


## Operator runbook measurability update

- Expanded `NEXT_READ_ONLY_LIVE_VERIFICATION_RUNBOOK.md` with process/open-handle stability checks, producer SHA and safety-contract admission, explicit prohibition on broker login/profile calls, source-event clock separation, independent manifest verification, per-edge join counts, cadence-unknown behavior, and a required append-only operator run record.
- The runbook remains `LIVE_VERIFICATION_PENDING` and was not executed. It grants no runtime or broker authority and directs the operator to defer when a writer is active.
- Validation: `git diff --check` passed; no runtime code, configuration, protected source data, or behavior changed.


## Stable stopped-run evidence recheck

- Verified no current `ps` entry for recorded PID 82150 and no observer child under Antigravity scheduler PID 1167. Canonical checkout `run_all.sh` PID 1403, watchdog PID 1469, and scheduler PID 67023 remain active and untouched. Exact `lsof` checks were empty for selected artifacts; every file read was checked as a regular non-symlink file with unchanged inode/size/mtime before and after read. No runtime process or schedule was modified.
- Hash-bound shutdown evidence now records `PARTIAL`/`FAILED`, incomplete persistence drains, 50,801 pending tick writes, 330 worker failures, expired drain deadline and no final flush. The process identity remains stale `RUNNING` and records source branch SHA `12d01da414d9a1ffc13718390e2c950c9f621bfd`, not the integration SHA.
- Feed truth is DEGRADED with 95 blockers; per-token coverage and same-day heritage artifacts are absent; CAS targets remain blocked/null. The recurring Antigravity weekday trigger for the supplied worktree remains present with no child. See `SOURCE_AND_HERITAGE_MANIFEST.json` for exact hashes and typed statuses.
- Result: runtime proof fails clean-shutdown, integration-SHA, and coverage-artifact checks. This does not invalidate synthetic code tests, but prohibits live/runtime acceptance claims.

## Agent Work Contract

```yaml
source_agent: hermes_then_gsd
action: PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
title: PR939 CI blocker repair
scope: Repair verified hosted CI failures while preserving read-only authority and the frozen SQLite tick contract.
requested_paths: .github/workflows/pr782-remaining-evidence-contracts.yml, .gsd-forensics.yaml, core/kite_read_only_observation_runtime.py, core/market_snapshot_builder.py, docs/agent_reviews/{FINAL_VERDICT,GSD_IMPLEMENTATION_CHANGESET,HERMES_SESSION_CONTINUITY_HERITAGE_CONTRACT,NEXT_READ_ONLY_LIVE_VERIFICATION_RUNBOOK}.md, tests/core/test_market_snapshot_builder.py, tests/test_candidate_pipeline_architecture_repair.py, tests/test_code_excellence_cerberus_gate.py, tests/test_code_excellence_evidence_gate.py, tests/test_read_only_observation_storage_binding.py
allowed_paths: listed requested paths only
forbidden_paths: credentials, environment files, order/execution/risk/strategy behavior, broker API invocation, runtime session artifacts
expected_tests: affected regression suites, unified Code Excellence gates, full pytest suite, required hosted PR checks
acceptance_proof: exact-SHA green required CI, zero gate blocks, exact changed-path reconciliation, no runtime/broker activity
```

This continuation repairs concrete PR #939 CI failures only: stacked-PR scope validation, failing focused tests, review/evidence gate policy, and required review record sections. No runtime was started.

## Scope Guard

Changed paths are controlled by the exact candidate diff and PR782 workflow allowlist. No credentials, broker calls, orders, risk gates, strategy thresholds, or live configuration were changed.

## Grill Me Review

No external Grill Me review is claimed. Self-review retains actual API event facts as telemetry and does not falsify them to satisfy an authority policy.

## Hermes Review

The bounded 12-field SQLite tick schema remains unchanged. Snapshot assembly uses the SQLite getter and explicitly marks absent persisted callback identity as `UNAVAILABLE`; it does not synthesize lineage.

## GSD Review

Focused regressions passed locally after the repair. Hosted checks are authoritative for the final candidate SHA; no pending result is considered acceptance.

## QA / Safety Review

Changes and tests are offline. Explicit broker-write, order, paper, and live authority fields remain fail-closed. No runtime or broker path was invoked.

## Acceptance Proof

Acceptance requires exact-SHA green required CI, passing review-evidence validation, clean diff checks, and reconciled changed-path count. Record final SHA and check URLs after publication.

## Runtime Proof Required After Merge

A separate operator authorization and a same-SHA read-only session with complete drain evidence remain required. This CI repair is not runtime proof.

## What This PR Does Not Prove

It does not prove T-1 source admission, market-data quality, live observation readiness, strategy edge, execution readiness, or `LIVE_VERIFIED`.

## Human Approval

The user authorized CI repair work. This does not authorize merge, runtime observation, broker calls, credential access, or order authority.

## High-Risk Path Review

`core/kite_depth_ws.py` remains within previously scoped read-only observer work and is not changed by this CI repair. `core/market_snapshot_builder.py` now reads the SQLite getter and labels absent event identity `UNAVAILABLE`; no execution authority is added.
