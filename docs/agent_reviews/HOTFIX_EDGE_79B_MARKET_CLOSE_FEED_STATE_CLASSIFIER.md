# HOTFIX/EDGE-79B Market Close Feed State Classifier Agent Review

mode: REVIEW
candidate_id: hotfix_edge_79b_market_close_feed_state_classifier
decision: review_ready
reason: market_close_feed_state_contract_tests_docs
timestamp: 2026-05-26T13:35:00Z
source: hotfix_edge79b_market_close_feed_state_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

HOTFIX/EDGE-79B adds a pure market-close feed state classifier before EDGE-80.

The output is intended to become input evidence for NoTradeOracle so it can distinguish websocket disconnects from stale LTP, option-feed staleness, close-window slowdown, cycle latency, and market-closed states.

## Work contract

This PR covers diagnostics only.

It does not reconnect feeds, resubscribe tokens, wire runtime, change dashboard, rank candidates, score edge, or add strategy behavior.

## Scope guard

- Websocket disconnected is a distinct state.
- LTP stale while websocket remains connected is not misclassified as websocket disconnected.
- Option feed stale is distinct from underlying LTP stale.
- Close-window slowdown has an explicit state.
- Cycle latency stale has an explicit state.
- Market closed has highest priority.
- Read-only and no-append evidence stays explicit.

## High-risk path review

The high-risk path is a live run near close where stale ticks are misdiagnosed as websocket failure.

Controls:

- `ws_connected=True` plus stale LTP produces `LTP_STALE` or `CLOSE_WINDOW_TICK_SLOWDOWN`.
- `ws_connected=False` produces `WEBSOCKET_DISCONNECTED`.
- Market closed is classified before stale data states.
- Cycle latency stale is classified before tick-age staleness.
- Empty payload fails as unknown, not healthy.

## QA / safety review

Focused tests cover:

- websocket disconnected
- connected websocket with stale LTP
- close-window tick slowdown
- option feed stale
- cycle latency stale
- market closed precedence
- healthy feed state
- empty payload unknown state

## Runtime Proof Required After Merge

After merge, runtime proof is still required before this classifier is connected to live review or NoTradeOracle flow.

EDGE-80 should consume this as evidence, not replace existing feed health truth.

## What This PR Does Not Prove

This PR does not prove NoTradeOracle behavior, live readiness, live profitability, feed recovery, replay proof, or final executable quality.

Those belong to later roadmap items.

## Acceptance proof

Command:

`PYTHONPATH=. python -m pytest tests/test_hotfix_edge_79b_market_close_feed_state.py`

Expected result:

- focused HOTFIX/EDGE-79B tests pass
- websocket disconnect is distinct from stale LTP
- close-window slowdown is explicit
- no runtime or dashboard change
