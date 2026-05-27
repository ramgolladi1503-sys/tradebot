# EDGE-90 — Strategy Suspension and Retirement Rules

## Scope

EDGE-90 adds read-only strategy suspension and retirement rule evidence derived from EDGE-88 strategy lifecycle states.

This PR does **not** suspend strategies, retire strategies, mutate lifecycle state, promote strategies, execute trades, route orders, call brokers, wire runtime behavior, or change dashboards.

## Inputs

The rule evaluator accepts the EDGE-88 lifecycle report payload with:

- `status == STRATEGY_LIFECYCLE_REDUCED`
- `read_only == true`
- `append == false`
- `states` as a list

Invalid lifecycle reports fail closed with `STRATEGY_SUSPENSION_RETIREMENT_BLOCKED`.

## Suspension candidate criteria

A strategy family becomes a suspension candidate only when all criteria pass:

- lifecycle state is `SUSPEND_CANDIDATE`
- sample is valid
- closed trades meet `suspension_min_closed_trades`
- net expectancy per trade is negative

Passing this rule only sets read-only evidence:

```json
{
  "decision": "SUSPENSION_CANDIDATE",
  "suspension_ready": true,
  "suspension_applied": false,
  "lifecycle_state_mutated": false
}
```

## Retirement candidate criteria

A strategy family becomes a retirement candidate only when all criteria pass:

- lifecycle state is `RETIRED_CANDIDATE`
- sample is valid
- closed trades meet `retirement_min_closed_trades`
- net expectancy per trade is negative

Passing this rule only sets read-only evidence:

```json
{
  "decision": "RETIREMENT_CANDIDATE",
  "retirement_ready": true,
  "retirement_applied": false,
  "lifecycle_state_mutated": false
}
```

## Fail-closed and review-required outcomes

The rule evaluator blocks or review-flags evidence for:

- invalid lifecycle report
- no lifecycle states
- invalid policy
- low suspension sample
- low retirement sample
- non-negative expectancy

Lifecycle states that are not suspend/retire candidates return `NO_ACTION`.

## Safety contract

Every report, policy, and decision payload includes explicit non-action markers:

```json
{
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "live_order_action": false,
  "broker_order_action": false
}
```

This is evidence-only governance. Runtime wiring, dashboard exposure, actual suspension/retirement state changes, and live execution remain out of scope.

## Tests

Covered by `tests/test_edge_90_strategy_suspension_retirement_rules.py`:

- suspension candidate readiness
- retirement candidate readiness
- no-action behavior for active-eligible lifecycle states
- low suspension sample review requirement
- low retirement sample review requirement
- non-negative expectancy review requirement
- invalid lifecycle report blocking
- empty lifecycle states blocking
- invalid policy blocking
- payloads remain JSON-serializable and non-action
