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
