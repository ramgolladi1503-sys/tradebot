# EDGE-89 Strategy Promotion Gate Agent Review

mode: REVIEW
candidate_id: edge_89_strategy_promotion_gate
decision: review_ready
reason: strategy_promotion_gate_tests_docs
timestamp: 2026-05-27T16:55:00Z
source: edge_89_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers EDGE-89 only.

The PR adds read-only promotion gate evidence from EDGE-88 lifecycle states. It must not promote strategies, mutate lifecycle state, suspend, retire, execute, wire runtime behavior, change dashboards, alter ranking/scoring, or call broker APIs.

## Scope Guard

Allowed:

- Add a pure promotion-gate evidence reducer.
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

Question: Can an active-eligible lifecycle state automatically promote a strategy?

Answer: No. The gate can only emit `PROMOTION_CANDIDATE` evidence. It explicitly keeps `promotion_applied=false` and `lifecycle_state_mutated=false`.

Question: Can a watchlist or review-required family become promotion ready?

Answer: No. Review-required evidence is routed to `PROMOTION_REVIEW_REQUIRED`, not `PROMOTION_CANDIDATE`.

Question: Can weak sample, negative expectancy, or low win rate pass the gate?

Answer: No. Those cases are blocked with deterministic reason codes and `promotion_ready=false`.

## Hermes Review

The public contract is intentionally narrow:

- `build_strategy_promotion_gate_report(...)`

Payloads include schema version, source, status, reason codes, policy, promotion counts, decisions, and non-action markers.

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

- clean active-eligible family to `PROMOTION_CANDIDATE`
- watchlist/review-required family to `PROMOTION_REVIEW_REQUIRED`
- low-sample evidence blocking
- negative-expectancy evidence blocking
- low-win-rate evidence blocking
- invalid lifecycle report blocking
- empty lifecycle-state blocking
- invalid policy blocking
- JSON serialization and non-action payload markers

## Acceptance Proof

Run:

```bash
pytest tests/test_edge_89_strategy_promotion_gate.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire promotion evidence into runtime only if explicitly scoped. That later PR must prove:

- read-only output remains read-only
- broker/order markers remain false
- promotion markers remain explicit
- no lifecycle mutation occurs without a separately scoped gate

## What This PR Does Not Prove

This PR does not prove strategy profitability, live order safety, actual promotion correctness, suspension correctness, retirement correctness, ranking quality, or execution quality. It only proves that lifecycle evidence can be deterministically mapped into read-only promotion gate evidence.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with `EDGE-90 — Strategy Suspension and Retirement Rules` only from the latest merged main commit.


## High-Risk Path Review

N/A
