# Live Option Identity Launch Plan Contract

## Agent Work Contract

- `source_agent: hermes` for architecture, contract, workflow, and acceptance design; followed by `source_agent: gsd` for scoped implementation, tests, and verification.
- `action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS` for Hermes; `PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS` for GSD.
- `title: Fail closed on incomplete launch-plan token ownership`.
- `scope: Make production subscription resolution, launch-plan production, and runtime activation agree on ownership of production option, underlying, and sticky tokens. Derive resolution counts from the invocation-local production owner map, not the concurrently mutable process-global map. Reject malformed token arrays and plans before they advertise presession readiness. Preserve feed freshness, coverage, budget, recovery, and live-safety gates.`
- `requested_paths: core/market_event_graph_live_launch_plan.py; core/kite_depth_ws.py; tests/test_market_event_graph_live_launch_plan.py; tests/test_kite_depth_ws_stability.py; tests/test_depth_subscription_tokens.py; tests/test_kite_read_only_observation_entrypoint.py; docs/agent_reviews/live_option_identity_launch_plan_contract.md`.
- `allowed_paths: exactly the requested paths`.
- `forbidden_paths: credentials and environment files; runtime session data; broker, order, execution, risk, or strategy code; feed-gate weakening; live configuration; UI/dashboard; unrelated files`.
- `expected_tests: complete-plan closure; exact row/aggregate option counts; valid sparse zero-option rows; rejection of malformed, flat/unowned, or multiply-owned tokens; sticky-token accounting and activation; invalid-plan fail-closed behavior; offline replay of the October 1 incident shape`.
- `acceptance_proof: production_tokens equals the disjoint union of row-owned underlyings, row-owned options, and declared sticky tokens; production_underlying_tokens and production_option_tokens equal the identities derived from rows; every non-sticky token has exactly one symbol owner; declared counts match identity-derived counts; final option counts remain correct if the global ownership maps change during observation-plan merging; minimum-option, budget, freshness, recovery, read-only, and execution-safety gates remain unchanged; focused tests and required CI pass on the exact resulting SHA`.

## Evidence and Root Cause

The October 1 latest session launch plan declared 123 production token IDs, including 53 underlying IDs and 70 option IDs. Its per-symbol resolution rows did not account for the option IDs and included rows with empty token lists. The plan still carried a ready verdict. Runtime activation then rejected the incomplete rows, cleared option and underlying symbol maps, and left option verification and websocket recovery proof blocked. The runtime rejection is fail-closed and must remain so; the producer's readiness claim is the defect.

The incident plan is a regression fixture only. It is not permission to infer token ownership from current configuration, a flat token list, or unverified instrument data.

## Design

1. Treat each production-resolution row as the sole authority assigning a production index token and its option tokens to one symbol.
2. Derive expected underlying and option token sets from those rows. Require exact agreement with the corresponding top-level plan sets.
3. Treat sticky tokens as a separate, explicitly declared set. They must be present in production tokens and disjoint from row-owned tokens. At runtime activation, preserve their existing `STICKY` classification so they are not counted as option contracts.
4. Require a unique non-empty symbol per row, a positive index token included in that row's token set, no duplicate token within/across rows, and exact declared option counts. A row may have only its index token and zero options; this describes degraded coverage and does not pass option-health minimums.
5. Make invalid resolution prevent `PASS_LIVE_SOURCE_PRESESSION_READINESS`. Keep the existing runtime rejection and all downstream freshness, coverage, subscription-parity, recovery, and execution-safety gates intact.
6. Do not infer missing owners, silently omit unresolved tokens, raise the subscription budget, lower option minimums, generate synthetic bars, call brokers, or mutate runtime evidence.

## Workflow

Offline evidence -> launch-plan structural validation -> immutable hash-bound plan -> runtime activation revalidation -> exact subscription and per-symbol freshness checks -> websocket recovery proof. Any missing or inconsistent identity blocks at the first applicable stage. No offline pass grants trading authority.

## Acceptance Gates

- A valid multi-symbol plan with a sparse zero-option row and a separate sticky token remains structurally valid; health remains blocked where the option minimum is unmet.
- A plan with unowned option IDs, an incorrect underlying set, duplicate symbol ownership, or inconsistent counts cannot return a readiness-pass verdict and cannot be loaded as a valid ready plan.
- Runtime activation maps row-owned options and underlyings exactly, maps sticky tokens as `STICKY`, and continues to clear unsafe mappings for invalid plans.
- The captured October 1 incident shape (flat production option IDs not assigned to symbol rows) is rejected offline before runtime activation.
- No test calls broker APIs, performs order actions, enables live execution, writes to the captured session, weakens a safety gate, or treats empty candidate files as successful processing.
- Focused tests and required full CI are green on the exact final SHA. Post-merge live readiness remains unproven until separately collected read-only runtime evidence validates actual subscriptions and per-symbol option receipts.

## GSD Execution Scope

GSD may modify only the requested paths. If tests reveal a required change outside that list, stop and report it as a separate scope item. Do not merge or deploy as part of this contract.

## Scope Guard

This repair validates identities already produced by the option resolver. It does not infer token ownership, widen the subscription budget, relax option minimums, modify freshness/recovery gates, or enable execution.

## Grill Me Review

- The incident producer claimed 123 production IDs while row metadata did not own all IDs; a websocket connection and a ready verdict were insufficient evidence.
- The loader must reject unhashed readiness flags and derived-count tampering, not only malformed source rows.
- Sticky tokens must remain separate from per-symbol options; sparse zero-option rows remain degraded and downstream option-health minimums still block.

## Hermes Review

The producer, immutable-plan loader, runtime activation, and final per-symbol resolution must share one exact ownership contract. Rows are the authority for index and option identities; invocation-local mappings are authoritative during build. Missing or duplicate ownership blocks readiness.

## GSD Review

GSD implemented exact row ownership, strict token-array validation, aggregate count and safety-metadata checks, local-map option attribution, and regression tests. The captured incident plan is replayed offline and rejected before activation.

## QA / Safety Review

**High-Risk Path Review:** `core/kite_depth_ws.py` is a feed/WebSocket path. This change only validates and reports identity mappings; it does not call a broker, alter feed freshness or recovery gates, or change subscription capacity. Invalid data fails closed. Tests use offline fixtures and assert read-only/no-order/no-broker/no-live-authority fields.

## Acceptance Proof

The focused launch/feed/supervisor/lock tests pass. The October 1 captured launch plan rejects as `BLOCKED_BY_LAUNCH_PLAN_IDENTITY`; a synthetic 53-observation-token replay retains at least 12 local options for each configured index under the existing governed cap. Plan tampering of verdict, safety flags, and derived counts is rejected.

## Runtime Proof Required After Merge

In a later operator-controlled read-only run, bind the producer SHA and verify actual production token ownership, per-symbol option token receipts and fresh ticks, exact subscription parity, recovery proof, and global/per-symbol feed truth. A plan pass alone does not establish these runtime facts.

## What This PR Does Not Prove

It does not prove future broker subscriptions, fresh market data, option coverage in a live run, strategy quality, or live execution readiness. It does not resolve `INDEX_INTERVAL_MISALIGNED` by synthesizing bars.

## Human Approval

Human review is required for merge and any later runtime rollout. This contract grants no order, broker-write, or live-execution authority.

## Hermes Follow-On Contract: Full-Suite CI Regressions

- `source_agent: hermes`; `action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS`.
- `title: Keep production launch-plan identities separate from observation identities`.
- `scope: Repair PR #957's full-suite failures without changing the public subscription union semantics. A production launch-plan builder must obtain production-owned tokens and resolution rows from one invocation, before observation tokens are merged. The launch plan then merges the independently authorized observation set exactly once. The observation resolver must be called through one canonical, testable boundary so test import hooks cannot redirect it to a stale module object.`
- `requested_paths: core/kite_depth_ws.py; scripts/run_market_event_graph_live_session_v1.py; tests/test_depth_subscription_tokens.py; tests/test_run_market_event_graph_live_session_v1.py; docs/agent_reviews/live_option_identity_launch_plan_contract.md`.
- `allowed_paths: exactly the requested paths`.
- `forbidden_paths: broker/order/execution/risk/strategy code; credentials or environment files; runtime evidence; safety-gate weakening; synthetic or forward-filled market data; unrelated test shims or files`.
- `expected_tests: actual implementation retains local option ownership if the process-global symbol map changes during observation merge; production-only resolution contains no observation IDs; the final launch plan has disjoint production and observation sets and an exact final union; preflight without usable production metadata fails closed with zero claimed production tokens; existing default subscription callers retain their current merged-union behavior`.
- `acceptance_proof: the two reported full-suite failures reproduce before the repair and pass after it; affected focused tests pass; full `ci.yml` and `tests.yml` suites pass on the same exact SHA; all other PR checks remain green except the explicitly user-excluded PR818 gate. The diff does not change credentials, call broker APIs, place orders, alter budgets/minimums/freshness/recovery gates, or grant live authority.`

### Hermes Design Decision

The PR-triggered unit suite completed with 8,549 passed, 16 skipped, 28 deselected, and two failures. One failure reported `registry_load_failed:FileNotFoundError:MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH` while checking local option ownership after a global-map replacement. The other showed a blocked launch plan claiming 51 production tokens, which overlaps the separately declared 51-token observation registry. These indicate the production builder and its test boundary are not stable under the repository's import-time depth compatibility hooks.

GSD must preserve the public `build_subscription_tokens` behavior for ordinary feed subscription callers, while adding a dedicated production-only builder over the same internal implementation. The launch orchestrator must use that dedicated builder, then pass the independently loaded observation registry to `build_launch_plan`. The observation-registry lookup must be a canonical dependency boundary that tests can replace without relying on package-attribute import behavior. If production resolution fails, it must produce no claimed production IDs and retain the existing blocked verdict. Do not treat the captured 51 IDs as proof of ownership, fold observation tokens into production rows, or conceal the failure by loosening the identity validator.
