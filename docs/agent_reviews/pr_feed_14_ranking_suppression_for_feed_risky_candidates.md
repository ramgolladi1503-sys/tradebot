# Agent Review Evidence — PR-FEED-14 Ranking Suppression for Feed-Risky Candidates

## Agent Work Contract

### Goal

Add a ranking-layer safety guard so feed-risky scored candidates cannot remain executable or near-executable in ranking output.

### Files changed

- `core/candidate_ranking.py`
- `tests/test_candidate_ranking.py`
- `docs/PR_FEED_14_RANKING_SUPPRESSION_FOR_FEED_RISKY_CANDIDATES.md`
- `docs/agent_reviews/pr_feed_14_ranking_suppression_for_feed_risky_candidates.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: PR_FEED_14_RANKING_SUPPRESSION_FOR_FEED_RISKY_CANDIDATES
message_decision: READ_ONLY_RANKING_FEED_RISK_SUPPRESSION
decision: READ_ONLY_RANKING_FEED_RISK_SUPPRESSION
reason: Feed-risky scored candidates are suppressed inside ranking output and cannot remain executable ranked candidates.
timestamp: 2026-05-25T09:02:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr_feed_14_ranking_suppression_for_feed_risky_candidates.md

### Non-goals

- No websocket reconnect changes.
- No subscription changes.
- No token-resolution changes.
- No strategy changes.
- No dashboard UI changes.
- No broker calls.
- No order creation.

## Grill Me Review

### Pushback

The prior feed-hold gate blocks ranking only when the whole feed is unhealthy. It does not handle mixed-feed situations where one candidate carries feed-risk evidence while the global feed is otherwise usable.

### Required proof

- A high-score feed-risk executable candidate is not executable in ranking output.
- A feed-risk near-executable candidate is suppressed before advisory records.
- Source score records are not mutated.
- Advisory feed-risk records are not double-suppressed.

## Hermes Review

### Contract clarity

The ranking layer remains read-only. It emits suppression evidence only in `CandidateRankRecord`; it does not mutate `OpportunityScoreRecord`.

### Serialization

The report remains JSON serializable. Suppression metadata is emitted under ranking metadata.

## GSD Review

### Minimality

The PR modifies only ranking-layer behavior and tests. It does not add new pipeline stages, external calls, or live/runtime wiring.

### Determinism

The suppression is a pure function over existing score-record evidence: blockers, warnings, downgrade reasons, and safety flags.

## QA / Safety Review

Tests assert:

- Feed-risk executable candidates become `SUPPRESSED_BY_DOWNGRADE`.
- Feed-risk near-executable candidates become `SUPPRESSED_BY_DOWNGRADE`.
- Clean executable candidates outrank feed-risk executable candidates even when their score is lower.
- Upstream score records remain unchanged.
- Advisory records with feed-risk evidence remain advisory, avoiding double suppression.

## Scope Guard

Confirmed not touched:

- Feed lifecycle.
- Reconnect/resubscribe behavior.
- Token resolution.
- Strategy code.
- Dashboard UI.
- Broker/order execution paths.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_candidate_ranking.py
```

Expected:

- candidate ranking tests pass.
- ranking remains read-only and non-order-action.
- feed-risk suppression metadata is present.

## Runtime Proof Required After Merge

After merge, capture paper-mode ranking evidence proving:

- `feed_risk_suppressed_count` appears in ranking metadata.
- feed-risk candidates are not top executable ranked candidates.
- no broker or order behavior is triggered.

## What This PR Does Not Prove

- It does not prove feed recovery.
- It does not prove token freshness.
- It does not prove strategy profitability.
- It does not prove paper/live readiness.

## Human Approval

Proceed only if CI is green and the PR remains limited to ranking-layer feed-risk suppression.


## High-Risk Path Review

N/A
