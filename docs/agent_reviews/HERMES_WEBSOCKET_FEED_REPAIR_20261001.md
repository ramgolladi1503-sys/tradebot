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
