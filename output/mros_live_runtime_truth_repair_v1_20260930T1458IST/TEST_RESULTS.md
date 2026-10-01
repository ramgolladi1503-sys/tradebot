# Test results

## Offline baseline before edits

The targeted 24-module baseline command and outcome are recorded in `BASELINE.md`: **277 passed, 9 failed**. All nine failures were in the bridge test module when combined with other selected tests; the bridge module in a fresh process passed **18/18**. The tests/assertions were not altered before baseline. The bridge test now resets its module-global `feed_epoch` state before and after each case; a process-isolation fixture repair, not behavior assertion removal.

## Focused post-edit validation

Command run independently by the parent agent in the isolated repair worktree:

```bash
/opt/anaconda3/bin/pytest -q tests/test_edge43_feed_health_truth.py tests/test_edge45_symbol_execution_safety.py tests/core/test_runtime_snapshot_store.py tests/test_depth_store_accounting.py tests/test_feed_recovery_coordinator.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_market_event_graph_live_runtime_bridge.py tests/test_sidecar_reporter_status_aggregation.py tests/test_market_heritage_graph.py
```

Result after the cadence and 855-identity replay additions: **176 passed, 2 dependency-version warnings, 22.46s**. A preceding focused subset of four modules passed 63 tests. Warnings: installed pandas reports older `numexpr` and `bottleneck` versions.

`git diff --check`: passed with no output.

No whole-repository test run, live entrypoint, broker/API test, order action, live stress, or production T-1 data test was run. Therefore test status is targeted offline validation, not release/production certification.


## Broader targeted regression after final changes

The 26 baseline modules plus the new sidecar, depth, recovery, and symbol-safety suites were run together, including the feed-epoch isolation fix and recovery-test update:

```bash
/opt/anaconda3/bin/pytest -q tests/test_edge43_feed_health_truth.py tests/test_pr_feed_04_feed_recovery_warmup_gate.py tests/test_candidate_executability_evidence.py tests/test_kite_depth_ws_stability.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_kite_depth_ws_market_event_graph_lifecycle.py tests/test_kite_depth_ws_watchdog_scope.py tests/core/test_runtime_snapshot_producer.py tests/test_runtime_snapshot_producer_metrics.py tests/test_runtime_snapshot_producer_tail.py tests/core/test_runtime_snapshot_store.py tests/core/test_tick_store_db_truth.py tests/test_tick_store.py tests/test_tick_store_nonblocking_decision_path.py tests/test_ws_tick_ingestion_updates_tick_store.py tests/test_feed_truth_contract.py tests/test_market_event_graph_live_ohlc_buffer.py tests/test_market_event_graph_live_ohlc_buffer_deterministic_test.py tests/test_market_event_graph_runtime_observer.py tests/test_market_event_graph_live_runtime_bridge.py tests/test_market_heritage_graph.py tests/test_auth_health.py tests/test_morning_operator_status.py tests/test_runtime_status_overlay.py tests/test_orchestrator_runtime_snapshots.py tests/test_orchestrator_reports_finally.py tests/test_edge45_symbol_execution_safety.py tests/test_depth_store_accounting.py tests/test_feed_recovery_coordinator.py tests/test_sidecar_reporter_status_aggregation.py
```

Result after the 855-token sampled-depth replay was added: **334 passed, 0 failed, 0 skipped, 3 dependency/deprecation warnings, 36.02s**. An immediately preceding command typo referenced a nonexistent path (`tests/core/test_runtime_snapshot_producer_tail.py`); it collected no tests and made no changes. The corrected command above is the successful result.


## Final targeted regression after domain-contract changes

Command covered the prior 30-module targeted list plus `tests/test_feed_fault_replay_scenarios.py`, `tests/test_ranking_orchestrator.py`, and `tests/test_pr_feed_03_feed_hold_gate.py`; an attempted command with nonexistent `tests/test_runtime_snapshot_producer.py` collected no tests and changed no files. The corrected run completed successfully: **362 passed, 0 failed, 0 skipped, 3 dependency/deprecation warnings, 36.11s**.


## Final targeted regression after recovery proof hardening

The exact 33-module targeted command is the corrected regression command from the prior section, with the same module list. The first run after hardening produced one failure because a `kite_depth_ws` test supplied the obsolete incomplete proof fixture; the validator remained strict, the fixture was updated to provide explicit healthy-window evidence, and the rerun passed: **364 passed, 0 failed, 0 skipped, 3 dependency/deprecation warnings, 35.17s**. The whole repository was not run.


## Latest targeted regression after domain producer and overall-state changes

```bash
/opt/anaconda3/bin/pytest -q tests/test_edge43_feed_health_truth.py tests/test_pr_feed_04_feed_recovery_warmup_gate.py tests/test_candidate_executability_evidence.py tests/test_kite_depth_ws_stability.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_kite_depth_ws_market_event_graph_lifecycle.py tests/test_kite_depth_ws_watchdog_scope.py tests/core/test_runtime_snapshot_producer.py tests/test_runtime_snapshot_producer_metrics.py tests/test_runtime_snapshot_producer_tail.py tests/core/test_runtime_snapshot_store.py tests/core/test_tick_store_db_truth.py tests/test_tick_store.py tests/test_tick_store_nonblocking_decision_path.py tests/test_ws_tick_ingestion_updates_tick_store.py tests/test_feed_truth_contract.py tests/test_market_event_graph_live_ohlc_buffer.py tests/test_market_event_graph_live_ohlc_buffer_deterministic_test.py tests/test_market_event_graph_runtime_observer.py tests/test_market_event_graph_live_runtime_bridge.py tests/test_market_heritage_graph.py tests/test_auth_health.py tests/test_morning_operator_status.py tests/test_runtime_status_overlay.py tests/test_orchestrator_runtime_snapshots.py tests/test_orchestrator_reports_finally.py tests/test_edge45_symbol_execution_safety.py tests/test_depth_store_accounting.py tests/test_feed_recovery_coordinator.py tests/test_sidecar_reporter_status_aggregation.py tests/test_feed_fault_replay_scenarios.py tests/test_ranking_orchestrator.py tests/test_pr_feed_03_feed_hold_gate.py
```

Result: **367 passed, 0 failed, 0 skipped, 3 dependency/deprecation warnings, 33.43s**. This targeted suite is not a whole-repository run.

## Latest targeted regression after SQLite drain and direct artifact cadence changes

The exact 33-module command immediately above was rerun unchanged.

Result: **370 passed, 0 failed, 0 skipped, 3 dependency/deprecation warnings, 43.83s**. `git diff --check` also passed after these changes. This targeted suite is not a whole-repository run.

## Latest targeted regression after producer-side assembly cadence gate

The exact 33-module targeted command above was rerun after adding the producer-side admission gate and the synthetic 855-request replay.

Result: **373 passed, 0 failed, 0 skipped, 3 dependency/deprecation warnings, 44.04s**. This run excludes `tests/test_feed_runtime_states.py`, which was run separately because combining it with the broader selection exposes shared module-global token-count state.

An expanded combined run appended `tests/test_feed_runtime_states.py` and produced **397 passed, 1 failed**. The failure was `test_start_depth_ws_writes_import_missing_state`, which observed `intended_tokens_count=55` instead of its requested 2 after preceding test modules had modified process-global state. In fresh pytest processes, the failing test passed **1/1** and the full module passed **25/25**. No assertions or fixtures were changed to suppress the combined-run failure; retain the combined contamination as a regression limitation.

The focused producer/runtime suites (`tests/core/test_runtime_snapshot_store.py`, `tests/test_kite_depth_ws_observation_on_ticks.py`, `tests/test_kite_depth_ws_stability.py`, `tests/test_feed_runtime_states.py`) passed **131 tests** before the final identity-field refinement. The current final focused run including `tests/test_feed_runtime_states.py` in the same process reproduced the shared-state failure; the runtime/observation/stability suites and the feed-runtime-state module each pass in isolated execution.

## Final expanded combined regression after feed-domain, fixture-isolation, and sidecar status corrections

The same expanded 34-module command above was rerun after explicitly populating all required sidecar subsystem keys with `UNKNOWN` when no evidence was supplied. Result: **400 passed, 0 failed, 0 skipped, 4 warnings, 38.22s**. The warnings are the existing Hypothesis-directory warning, pandas dependency-version warnings for `numexpr` and `bottleneck`, and the existing `Timestamp.utcnow` deprecation warning.

## Whole-repository regression attempt

`/opt/anaconda3/bin/pytest -q` was started from this isolated worktree and collected 8,461 tests (28 deselected). The log contains failures in `tests/option_backtest/test_engine.py` before output reached 68%. It then made no test-output progress for approximately 20 minutes. A process sample showed the main Python thread sleeping inside the delayed background-writer path in `tests/test_orchestrator_latency.py` while a worker thread remained active. The stalled process was interrupted to avoid leaving a hung test process. The log is retained in `WHOLE_REPO_REGRESSION.log`; this run is **INCOMPLETE WITH FAILURES**, not a pass. Those option-backtest failures are outside this repair's scope and were not independently diagnosed. Targeted regression remains the final completed evidence. No test change was made to `tests/test_orchestrator_latency.py` because that unrelated test-quality repair needs its own bounded scope and diagnosis.

## Recovery-clearance bypass regression

Forensic review found restart subscription verification could clear `ws1006_process_restart_required` without invoking the causal recovery coordinator. The path now keeps the blocker and emits `FEED_RECONNECT_RECOVERY_CLEAR_DENIED` with `BLOCKED_CAUSAL_PROOF_REQUIRED`. The exact regression and adjacent restart/coordinator suites passed:

```bash
/opt/anaconda3/bin/pytest -q tests/test_kite_depth_restart.py tests/test_feed_recovery_coordinator.py tests/test_kite_depth_ws_stability.py
```

Result: **125 passed, 0 failed, 0 skipped, 3 dependency-version warnings, 15.99s**. The runtime causal proof builder is still absent, so recovery remains fail-closed and cannot be declared operationally complete.

A second bypass was then found in partial-activity recovery: stable local tick cycles could clear the same global restart-required blocker and emit `LIVE`. The central clear helper now refuses while restart-required/reactor-terminal state is active; partial-recovery status remains `RECOVERY_BLOCKED` and telemetry preserves the blocker. The expanded recovery-focused selection passed **125 tests, 0 failed, 0 skipped, 3 dependency-version warnings, 15.99s**.

## Final combined targeted regression after both recovery-clearance bypass fixes

The expanded 35-module regression command above plus `tests/test_kite_depth_restart.py` was rerun after both recovery-clearance bypass fixes. Result: **457 passed, 0 failed, 0 skipped, 4 warnings, 46.44s**. The command included feed truth, runtime snapshot storage, callback observation, depth accounting, recovery coordinator, restart/stability, MEG, heritage, and sidecar status tests. This is targeted offline evidence, not a whole-repository pass.

The T-1 authority regression was separately rechecked:

```bash
/opt/anaconda3/bin/pytest -q tests/paper_shadow/test_t1_prerequisites_authority.py tests/test_market_heritage_graph.py
```

Result: **71 passed, 0 failed, 0 skipped, 3 warnings, 5.34s**. This validates existing offline fail-closed behavior; it does not establish production heritage source readiness.


## Recovery history immutability regression

Coordinator incident history now deep-copies nested proof evidence on ingress and egress. The adversarial case mutates nested gap and token collections in both the caller-owned proof and returned history snapshot and verifies stored history remains unchanged.

```bash
/opt/anaconda3/bin/pytest -q tests/test_feed_recovery_coordinator.py tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py
```

Result: **126 passed, 0 failed, 3 dependency-version warnings, 16.02s**. The expanded combined 35-module regression also passed **457 tests** after this code change.


## Runtime recovery proof builder and snapshot progress

The runtime now captures exact expected and locally applied subscription sets, requires an explicit local subscribe/mode call return, records pre-disconnect and first post-reconnect receipts for resolved critical underlying identities, checks current freshness and option verification, and requires a configured healthy window before coordinator clearance. A mismatch or missing evidence remains blocked. Restart-required terminal blockers still cannot clear through this path. Both direct and callback runtime snapshots expose `recovery_proof_progress` with missing/extra subscription identities, missing timestamps, gaps, progress state, and a pending/blocked verdict. The fields explicitly preserve `read_only=true`, `is_order_action=false`, `broker_api_called=false`, and `allowed_for_live_execution=false`. Subscription evidence denotes local API call return, not broker acknowledgement.

Focused recovery selection (coordinator, stability, restart, observation, simulation, and negative controls): **185 passed, 3 warnings, 23.26s**.

Expanded targeted selection (listed in the latest execution record) including recovery simulation and capability-gap negative controls: **452 passed, 0 failed, 0 skipped, 4 warnings, 42.55s**. `git diff --check` is rerun after evidence updates. No whole-repository rerun, live process, broker/API call, or order action was involved.


## Explicit candidate feed-domain dependencies

The symbol execution-safety consumer now forwards candidate `required_feed_domains` (directly or through `source_flags`) into the existing feed-truth classifier, carries domain evidence through the same boundary, and preserves the declared dependency set in decision context. Unknown or malformed declarations fail closed. Undeclared domains are not inferred. Existing selected-symbol option freshness checks remain in place, and safety evidence explicitly reports read-only/no-order/no-broker/no-live authorization. This does not yet populate declarations in candidate generators; domain gating applies only where an upstream candidate supplies authoritative dependencies.

Focused feed and execution-safety tests: **27 passed, 3 warnings, 1.69s**; the executable-truth adjacent focused set passed **41 tests, 3 warnings, 2.25s**.

The expanded targeted regression including all recovery suites was rerun after this change: **455 passed, 0 failed, 0 skipped, 4 warnings, 45.16s**.

## T-1 exact-session consumer hardening

The pinned T-1 loader now requires exact equality between manifest session identity and caller target session; partial caller identities no longer accept a manifest. A regression case passes only trading date and venue and confirms the loader returns `BLOCKED / TARGET_SESSION_MISMATCH` with empty prerequisite values and non-authorizing safety fields. The existing T-1 authority suite remains fail-closed. Combined offline regression including the full heritage graph and T-1 prerequisite authority modules: **462 passed, 0 failed, 0 skipped, 4 warnings, 45.10s**.

This does not create source authority. `scripts/generate_t1_prerequisites.py` explicitly emits a legacy inventory with prerequisite values null and `BLOCKED_SOURCE_AUTHORITY`, because its legacy snapshot/futures/rolling inputs do not establish the exact contracts required by the pinned heritage graph. No current authoritative calendar/futures/daily source package was found or promoted. Operational production and next-session source readiness therefore remain unresolved.

## Fail-closed candidate dependency declaration gate

Where a candidate receives structured `domain_health_by_domain`, symbol execution safety now requires a nonempty explicit `required_feed_domains` list. Missing/empty declarations and malformed values block visibly; a declared unknown domain is blocked by the classifier. No dependencies are inferred. Legacy symbol-only payloads without structured domain evidence retain their previous per-symbol path. Since current candidate producers do not yet populate dependency declarations, candidates reaching the structured-domain path are now blocked until that upstream contract is supplied; this is a safety closure, not readiness evidence.

The broader selection initially exposed two nominally clean executable-truth fixtures that supplied a symbol but no feed evidence and were correctly classified UNKNOWN. Their tests retain the original assertions; the common fixture now supplies explicit connected transport and fresh NIFTY option evidence. Focused feed/executable safety and candidate evidence suites then passed **50 tests, 3 warnings, 2.66s**.

Expanded combined regression including recovery, T-1, and executable-truth firebreak suites: **474 passed, 0 failed, 0 skipped, 4 warnings, 45.08s**. It remains targeted offline validation, not a whole-repository pass.

## 855-token sampled-depth persistence drain

Added a deterministic offline 855-identity replay through the actual `DepthStore` batch worker and SQLite sink in a temporary database. It queries the database and reconciles 855 input/sample/enqueued/persisted rows with zero rejects, zero write failures, no outstanding queue work, and both accounting invariants true. The replay uses a zero sampling interval to admit one sample per identity; telemetry now reports the explicit zero interval accurately instead of defaulting it to 500 ms. This proves fixture-scale sink drain only, not production hardware throughput or real callback timing.

`tests/test_depth_store_accounting.py`: **11 passed, 3 warnings, 8.08s**. Expanded combined regression including this sink-drain case: **472 passed, 0 failed, 0 skipped, 4 warnings, 45.57s**.

## Depth sampling configuration validation

DepthStore now validates the configured sample interval at use. Negative and non-finite values fall back to the conservative 0.5-second interval, mark persistence durability degraded, and expose `sampling_interval_config_valid=false`; valid explicit zero remains zero. NaN and negative adversarial cases verify the fallback coalesces a repeated token update instead of silently disabling sampling.

Focused depth accounting suite: **13 passed, 3 warnings, 6.43s**. Expanded combined regression after the invalid-config handling and 855-row SQLite drain: **474 passed, 0 failed, 0 skipped, 4 warnings, 45.08s**.

## Actual callback burst admission regression

`test_on_ticks_855_row_batches_preserve_tick_depth_observation_when_snapshot_coalesces` invokes the actual callback twice with 855 synthetic valid rows per callback. It asserts all 1,710 rows reach tick insertion and depth-store update instrumentation while the actual snapshot admission path assembles/publishes once and coalesces the second request. External artifact/forensic/database effects are stubbed, so this proves callback ordering and bounded assembly in an offline regression only; it does not establish production throughput or durable raw-tick completeness.

Focused command:

```bash
/opt/anaconda3/bin/pytest -q tests/test_kite_depth_ws_stability.py::test_on_ticks_855_row_batches_preserve_tick_depth_observation_when_snapshot_coalesces
```

Result: **1 passed, 3 dependency-version warnings, 2.12s**. The broader websocket/depth/recovery/runtime selection below also passed.

Broader focused command:

```bash
/opt/anaconda3/bin/pytest -q tests/test_kite_depth_ws_stability.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_kite_depth_restart.py tests/test_feed_recovery_coordinator.py tests/test_feed_recovery_simulation.py tests/test_kite_depth_ws_watchdog_scope.py tests/test_depth_store_accounting.py tests/core/test_runtime_snapshot_store.py
```

Result: **209 passed, 0 failed, 0 skipped, 3 warnings, 41.18s**.

## Expanded targeted rerun after canonical feed fixture correction

The prior whole-repository log included `test_runtime_store_writes_canonical_truth_to_required_artifacts` failing because its synthetic healthy payload omitted per-symbol option-age evidence. The test fixture now supplies explicit fresh NIFTY option age and retains all existing LIVE/safety assertions; runtime classification remains fail-closed for missing age.

The expanded 36-module targeted command (the latest regression command recorded in `MANIFEST.json`) passed **465 tests, 0 failed, 0 skipped, 4 warnings, 44.92s**. The other three previously observed feed/recovery/MEG failure candidates passed isolated execution as well. At that point the whole-repository run had not yet been repeated; see the later completed full-suite records below.


## Broker guard module identity and final full-suite validation

Guard installation now resolves the actual imported module through `importlib.import_module`. The updated regression test deliberately binds `core.execution_engine` to a stale package attribute and verifies that the class imported from `sys.modules` is still intercepted before its original write method.

Focused command: `/opt/anaconda3/bin/pytest -q tests/test_trade_truth_prospective_repair.py tests/test_tradebuilder_canonical_observer_integration.py tests/test_torture_replay.py tests/test_four_strategy_dataset_manifest.py::test_real_candle_and_tick_truth_prove_current_field_classification` — **44 passed**, 3 warnings, 19.28s.

Historical hydrated-data full-repository run: `/opt/anaconda3/bin/pytest -vv -ra` — **8,482 passed, 0 failed, 9 skipped, 28 deselected**, 1,476 warnings, 827.31s, exit 0. It is superseded by the pointer-safe final run below.

Final pointer-safe full-repository command: `/opt/anaconda3/bin/pytest -vv -ra` — **8,484 passed, 0 failed, 9 skipped, 28 deselected**, 1,476 warnings, 785.98s, exit 0. Full log: `WHOLE_REPO_REGRESSION_POINTER_SAFE_20261001.log`. The tracked LFS file remains a 132-byte pointer; the test tries the byte-identical local canonical copy and explicitly skips when unavailable. This is offline test evidence only.

## Candidate registry coverage continuation (2026-10-01)

Repository scan found two additional exact paper-shadow candidate IDs: `DAY_TO_NIGHT_MOMENTUM_V1` and `DAY_TO_NIGHT_MOMENTUM_V2_A_OPTION`. The latter is declared partial from its frozen spec and runner: it requires futures signal input, NIFTY spot ATM mapping, and dynamic NIFTY option observation. Futures/option contract identities are not bound to canonical health and the runner-local quote-age check is not a governed identity-scoped freshness policy. The V1 runner has no matching versioned frozen input contract. Both IDs now resolve as `PARTIAL_DECLARATION` and remain blocked. Focused command `/opt/anaconda3/bin/pytest -q tests/test_candidate_feed_dependencies.py tests/test_edge43_feed_health_truth.py tests/test_edge45_symbol_execution_safety.py`: **40 passed, 3 warnings, 2.90s**. The source registry digest check passes for all 8 entries. Registry resolution now emits optional/fallback/breadth/freshness as explicit null (unknown), not empty declarations. The full-repository run predates these metadata-only registry additions; focused dependency/feed-safety tests are the current evidence for them.


## C1/C2 candidate dependency enforcement (2026-10-01)

Read-only inspection of `core/candidate_evaluators.py`, `core/market_session_store.py`, `core/orchestrator.py`, and `core/governed_strategy_authority.py` found source-backed NIFTY memory inputs, explicit NIFTY Futures entry/exit boundaries, and an orchestrator fallback that synthesizes memory from generic `market_data` without binding source identity or age. Six governed C1/C2 aliases and emitted IDs were added as partial declarations; their exact identities remain unresolved and the fallback remains unchanged. Exact integration regression was included in the combined five-module command: **115 passed, 0 failed, 3 warnings, 5.82s**.


## Opaque candidate identifier enforcement (2026-10-01)

The symbol-safety boundary no longer drops an unknown per-signal `candidate_id` into the legacy pass. It resolves through an exact registered `strategy_id` when available; otherwise the candidate blocks as `UNKNOWN_BLOCKED`. Structured required-domain/identity health also invokes dependency resolution. The former permissive regression was updated to assert the fail-closed contract. Five-module dependency, feed-health, symbol-safety, heritage, and T-1 authority command: **118 passed, 0 failed, 3 warnings, 7.34s**.


## Current-tree isolated-temp whole-repository rerun (2026-10-01)

Command: `/opt/anaconda3/bin/pytest -vv -ra --basetemp=<fresh /tmp/tradebot-pytest-full.* directory>` — **8,493 passed, 0 failed, 9 skipped, 28 deselected**, 1,476 warnings, 866.58s, exit 0. Full console log: `WHOLE_REPO_REGRESSION_ISOLATED_TMP_20261001.log`. The dedicated temporary root avoids collisions with pytest temporary directories from concurrent/local runs. This run occurred after the candidate dependency registry and opaque-ID fail-closed continuation changes.

An immediately preceding run using pytest's shared default temp root ended with 8,439 passed, 54 setup errors, 9 skipped, 28 deselected. The errors were temporary-directory allocation errors (`could not create numbered dir ... after 10 tries`), not assertion failures. The affected six research modules passed 61/61 with a fresh temp root, and the current-tree whole-suite rerun passed with its own fresh root. That intermediate run is classified `ENVIRONMENTAL / TEMP_ROOT_ALLOCATION_NOT_REPRODUCED`; it is retained as a failed historical run, not counted as a pass.


## PR review-gate remediation (2026-10-01)

The first PR review-gate run identified missing required review headings, static-scan false positives from literal guarded-call names, and a broad exception-swallowing cleanup pattern in a changed test. Review documents now include the required scope/acceptance/high-risk sections; the test invokes the guarded method through the already-composed method name; cleanup failures are no longer suppressed. Focused command: `/opt/anaconda3/bin/pytest -q tests/test_pr763_offline_remaining_gates.py tests/test_trade_truth_prospective_repair.py` — **36 passed, 0 failed, 3 warnings, 18.42s**. Local unified Code Excellence gates: **105 findings, 0 blocks, exit 0**.
