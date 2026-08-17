# Observation Execution Guard and Clean Launcher Review

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Add fail-closed observation execution guard and clean exact-SHA launcher
- scope: Observation-only execution boundary, external credential injection, isolated runtime manifest, and focused tests
- requested_paths: `core/execution_engine.py`, `core/execution_adapter.py`, `core/broker/mock_broker.py`, `core/observation_execution_guard.py`, `scripts/run_clean_observation_session.py`, focused tests
- forbidden_paths: strategy, feed/WebSocket, broker credentials, live launchers, launchd, cron, PR813/PR814/PR815, MROS, CAS, ranking
- expected_tests: focused guard/launcher tests and execution/read-only regressions
- acceptance_proof: observation mode blocks routeable intent and all covered write boundaries; launcher fails closed on authority, SHA, tree, credential, and runtime violations

## Scope Guard

The implementation does not change strategy selection, market-data ingestion, feed recovery, broker credentials, launchd, cron, or live execution configuration. The launcher never kills processes, deletes locks, or uses broad process controls.

## High-Risk Path Review

`core/execution_engine.py`, `core/execution_adapter.py`, and `core/broker/mock_broker.py` are high-risk execution paths. The guard is inserted before `ExecutionEngine.place_order()` creates intent/order state. Adapter and mock-broker write methods independently reject observation mode. Non-observation behavior is unchanged because the guard is inactive unless `OBSERVATION_ONLY_MODE=true`.

## Grill Me Review

- Could execution-enabling flags override observation mode? No; the guard is evaluated before intent creation and rejects conflicting flags.
- Could the submit callback run? No; the execution boundary raises before callback dispatch.
- Could the launcher contaminate the repository? It rejects repository-contained credential/runtime paths and writes only to an external session namespace.
- Could it create duplicate producers? It starts one direct `main.py` subprocess and does not run supervisors or sidecar launch loops.

## Hermes Design Review

The design uses one shared runtime predicate, defense-in-depth at adapter/broker boundaries, explicit external path contracts, and a pre-start non-secret manifest. It avoids a new configuration system and reuses existing `DATA_ROOT`, `LOGS_ROOT`, `REPORTS_ROOT`, `LOCKS_ROOT`, and `DB_ROOT` environment overrides.

## GSD Implementation Review

The candidate is based on the frozen exact SHA `556f3dc9750212618353ed07f76e11826a01a744`, includes the validated guard commit `96627ad8ed5f3c8b780df975c4a3ca10d3baaad5`, and does not modify either protected checkout.

## QA/Safety Review

Focused and regression tests prove callback non-invocation, no mock-broker mutation, flag-conflict rejection, exact-SHA/tree/path gates, manifest creation, and absence of broad process termination. No broker/API call or order action is used by tests.

## Acceptance Proof

- routeable intent creation: BLOCKED
- submit order callback: NEVER CALLED in observation mode
- place/modify/cancel: BLOCKED at covered boundaries
- paper/live routes: BLOCKED
- external credentials: required, presence-only in manifest, never copied or printed
- runtime evidence: external session namespace, `tracked_runtime_write_risk=false`

## Runtime Proof Required After Merge

After merge, independently re-freeze the exact `origin/main` SHA, prepare an external credential file and runtime root, run the launcher validation gate, and verify one healthy producer before attaching any read-only observers. Do not infer live readiness from this PR.

## What This PR Does Not Prove

This PR does not prove live feed health, broker connectivity, market-data freshness, observer completeness, profitability, live readiness, structural edge, or certification of H1, PR815, MROS/T35, CAS-A1, or Global Context.

## Human Approval

Required before merge and live use: human review of the execution-boundary diff, exact-SHA re-freeze, external credential source, runtime root, and post-merge dry startup gate.
