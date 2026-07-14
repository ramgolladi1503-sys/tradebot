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

## Grill Me Review

Question: Can this PR claim the socket is disconnected when the socket is still connected but LTP is stale?

Answer: No. Tests prove connected websocket plus stale LTP returns `LTP_STALE` outside the close window and `CLOSE_WINDOW_TICK_SLOWDOWN` inside the close window.

Question: Can this PR hide market close behind stale-feed evidence?

Answer: No. `MARKET_CLOSED` has highest priority and blocks before tick-age or cycle-latency states.

Question: Does this PR perform recovery behavior?

Answer: No. It only classifies supplied evidence and never reconnects, resubscribes, writes runtime state, ranks candidates, or changes strategy behavior.

## Hermes Review

The public contract is stable and explicit:

- `classify_market_close_feed_state(...)`
- `MarketCloseFeedStateDecision.to_payload()`
- canonical state constants including websocket, LTP, option feed, cycle latency, close-window slowdown, market closed, healthy, and unknown states

Payloads expose read-only, no-append, and non-action metadata so later consumers can use the classifier as evidence without mutating runtime state.

## GSD Review

The PR keeps the work narrow:

- one core classifier module
- one focused test file
- one implementation doc
- one agent-review evidence file
- TODO update that makes 79B active and keeps EDGE-80 blocked until 79B merges

No dashboard, runtime wiring, strategy changes, ranking, scoring, feed reconnect, or resubscribe behavior is included.

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

## Human Approval

Human review is required before any later PR wires this classifier into live runtime, dashboard, NoTradeOracle, or review queue behavior.

## Acceptance proof

Command:

`PYTHONPATH=. python -m pytest tests/test_hotfix_edge_79b_market_close_feed_state.py`

Expected result:

- focused HOTFIX/EDGE-79B tests pass
- websocket disconnect is distinct from stale LTP
- close-window slowdown is explicit
- no runtime or dashboard change


## Scope Guard

N/A

## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A
