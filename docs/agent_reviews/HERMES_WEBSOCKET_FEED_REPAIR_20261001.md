# WebSocket Feed Health Repair Contract

```yaml
source_agent: hermes
action: DESIGN_ARCHITECTURE
title: Restore symbol-scoped feed eligibility and truthful startup verification
scope: Offline source repair for launch-plan metadata, option verification, and per-symbol feed truth; preserve all configured coverage and freshness requirements
requested_paths:
  - core/kite_depth_ws.py
  - core/feed_health_truth.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_edge43_feed_health_truth.py
  - docs/agent_reviews/HERMES_WEBSOCKET_FEED_REPAIR_20261001.md
  - docs/agent_handoffs/WEBSOCKET_FEED_REMEDIATION_20261001.md
allowed_paths:
  - core/kite_depth_ws.py
  - core/feed_health_truth.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_edge43_feed_health_truth.py
  - docs/agent_reviews/HERMES_WEBSOCKET_FEED_REPAIR_20261001.md
  - docs/agent_handoffs/WEBSOCKET_FEED_REMEDIATION_20261001.md
forbidden_paths:
  - config/
  - credentials.py
  - environment files and access tokens
  - runtime/live*
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - strategies/
  - any running process or production data mutation
expected_tests:
  - tests/test_kite_depth_ws_stability.py
  - tests/test_edge43_feed_health_truth.py
  - tests/test_feed_00_canonical_feed_truth.py
acceptance_proof:
  - Launch-plan option metadata is transferred into startup verification only when production-resolution rows reconcile exactly with production tokens and the final token union includes all production tokens.
  - Missing verification scope cannot become an OK verification result.
  - A producer-declared symbol aggregate can be scoped only when an explicit global-block field is false, transport is connected, and every evaluated symbol has block-reason and freshness evidence.
  - Explicit global blocks, disconnected transport, unsafe state, stale data, and missing requested-symbol evidence still block.
  - No configuration limits, thresholds, credentials, broker/order/risk paths, or live processes are changed.
```

## Evidence and problem statement

The observed session artifact generated at 2026-10-01 12:08:56 IST reported a connected WebSocket, 97 option tokens, 53 symbols passing the reconnect tick window, and `feed_ok=false` / `feed_truth_state=DEAD`. Its feed-health artifact remained degraded. The 11:28 connect log showed zero requested/subscribed per-symbol option maps, selected 150 fallback tokens, and emitted `FEED_OPTION_VERIFY_AUTO_OK`. At 12:08 the reconnect log contained populated symbol maps and a 53-symbol verification set. These records show both a startup metadata gap and a later distinction between reconnect verification and continuous symbol freshness.

The active launch plan configured a 150-token budget for 53 underlyings and resolved 97 option tokens. Its production resolution rows report final per-symbol option counts below the existing `option_min_required=12`. The configured budget predates the reviewed PR window and is outside this contract: do not raise it, lower the minimum, or claim provider capacity without a separately scoped approval and evidence.

PR #943 introduced the current symbol-aware feed-health classifier. It permits a false aggregate health value to be scoped only when the input declares `feed_ok_scope="symbol_aggregate"`; the observed producer input did not carry that scope, so the classifier represented it as `global_or_unknown` and emitted `global_feed_unhealthy`. For symbol-specific consumers, complete per-symbol evidence can safely identify whether the requested symbol is healthy. Whole-feed decisions must continue to consider every monitored symbol and remain degraded when any required symbol is blocked.

## Invariants

1. Authentication and WebSocket connectivity are global transport facts. A disconnected or unknown transport does not pass a symbol-specific check.
2. A global recovery block, unsafe feed/runtime state, explicit global blocker, or required-domain failure remains a hard block.
3. A false aggregate feed flag may be scoped only when the producer explicitly declares `feed_ok_scope="symbol_aggregate"`, `global_feed_blocked` is explicitly false, WebSocket connectivity is true, and every evaluated symbol has both block-reason and freshness evidence. Each evaluated symbol is still checked with existing rules and freshness thresholds. An unscoped false value remains a global blocker.
4. Missing or malformed launch-plan symbol metadata never implies verified health. The empty required-symbol case is blocked/failed, not OK.
5. Startup/reconnect verification is not ongoing freshness proof and does not override per-symbol `option_feed_block_reason`, tick age, subscription minimums, or feed-health gates.
6. Preserve `MIN_OPTION_TOKENS`, all existing freshness thresholds, and the configured subscription budget. Incomplete coverage remains explicitly ineligible.
7. This work is read-only with respect to broker and order capabilities: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`.

## Implementation design

- On launch-plan activation, derive option-token counts, per-symbol minimums, and token-to-symbol identity from `production_resolution`; validate counts against production tokens and require production tokens to be present in the final union. Observation tokens may expand the final union. Invalid or incomplete metadata must remain unavailable and block option verification rather than fabricate identity.
- In option verification, require evidence for the expected symbols. An empty expected set records a blocked verification state with a concrete reason. Do not change callback/reconnect policy or token selection.
- In runtime snapshot production, identify `feed_ok` as a symbol aggregate and emit an explicit global-block boolean derived from transport/recovery state. In feed-health classification, honor that scope only under invariant 3. Keep the existing hard global blockers and per-symbol freshness/error checks.
- Add behavior tests for positive scoped selection and each negative control. Tests use synthetic in-memory payloads/monkeypatches only and never start a live runtime or call a broker.

## Risks and boundaries

- The patch can allow a healthy explicitly requested symbol through an unrelated symbol's aggregate failure, but cannot restore missing ticks or make an under-covered symbol healthy.
- The observed 150-token plan cannot satisfy 12 option tokens for every symbol in the 53-symbol universe. No code in this patch will widen the configured budget or narrow the universe automatically.
- Current PIDs remain on the deployed commit and do not receive this code. Deployment requires a later operator-controlled session after separate review and capacity proof.

## Stage 1 addendum — intermediate plan activation regression

Read-only verification of the October 1 live artifact and exact source at `a79dfb46ef70fe2a19b22db16c131774c31adec6` found a regression in the initial remediation: `build_subscription_tokens()` constructs an intermediate observation-merge mapping without `production_resolution`, then calls `activate_market_event_graph_launch_plan()` before it assembles final per-symbol resolution rows. The strict activation function interpreted this incomplete intermediate mapping as malformed and cleared `_TOKEN_TO_SYMBOL`, `_UNDERLYING_TOKEN_TO_SYMBOL`, option counts, and minimums. The builder then derived zero option counts for every symbol. Live logs show the metadata-block event at 13:28:07 and empty-scope verification failures at 13:28:08; the persisted plan shows 70 option tokens outside the zero-option resolution rows. This explains the option attribution and feed-health failure. The exact process-exit cause remains unresolved.

### Revised implementation contract

- The intermediate observation merge may update only observation-plan state; it must not call the full launch-plan metadata validator or mutate token-to-symbol/count/minimum maps.
- The full `activate_market_event_graph_launch_plan()` path remains strict for actual launch plans and clears stale metadata on malformed authoritative plans.
- A regression test must exercise `build_subscription_tokens()` with a synthetic, read-only registry and assert resolved option token ownership and per-symbol counts survive observation-plan activation.
- No direct token-to-symbol inference from an unassociated token list; no provider calls; no live process action; no threshold/budget changes.

```yaml
source_agent: hermes
action: DEFINE_CONTRACT
title: Preserve resolved option identity across intermediate observation merge
scope: Repair the intermediate observation-plan state update and add a regression test
requested_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_ws_stability.py
  - docs/agent_reviews/HERMES_WEBSOCKET_FEED_REPAIR_20261001.md
allowed_paths:
  - core/kite_depth_ws.py
  - tests/test_kite_depth_ws_stability.py
  - docs/agent_reviews/HERMES_WEBSOCKET_FEED_REPAIR_20261001.md
forbidden_paths:
  - config/
  - credentials.py
  - environment files and access tokens
  - runtime/live*
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - strategies/
  - any running process or production artifact
expected_tests:
  - tests/test_kite_depth_ws_stability.py
acceptance_proof:
  - Intermediate merge preserves option and underlying symbol maps and option counts.
  - Full launch-plan activation remains fail-closed on invalid metadata.
  - No token ownership is inferred from unassociated tokens.
  - No live/runtime/configuration change occurs.
```

## Stage 2 execution record

- `core/kite_depth_ws.py`: intermediate observation merge now updates only observation-plan state through `_set_observation_plan_state()`; strict full launch-plan validation remains on the actual launch-plan activation path.
- `tests/test_kite_depth_ws_stability.py`: added an in-memory observation-merge regression test verifying option and underlying token mappings plus per-symbol option counts survive the intermediate state update.
- Focused validation passed: 124 tests across WebSocket stability, observation callbacks, feed health truth, and canonical feed truth; an additional 17 direct subscription-token tests passed. `git diff --check` passed.
- Two environment warnings remain: installed `numexpr` and `bottleneck` versions are below pandas' declared recommendations.
- The patch is local to the isolated worktree, not deployed. The inspected live PIDs are absent now; no PID action was taken. The exact reason the process tree exited remains unproven.

## Follow-up scope addendum — symbol safety and LIVE readiness

```yaml
source_agent: hermes
action: DEFINE_CONTRACT
title: Require explicit producer authority for symbol-scoped health and complete LIVE preflight coverage
scope: Preserve explicit transport/global-health authority at symbol execution safety and prevent partial per-symbol option coverage from passing LIVE preflight
requested_paths:
  - core/symbol_execution_safety.py
  - core/pre_live_readiness_gate.py
  - tests/test_edge45_symbol_execution_safety.py
  - tests/test_kite_depth_ws_observation_on_ticks.py
  - tests/test_pre_live_readiness_gate.py
  - docs/agent_reviews/HERMES_WEBSOCKET_FEED_REPAIR_20261001.md
allowed_paths:
  - core/symbol_execution_safety.py
  - core/pre_live_readiness_gate.py
  - tests/test_edge45_symbol_execution_safety.py
  - tests/test_kite_depth_ws_observation_on_ticks.py
  - tests/test_pre_live_readiness_gate.py
  - docs/agent_reviews/HERMES_WEBSOCKET_FEED_REPAIR_20261001.md
forbidden_paths:
  - config/
  - credentials.py
  - environment files and access tokens
  - runtime/live*
  - core/execution*
  - core/broker*
  - core/order*
  - core/risk*
  - strategies/
  - any running process or production data mutation
expected_tests:
  - tests/test_edge45_symbol_execution_safety.py
  - tests/test_kite_depth_ws_observation_on_ticks.py
  - tests/test_pre_live_readiness_gate.py
acceptance_proof:
  - Aggregate feed degradation can be scoped to a healthy candidate symbol only when the producer declares symbol-aggregate scope, explicitly declares no global block, and supplies connected transport and complete per-symbol health evidence.
  - Symbol maps alone cannot establish that global transport or recovery state is clear.
  - LIVE preflight blocks positive aggregate coverage when any configured symbol is absent, degraded, or below its declared option minimum.
  - Option-verification tests isolate module-level minimum maps without changing production verification behavior.
  - No subscription budget, configured universe, auth, risk, broker/order, or live process behavior is changed.
```

## Agent Work Contract

The task is read-only feed diagnosis and offline source repair for option-token attribution, symbol-scoped feed truth, and readiness reporting. All modifications are limited to the code and tests in the two Hermes contracts above plus this review evidence. The work contains no broker calls, order actions, credential access, runtime configuration changes, or live process operations.

## Scope Guard

The code preserves existing option minimums and freshness checks. It does not alter the 150-token budget, reduce the symbol list, enable LIVE execution, or claim that depth persistence can sustain a wider subscription universe. The readiness fix reports insufficient coverage as a blocker.

## High-Risk Path Review

`core/kite_depth_ws.py` and `core/symbol_execution_safety.py` affect WebSocket/feed eligibility. The launch-plan path validates authoritative production-resolution metadata and clears invalid maps. The symbol-safety path accepts scoped aggregate degradation only with an explicit producer scope, `global_feed_blocked=false`, connected WebSocket evidence, and complete selected-symbol evidence. No threshold, credential, execution, broker, or order path was changed. Synthetic tests cover incomplete and valid scope evidence.

## Grill Me Review

- Could readiness report PASS when one configured symbol is absent? The new expected-symbol comparison blocks that case.
- Could a healthy symbol bypass an explicit transport/recovery block because another symbol is degraded? No; global block and disconnected or unknown transport remain hard blockers.
- Does this make all candidates eligible? No. It makes preflight truthful; tick freshness, depth persistence, strategy qualification, and other downstream gates remain authoritative.
- Does the queue-full evidence prove a single lock owner or a specific throughput bottleneck? No. Queue saturation remains a separately investigated operational issue.

## Hermes Review

The Stage 1 contracts above define authoritative producer scope, fail-closed missing coverage, existing minimum preservation, allowed paths, forbidden paths, and observable acceptance criteria. The implementation follows those contracts and retains negative outcomes when authority is missing.

## GSD Review

The Stage 2 changes implement the two scoped contracts, add behavior tests for both positive and negative feed-scope cases, add partial/missing/zero-option readiness cases, and isolate the required-option verification test from module-level state left by unrelated tests. No safety gate was weakened to satisfy tests.

## QA / Safety Review

The focused feed/readiness suite passed 95 tests before CI review. CI then found two additional issues: a legacy symbol-safety test omitted the newly required explicit global-clear/scope evidence, and an option-verification test depended on residual module-level minimum state. The tests and fixture authority have been corrected; the focused checks are being rerun. The first CI run also reported frozen-main baseline drift in unrelated files already present between the repository's pinned PR818 baseline and current `main`; this PR does not change the freeze gate or baseline.

## Acceptance Proof

Acceptance requires the focused feed, symbol-safety, option-verification, and readiness tests to pass; the agent-review evidence validator to pass against the exact PR head; and CI to retain all existing hard feed, freshness, recovery, and LIVE execution boundaries. The local 95-test result covers the original targeted suite; updated validation results will be recorded in the PR after fixes.

## Runtime Proof Required After Merge

Before claiming live readiness after a later operator-controlled rollout, capture exact deployed SHA, authenticated WebSocket state, connected transport, configured and verified per-symbol token counts, per-symbol tick/depth freshness, recovery proof state, depth-persistence queue/rejection metrics, candidate qualification/ranking outputs, and all blocker reasons. Keep the run read-only and do not infer healthy candidate flow from preflight alone.

## What This PR Does Not Prove

This PR does not prove the persistence queue can keep up with the full configured universe, identify the cause of every queue rejection or process exit, guarantee that market data is fresh, establish strategy edge, guarantee candidate availability, certify auth for a future session, or authorize live deployment or order execution.

## Human Approval

The user authorized investigation, fixes, and PR creation. No merge, live rollout, process restart, token-budget change, universe change, or order execution is authorized by this evidence. Those actions remain subject to explicit operator control and the repository's normal review gates.
