# EDGE-34 — Execution-First Scoring Reweight

mode: PAPER
candidate_id: EDGE-34
source: docs/agent_reviews/EDGE-34-execution-first-scoring-reweight.md
timestamp: 2026-05-22T11:45:00+05:30
decision: add deterministic execution-first score adjustment primitive
reason: high signal score must not hide weak tradability, stale quote, liquidity gaps, spread uncertainty, or low data confidence when the helper is explicitly applied
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Market-state note

This PR does not claim live market validation. It adds deterministic scoring helper behavior only. Runtime proof remains scoped to later EDGE work.

## Agent Work Contract

### Scope

Implement a side-effect-free execution-first score adjustment helper so executable candidates with weak execution quality can be capped or penalized when the scoring path explicitly invokes it.

### Files changed

- `core/execution_first_scoring.py`
- `tests/test_execution_first_scoring.py`
- `docs/agent_reviews/EDGE-34-execution-first-scoring-reweight.md`

### Out of scope

- No strategy changes.
- No broker or live order behavior changes.
- No feed recovery rewrite.
- No dashboard changes.
- No ML/ranker changes.
- No import-time monkeypatching.
- No automatic threshold tuning.

## Grill Me Review

### Hard questions

1. Can high signal override bad execution inside this helper?
   - No. Weak execution score caps executable candidates.

2. Can stale quote, liquidity gaps, spread uncertainty, or low data confidence silently survive inside this helper?
   - No. They apply explicit execution-first penalties.

3. Are non-executable/advisory rows reweighted by this helper?
   - No. The adjustment applies only to executable candidate class.

4. Does this prove profitability?
   - No. It prevents fake high helper scores from weak tradability; it does not prove strategy edge.

## Hermes Review

### Broker boundary

- No broker APIs are called.
- No order placement, modification, cancellation, or live adapter behavior is changed.
- The scoring helper is deterministic and side-effect free.
- No package import side effects are introduced.

### Safety behavior

- Execution-not-ok caps final priority.
- Hard execution floor caps high-signal candidates.
- Soft execution floor applies penalty and cap.
- Stale quote, liquidity, spread, and data-confidence flags apply explicit penalties.

## QA / Safety Review

### Tests added

`tests/test_execution_first_scoring.py` covers:

- strong execution candidate remains unchanged
- high-signal weak-execution candidate is capped
- execution-not-ok candidate is capped
- stale/liquidity/spread/confidence penalties apply
- advisory candidate is not reweighted

### Regression risk

The helper is not wired by package import. That is intentional. Wiring it into runtime scoring must happen through an explicit scoped call site in a later PR, with regression tests for the selected scoring path.

## GSD Review

### What this improves

This PR adds a clean primitive that prevents false score confidence where signal score masks weak execution quality.

### What this does not improve

- It does not change runtime ranking yet.
- It does not improve strategy logic.
- It does not prove live fill quality.
- It does not fix feed recovery.
- It does not guarantee profitability.

## Scope Guard

The implementation is limited to a scoring helper, helper tests, and this evidence file. No strategy, broker, dashboard, feed, runtime import path, or threshold-learning behavior is changed.

## Approval + Evidence

### Local commands to run

```bash
pytest tests/test_execution_first_scoring.py -q
pytest tests/test_opportunity_engine.py tests/test_trade_scoring.py -q
```

## Acceptance Proof

Acceptance requires:

- High-signal weak-execution executable candidates are capped by the helper.
- Execution-not-ok executable candidates are capped by the helper.
- Non-executable/advisory candidates are not reweighted by the helper.
- Helper behavior is deterministic and side-effect free.

## Runtime Proof Required After Merge

Later PRs must prove scoring impact using explicit runtime or replay evidence:

- explicit final-score call-site wiring
- executable trade quality report
- paper outcome journal
- strategy expectancy review gate

## What This PR Does Not Prove

This PR does not prove live feed health, broker readiness, strategy expectancy, profitability, runtime ranking impact, or live fill quality.

## Human Approval

Human approval required before merge: verify CI is green and confirm this PR is accepted as a clean scoring primitive, not runtime scoring integration.