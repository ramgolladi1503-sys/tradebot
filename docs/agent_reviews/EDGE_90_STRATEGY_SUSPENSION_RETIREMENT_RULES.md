# EDGE-90 Strategy Suspension and Retirement Rules Agent Review

mode: REVIEW
candidate_id: edge_90_strategy_suspension_retirement_rules
decision: review_ready
reason: strategy_suspension_retirement_rules_tests_docs
timestamp: 2026-05-27T17:10:00Z
source: edge_90_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers EDGE-90 only.

The PR adds read-only suspension and retirement rule evidence from EDGE-88 lifecycle states. It must not suspend strategies, retire strategies, mutate lifecycle state, promote strategies, execute, wire runtime behavior, change dashboards, alter ranking/scoring, or call broker APIs.

## Scope Guard

Allowed:

- Add a pure suspension/retirement rule evidence reducer.
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

Question: Can this PR actually suspend a strategy?

Answer: No. The rule can only emit `SUSPENSION_CANDIDATE` evidence. It explicitly keeps `suspension_applied=false` and `lifecycle_state_mutated=false`.

Question: Can this PR actually retire a strategy?

Answer: No. The rule can only emit `RETIREMENT_CANDIDATE` evidence. It explicitly keeps `retirement_applied=false` and `lifecycle_state_mutated=false`.

Question: Can active or watchlist families be incorrectly suspended or retired?

Answer: No. Lifecycle states that are not suspend/retire candidates return `NO_ACTION`.

Question: Can weak sample or non-negative expectancy pass the rules?

Answer: No. Those cases are routed to `REVIEW_REQUIRED`, not ready evidence.

## Hermes Review

The public contract is intentionally narrow:

- `build_strategy_suspension_retirement_report(...)`

Payloads include schema version, source, status, reason codes, policy, rule counts, decisions, and non-action markers.

## GSD Review

The implementation stays deterministic and local:

- No hidden global state.
- No network calls.
- No broker imports.
- No filesystem writes.
- No runtime side effects.
- Invalid lifecycle reports and invalid policy fail closed.

## QA / Safety Review

Focused test coverage includes:

- suspend candidate readiness
- retirement candidate readiness
- no-action behavior for active-eligible lifecycle states
- low suspension sample review requirement
- low retirement sample review requirement
- non-negative expectancy review requirement
- invalid lifecycle report blocking
- empty lifecycle states blocking
- invalid policy blocking
- JSON serialization and non-action payload markers

## Acceptance Proof

Run:

```bash
pytest tests/test_edge_90_strategy_suspension_retirement_rules.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire suspension/retirement evidence into runtime only if explicitly scoped. That later PR must prove:

- read-only output remains read-only
- broker/order markers remain false
- suspension and retirement applied markers remain false until explicitly scoped otherwise
- no lifecycle mutation occurs without a separately scoped state transition mechanism

## What This PR Does Not Prove

This PR does not prove strategy profitability, live order safety, actual suspension correctness, actual retirement correctness, ranking quality, or execution quality. It only proves that lifecycle evidence can be deterministically mapped into read-only suspension/retirement rule evidence.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with `PR-FEED-08 — Extract Pure Tick Utility Helpers` only from the latest merged main commit.
