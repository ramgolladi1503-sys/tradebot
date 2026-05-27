# EDGE-89 — Strategy Promotion Gate

## Scope

EDGE-89 adds read-only strategy promotion gate evidence derived from EDGE-88 strategy lifecycle states.

This PR does **not** promote strategies, mutate lifecycle state, execute trades, route orders, call brokers, wire runtime behavior, or change dashboards.

## Inputs

The gate accepts the EDGE-88 lifecycle report payload with:

- `status == STRATEGY_LIFECYCLE_REDUCED`
- `read_only == true`
- `append == false`
- `states` as a list

Invalid lifecycle reports fail closed with `STRATEGY_PROMOTION_GATE_BLOCKED`.

## Promotion candidate criteria

A strategy family becomes a promotion candidate only when all criteria pass:

- lifecycle state is `ACTIVE_ELIGIBLE`
- lifecycle evidence says `eligible_for_promotion == true`
- lifecycle evidence says `requires_review == false`
- sample is valid and closed trades meet `promotion_min_closed_trades`
- net expectancy per trade is positive
- net win rate meets `promotion_min_win_rate`

Passing the gate only sets read-only evidence:

- `decision == PROMOTION_CANDIDATE`
- `promotion_ready == true`
- `promotion_applied == false`
- `lifecycle_state_mutated == false`

## Fail-closed outcomes

The gate blocks or review-flags promotion evidence for:

- invalid lifecycle report
- no lifecycle states
- invalid promotion policy
- non-active lifecycle state
- not eligible for promotion
- review required
- low sample
- non-positive expectancy
- low win rate

## Safety contract

Every report, policy, and decision payload carries:

- `read_only == true`
- `append == false`
- `is_order_action == false`
- `broker_api_called == false`
- `live_order_action == false`
- `broker_order_action == false`

This is evidence-only governance. PR #307 owns suspension and retirement rules. Runtime wiring, dashboard exposure, and live execution remain out of scope.

## Tests

Covered by `tests/test_edge_89_strategy_promotion_gate.py`:

- clean active-eligible family becomes a promotion candidate
- watchlist/review-required family requires review and does not promote
- low sample blocks promotion
- negative expectancy blocks promotion
- low win rate blocks promotion
- invalid lifecycle report blocks before evaluation
- empty lifecycle states block safely
- invalid policy blocks safely
- payloads remain JSON-serializable and non-action
