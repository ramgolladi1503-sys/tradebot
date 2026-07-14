# Agent Review Evidence — FEED-STAB-06 Subscription Truth & Resubscribe Verification

## Agent Work Contract

### Goal

Add a pure subscription-truth contract that proves subscription completeness and resubscribe verification from runtime evidence only.

### Files changed

- `core/subscription_truth_contract.py`
- `tests/test_subscription_truth_contract.py`
- `docs/agent_reviews/feed-stab-06-subscription-truth-resubscribe-verification.md`

### Evidence Contract Fields

mode: REVIEW
candidate_id: FEED_STAB_06_SUBSCRIPTION_TRUTH_RESUBSCRIBE_VERIFICATION
decision: INTRODUCE_SUBSCRIPTION_TRUTH_CONTRACT
reason: The new contract is read-only, fail-closed, and only reports whether subscription evidence and resubscribe verification are complete.
timestamp: 2026-06-09T00:00:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/feed-stab-06-subscription-truth-resubscribe-verification.md

### Scope Guard

- No broker calls.
- No order creation or modification.
- No strategy, ranking, or scoring changes.
- No dashboard/UI changes.
- No credentials or auth wiring changes.
- No websocket reconnect implementation.

## Grill Me Review

### Pushback

This contract could become fake truth if it accepts subscription intent without verified completion. The implementation stays conservative by requiring actual subscribed counts, option coverage, and non-blocking evidence before marking truth complete.

## Hermes Review

### Contract clarity

The contract is a deterministic read-only classifier for subscription completeness and resubscribe verification. It does not mutate runtime state or trigger resubscribe behavior.

### Safety boundary

The contract emits `is_order_action=false`, `broker_api_called=false`, and `read_only=true`.

## GSD Review

### Minimality

The change is limited to a new pure contract module and focused tests.

### Determinism

Classification depends solely on supplied runtime evidence.

## QA / Safety Review

Tests assert:

- read-only and non-action serialization;
- missing option subscription counts block truth;
- failed resubscribe blocks truth;
- verified resubscribe with complete counts and coverage reports verified truth.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_subscription_truth_contract.py -q
PYTHONPATH=. python -m pytest tests/test_feed_readiness_for_candidates_contract.py tests/test_feed_supervisor_state_machine.py tests/test_feed_reconnect_quarantine.py -q
git diff --check
python scripts/validate_agent_review_evidence.py --base-ref origin/main
git diff --name-only origin/main...HEAD > /tmp/feed_stab_06_changed_paths.txt
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/feed_stab_06_changed_paths.txt
```

## Runtime Proof Required After Merge

Confirm the runtime payload that feeds this contract continues to expose intended and subscribed counts, verified and missing option symbols, and resubscribe status without relying on side effects.

## What This PR Does Not Prove

- Websocket reconnect implementation.
- Subscription mutation behavior.
- Strategy quality.
- Ranking/scoring quality.
- Broker/order safety beyond the read-only contract.
- UI or dashboard behavior.

## Human Approval

Proceed only if CI is green and the PR remains limited to the read-only subscription truth / resubscribe verification contract.


## High-Risk Path Review

N/A
