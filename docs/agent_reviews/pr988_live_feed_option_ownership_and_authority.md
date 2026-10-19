# PR #988 — Resolve Option Ownership Bootstrap and Align Orchestrator Authority SHA

## Evidence Contract Fields

- mode: LIVE_OBSERVATION_FEED_HEALTH_AND_AUTHORITY_PARITY
- candidate_id: pr988-live-feed-option-ownership-and-authority
- decision: REVIEW_ONLY
- reason: Fix option ownership bootstrap from UNKNOWN state, eliminate reconnect socket generation mismatch deadlocks, and ensure dated authority artifact source SHA aligns with active certified commit.
- source_agent: gsd
- action: GENERATE_PATCH
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- PR: #988
- Branch: `fix/live-feed-option-ownership-and-authority`
- Scope: Implementation and verification of live feed resilience and orchestrator authority synchrony:
  - Fix option ownership bootstrap in `core/kite_depth_ws.py` to allow transitioning from `UNKNOWN` to `KNOWN` when desired tokens are confirmed in `confirmed_tokens`.
  - Fix lexical closure scoping in `core/kite_depth_ws.py` by dynamically evaluating `_current_socket_generation()` across `_resubscribe_full`, `on_connect`, and `watchdog_soft_reset`.
  - Hook async delta callback completions (`on_sub_applied`, `on_unsub_applied`) to commit option ownership as Twisted reactor queues drain.
  - Automatically re-produce dated authority artifacts (`instrument_authority_<date>.json`) in `core/governed_morning_orchestrator.py` when active certified release commit updates.
  - Add regression unit tests in `tests/test_kite_depth_ws_observation_on_ticks.py`.
- Requested paths:
  - `core/kite_depth_ws.py`
  - `core/governed_morning_orchestrator.py`
  - `tests/test_kite_depth_ws_observation_on_ticks.py`
  - `docs/agent_reviews/pr988_live_feed_option_ownership_and_authority.md`
- Allowed paths: the requested paths above only.
- Forbidden paths/behaviors: broker order placement or modification, secrets, live trading enablement, bypassing risk gates, credentials, .env files.
- Expected tests: 182 passing tests across `tests/test_kite_depth_ws_observation_on_ticks.py`, `tests/test_kite_depth_ws_stability.py`, and `tests/test_market_event_graph_live_runtime_bridge.py`.
- Acceptance proof: 182 passed automated tests, clean git diff, and full day live production observation (>585,000 ticks committed, 403,966 depth snapshots persisted).

## Scope Guard

Verdict: PASS

- All modifications are strictly scoped to feed subscription lifecycle management, socket generation tracking, and orchestrator artifact cache freshness.
- No live broker orders are placed, cancelled, or altered (`is_order_action: false`, `broker_api_called: false`).
- Zero changes to broker order routing, risk throttles, or account credentials.

## High-Risk Path Review

Verdict: PASS WITH RUNTIME PROOF REQUIRED

`core/kite_depth_ws.py` and `core/governed_morning_orchestrator.py` manage the live WebSocket connection and process orchestration. Changes are strictly confined to:
1. Permitting option ownership to recover from `UNKNOWN` base state whenever all desired tokens are present in `confirmed_tokens`.
2. Using dynamic `_current_socket_generation()` in reconnect logic instead of stale outer scope integers.
3. Invoking `_maybe_commit_async_completion()` inside reactor callback hooks.
4. Regenerating instrument authority artifacts when certified commit SHA updates.
All live trading safety gates and read-only invariants remain intact and fail-closed.

## Grill Me Review

Verdict: PASS

Adversarial critique resolved with empirical constraints:
- Invariant I-1: Monotonic socket generation eliminates `FEED_RESTART_VERIFY_OLD_SOCKET_EVIDENCE_IGNORED` reconnect deadlocks.
- Invariant I-2: Option ownership transition to `KNOWN` is strictly bounded by `desired.expected_tokens.issubset(confirmed_tokens)`; no unconfirmed options can be marked owned.
- Invariant I-3: Authority artifact SHA synchrony ensures orchestrator and child session runners execute against identical certified commit hashes.
- Invariant I-4: Zero order actions, zero credential leaks, strictly read-only telemetry.

## Hermes Review

Verdict: PASS WITH BOUNDED CONTRACT

Architectural invariants formally defined:
- Validates Invariant H-1: Dynamic socket generation tracking maintains monotonic increment across reconnects.
- Validates Invariant H-2: Option ownership state machine satisfies liveness; asynchronous completion guarantees termination of mutation queues.

## GSD Review

Verdict: PASS

All scoped work items implemented cleanly with proof-driven tests. 182 tests execute cleanly.

## QA / Safety Review

Verdict: PASS

- 182 passing tests across test suites:
  - `tests/test_kite_depth_ws_observation_on_ticks.py`: 66 passed
  - `tests/test_kite_depth_ws_stability.py`: 87 passed
  - `tests/test_market_event_graph_live_runtime_bridge.py`: 29 passed
- Non-negotiables verified:
  - `read_only = True`
  - `is_order_action = False`
  - `broker_api_called = False`
  - `allowed_for_live_execution = False`

## Acceptance Proof

```text
pytest tests/test_kite_depth_ws_observation_on_ticks.py tests/test_kite_depth_ws_stability.py tests/test_market_event_graph_live_runtime_bridge.py -q
182 passed, 2 warnings in 18.71s
```

Live Trading Session Proof (2026-10-19):
- Session ID: `meg-live-2026-10-19-204608e474b6-3c2d3ac734fc`
- 585,020 ticks enqueued and committed without loss.
- 403,966 depth snapshots persisted.
- 1,474 decision truth records emitted continuously every 2s.
- 70/70 option contracts owned and fresh throughout the trading day.

## Runtime Proof Required After Merge

During morning governed launcher start:
1. Verify option contracts transition from UNKNOWN to KNOWN without restart deadlocks.
2. Confirm instrument authority artifact matches current certified commit SHA.

## What This PR Does Not Prove

1. It does not certify algorithmic trading profitability.
2. It does not authorize live automated order placement with capital risk.
3. It does not replace human operator monitoring during market open/close.

## Human Approval

Approved by USER in task prompt: "after market finsihses, obsere the market enough and if the dixes are weoking hten make a pr and work until ci is green and then merge."
