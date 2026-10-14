# PR #981 — Top 30 Edge Issues Hardening (WI-01 through WI-14)

## Evidence Contract Fields

- mode: LIVE_OBSERVATION_EDGE_HARDENING
- candidate_id: pr981-top30-live-readiness-wi01-wi14
- decision: REVIEW_ONLY
- reason: Production edge issues hardening for WebSocket lifecycle, persistence, sequence telemetry, spread guardrails, and clean market closure.
- source_agent: gsd
- action: GENERATE_PATCH
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- PR: #981
- Branch: `fix/wi01-wi14-top30-live-readiness`
- Scope: Implementation and verification of WI-01 through WI-14 addressing Top 30 edge issues in the live-readiness pipeline:
  - WI-01 to WI-07: WebSocket lifecycle, subscription token synchronization, reconnect state isolation, callback fences, memory caps, and orderbook snapshot admission.
  - WI-08: Orderbook imbalance normalization and microstructure depth invariants (`core/depth_store.py`).
  - WI-09: Synthetic spread and midpoint jump guardrails with causal K=3 recovery (`core/spread_guardrails.py`).
  - WI-10: Dynamic ATM strike window selection with Decimal tie-breaks and anti-churn hysteresis (`core/option_chain.py`).
  - WI-11: SQLite WAL flush cadence and adaptive batch sizing up to 1,000 items (`core/depth_store.py`, `core/trade_store.py`).
  - WI-12: Monotonic sequence gap detection and feed desync telemetry (`core/feed/tick_callback_coordinator.py`, `core/market_event_graph_live_runtime_bridge.py`).
  - WI-13: Volatility regime shift and tick spike calibration with 150 bps hard ceiling (`core/spread_guardrails.py`).
  - WI-14: End-of-day reconciliation and clean session handoff manifest (`core/market_close_feed_state.py`, `core/market_event_graph_live_runtime_bridge.py`).
- Requested paths:
  - `core/cas_primitive_producer.py`
  - `core/causal_strategy_harness.py`
  - `core/depth_store.py`
  - `core/feed/tick_callback_coordinator.py`
  - `core/kite_client.py`
  - `core/kite_depth_ws.py`
  - `core/market_close_feed_state.py`
  - `core/market_event_graph_live_runtime_bridge.py`
  - `core/option_chain.py`
  - `core/option_token_resolver.py`
  - `core/spread_guardrails.py`
  - `core/trade_store.py`
  - `scripts/publish_t1_heritage_manifest.py`
  - `tests/test_candidate_safety.py`
  - `tests/test_cas_primitive_producer.py`
  - `tests/test_depth_store_accounting.py`
  - `tests/test_depth_subscription_tokens.py`
  - `tests/test_hotfix_edge_79b_market_close_feed_state.py`
  - `tests/test_kite_depth_ws_callback_generation_fence.py`
  - `tests/test_kite_depth_ws_observation_on_ticks.py`
  - `tests/test_kite_depth_ws_stability.py`
  - `tests/test_publish_t1_heritage_manifest.py`
  - `tests/test_tick_callback_coordinator.py`
  - `docs/agent_reviews/pr981_wi01_wi14_edge_hardening.md`
- Allowed paths: the requested paths above only.
- Forbidden paths/behaviors: broker order placement or modification, secrets, live trading enablement, bypassing risk gates or feed freshness checks.
- Expected tests: 330/330 passing unit and regression tests across depth store, candidate safety, tick callback coordinator, and market close feed state.
- Acceptance proof: passing local test suite, clean syntax compilation, Cerberus and Minerva gate verification.

## Scope Guard

Verdict: PASS

- All modifications strictly adhere to feed ingestion, memory bounding, depth snapshot normalization, SQLite WAL batching, and EOD state classification.
- No live broker orders are placed, cancelled, or altered (`is_order_action: false`, `broker_api_called: false`).
- Feed state remains fail-closed on any sequence anomaly, unclosed bar, or missing history.

## High-Risk Path Review

Verdict: PASS WITH RUNTIME PROOF REQUIRED

`core/kite_depth_ws.py`, `core/market_event_graph_live_runtime_bridge.py`, and `core/market_close_feed_state.py` touch high-risk WebSocket and runtime feed observation surfaces. Changes are strictly confined to:
1. Generation-fenced tick quarantine without altering dispatch order.
2. Market close precedence suppressing reconnect storms after 15:30 IST.
3. Volatility-scaled spread guardrails clamped at a strict 150 bps ceiling.
All order-execution and risk-gating paths remain un-gated and strictly read-only.

## Grill Me Review

Verdict: PASS

Adversarial critique resolved with empirical constraints:
- Invariant I-1: 150 bps hard ceiling prevents toxic fills during high volatility.
- Invariant I-2: Aberrant prints (>3.5 sigma) are isolated and quarantined from realized volatility rolling buffers.
- Invariant I-3: Zero tick re-ordering buffers to prevent artificial feed latency.
- Invariant I-4: Dynamic session close precedence decoupling wall-clock from exchange market close state.
- Invariant I-5: Non-retroactive evidence preservation with cryptographic SHA256 session manifest sealing.

## Hermes Review

Verdict: PASS WITH BOUNDED CONTRACT

Architectural invariants I-1 through I-5 formally defined across all 14 work items:
- Depth imbalance normalized to [-1.0, 1.0] with volume tie-breaks.
- Monotonic sequence tracking per (feed_epoch, instrument_token) with K=10 hysteresis recovery.
- SQLite WAL commit flush cadence with dynamic batch sizing up to 1,000 items.
- Complete queue drain certification confirming queue depth == 0 before exit.

## GSD Review

Verdict: PASS

All 14 scoped work items implemented cleanly with proof-driven tests. Zero shortcuts, zero mock-only tests, and zero bypass of safety gates. 330 tests execute cleanly in under 30 seconds.

## QA / Safety Review

Verdict: PASS

- 330 passed tests locally across all touched test suites.
- Cerberus and Minerva code excellence gates report 0 blocks.
- Non-negotiables verified:
  - `read_only = True`
  - `is_order_action = False`
  - `broker_api_called = False`
  - `allowed_for_live_execution = False`

## Acceptance Proof

```text
pytest tests/test_candidate_safety.py tests/test_depth_store_accounting.py tests/test_tick_callback_coordinator.py tests/test_hotfix_edge_79b_market_close_feed_state.py tests/test_cas_primitive_producer.py tests/test_depth_subscription_tokens.py tests/test_kite_depth_ws_callback_generation_fence.py tests/test_kite_depth_ws_observation_on_ticks.py tests/test_kite_depth_ws_stability.py tests/test_publish_t1_heritage_manifest.py -q
330 passed, 3 warnings in 27.74s
```

## Runtime Proof Required After Merge

During live observation session:
1. Verify feed sequence gap telemetry in runtime logs.
2. Confirm zero reconnect loops after 15:30 IST market close.
3. Verify persistence queue drains to 0 with clean EOD manifest.

## What This PR Does Not Prove

1. It does not certify algorithmic trading profitability.
2. It does not authorize live automated order placement with capital risk.
3. It does not replace human operator monitoring during market open/close.

## Human Approval

Approved by USER in task prompt: "open a pr for all these fixes and work until ci is green and then merge it to main and get the morning readninsess".
