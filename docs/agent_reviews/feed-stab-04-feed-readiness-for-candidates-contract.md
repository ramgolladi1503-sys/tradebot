# Agent Review Evidence — FEED-STAB-04 Feed Readiness for Candidates Contract

## Agent Work Contract

### Goal

Add a pure feed-readiness-for-candidates contract that consumes feed supervisor evidence and deterministically reports whether candidate generation is allowed.

### Files changed

- `core/feed_readiness_for_candidates.py`
- `tests/test_feed_readiness_for_candidates_contract.py`
- `docs/agent_reviews/feed-stab-04-feed-readiness-for-candidates-contract.md`

### Evidence Contract Fields

mode: REVIEW
candidate_id: FEED_STAB_04_FEED_READINESS_FOR_CANDIDATES_CONTRACT
decision: INTRODUCE_FEED_READINESS_FOR_CANDIDATES_CONTRACT
reason: The new contract is read-only, fail-closed, and only reports whether feed evidence is ready for candidate generation.
timestamp: 2026-06-09T00:00:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/feed-stab-04-feed-readiness-for-candidates-contract.md

### Scope Guard

- No broker calls.
- No order creation or modification.
- No strategy, ranking, or scoring changes.
- No dashboard/UI changes.
- No credentials or auth wiring changes.

## Grill Me Review

### Pushback

This contract could become fake readiness if it ignores feed warmup, recovery, or terminal blocker evidence. The implementation stays conservative by only marking readiness when the feed supervisor is already `CANDIDATE_READY` and all warmup evidence is complete.

## Hermes Review

### Contract clarity

The contract is a deterministic read-only classifier for candidate generation eligibility. It does not perform runtime wiring or mutate feed state.

### Safety boundary

The contract emits `is_order_action=false`, `broker_api_called=false`, and `read_only=true`. It does not call brokers, select strategies, or allocate capital.

## GSD Review

### Minimality

The change is scoped to the new contract module and focused tests only.

### Determinism

Classification depends solely on the supplied snapshot payload.

## QA / Safety Review

Tests assert:

- warming-up stays warming-up until clean cycles complete;
- candidate-ready only becomes ready when the feed supervisor is already candidate-ready;
- auth-required and restart-required block immediately;
- serialization remains read-only and non-order-action.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_feed_readiness_for_candidates_contract.py -q
PYTHONPATH=. python -m pytest tests/test_feed_supervisor_state_machine.py tests/test_feed_reconnect_quarantine.py -q
git diff --check
python scripts/validate_agent_review_evidence.py --base-ref origin/main
git diff --name-only origin/main...HEAD > /tmp/feed_stab_04_changed_paths.txt
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/feed_stab_04_changed_paths.txt
```

## Runtime Proof Required After Merge

Confirm the runtime feed supervisor continues to supply the warmup and blocker fields this contract consumes.

## What This PR Does Not Prove

- Feed quality outside the contract input.
- Strategy quality.
- Ranking/scoring quality.
- Broker/order safety beyond the read-only contract.
- UI or dashboard behavior.

## Human Approval

Proceed only if CI is green and the PR remains limited to the read-only feed-readiness-for-candidates contract.
