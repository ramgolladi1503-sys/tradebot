mode: REVIEW
candidate_id: EDGE-10-BUY-SELL-DIRECTION-OUTCOME-SUPPORT
decision: add_buy_sell_direction_outcome_support
reason: Extend candidate outcome truth to support long and short direction math for research-only outcome tracking without enabling live selling or broker execution.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-10-buy-sell-direction-outcome-support.md

# Agent Work Contract

## Scope Guard
- This PR only extends research/outcome truth for directional math.
- No broker, order, strategy, UI, websocket, feed lifecycle, or live-execution changes are allowed.
- The contract must remain read-only and fail closed.

## Grill Me Review
- Short-style math must be explicitly validated and not inferred from live order behavior.
- BUY_PUT must stay long-like unless the row explicitly supplies an underlying direction override.
- Unsupported directions and invalid short risk models must fail closed.

## Hermes Review
- The new normalizer maps directional labels into long-style or short-style outcome math.
- BUY/LONG remain long-style.
- SELL/SHORT/SELL_CALL/SELL_PUT remain short-style unless an explicit underlying override says otherwise.

## GSD Review
- Files touched are limited to the outcome-truth helper, focused directional tests, and this review doc.
- The candidate outcome tracker keeps consuming the same contract.
- No execution path is enabled by this PR.

## QA / Safety Review
- Read-only proof only.
- `is_order_action: false`
- `broker_api_called: false`
- `read_only: true`
- `append: false`
- No live orders, no broker calls, no runtime mutation beyond research math.

## Acceptance Proof
- Long target/stop math behaves as before.
- Short target below entry hits target.
- Short stop above entry hits stop.
- Short timeout gross R is computed correctly.
- Invalid short risk models fail closed.
- Unsupported directions fail closed.
- No broker/order behavior changes.

## Runtime Proof Required After Merge
- Confirm `normalize_outcome_direction()` is exported and used by the outcome truth builder.
- Confirm directional outcomes still serialize with the same safety flags.
- Confirm the tracker and expectancy pipeline continue to consume outcome truth normally.

## What This PR Does Not Prove
- It does not prove live short-selling readiness.
- It does not enable option selling.
- It does not change strategy or ranking behavior.

## Human Approval
- This contract is conservative by design.
- Any future attempt to use this math for live execution requires a separate approved PR.
