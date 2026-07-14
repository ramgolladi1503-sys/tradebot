# EDGE-88 Strategy Lifecycle States Agent Review

mode: REVIEW
candidate_id: edge_88_strategy_lifecycle_states
decision: review_ready
reason: strategy_lifecycle_states_tests_docs
timestamp: 2026-05-27T16:02:00Z
source: edge_88_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers EDGE-88 only.

The PR adds read-only lifecycle state modeling from EDGE-87 strategy-family recommendations. It must not promote, suspend, retire, execute, wire runtime behavior, change dashboards, alter ranking/scoring, or call broker APIs.

## Scope Guard

Allowed:

- Add a pure reducer for lifecycle state evidence.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for the completed PR.

Not allowed:

- Broker calls.
- Order actions.
- Runtime wiring.
- Dashboard/UI work.
- Promotion implementation.
- Suspension implementation.
- Retirement implementation.
- Strategy lifecycle mutation.
- Ranking/scoring/execution changes.

## Grill Me Review

Question: Can a weak/unknown recommendation become active eligible?

Answer: No. Unknown recommendations are routed to `WATCHLIST`, and low-sample evidence is routed to `CANDIDATE`, not `ACTIVE_ELIGIBLE`.

Question: Does `KILL` immediately retire or suspend a strategy?

Answer: No. `KILL` only derives `SUSPEND_CANDIDATE` or `RETIRED_CANDIDATE` evidence. The output explicitly keeps `suspension_applied=false` and `retirement_applied=false`.

Question: Does `KEEP` immediately promote a strategy?

Answer: No. `KEEP` derives `ACTIVE_ELIGIBLE` evidence and `eligible_for_promotion=true`, but `promotion_applied=false`. Promotion belongs to EDGE-89.

## Hermes Review

The public contract is intentionally narrow:

- `build_strategy_lifecycle_report(...)`

Payloads include schema version, source, status, reason codes, policy, lifecycle counts, lifecycle states, and non-action markers.

## GSD Review

The implementation stays deterministic and local:

- No hidden global state.
- No network calls.
- No broker imports.
- No filesystem writes.
- No runtime side effects.
- Invalid family reports and invalid policy fail closed.

## QA / Safety Review

Focused test coverage includes:

- `KEEP` to `ACTIVE_ELIGIBLE`
- `WATCH` to `WATCHLIST`
- low-sample evidence to `CANDIDATE`
- `KILL` below retire threshold to `SUSPEND_CANDIDATE`
- `KILL` at retire threshold to `RETIRED_CANDIDATE`
- unknown recommendation to `WATCHLIST`
- invalid family report blocking
- empty recommendation blocking
- invalid policy blocking
- JSON serialization and non-action payload markers

## Acceptance Proof

Run:

```bash
pytest tests/test_edge_88_strategy_lifecycle_states.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire lifecycle evidence into runtime only if explicitly scoped. That later PR must prove:

- read-only output remains read-only
- broker/order markers remain false
- promotion/suspension/retirement markers remain explicit
- no lifecycle mutation occurs without a separately scoped gate

## What This PR Does Not Prove

This PR does not prove strategy profitability, live order safety, promotion readiness, suspension correctness, retirement correctness, ranking quality, or execution quality. It only proves that family evidence can be deterministically mapped into read-only lifecycle state evidence.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with `EDGE-89 — Strategy Promotion Gate` only from the latest merged main commit.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
