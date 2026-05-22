# EDGE-34 — Execution-First Scoring Reweight

mode: PAPER
candidate_id: EDGE-34
source: docs/agent_reviews/EDGE-34-execution-first-scoring-reweight.md
timestamp: 2026-05-22T11:45:00+05:30
decision: make execution quality dominate final ranking for executable candidates
reason: high signal score must not hide weak tradability, stale data, missing liquidity, or spread uncertainty
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Market-state note

This PR does not claim live market validation. It adds deterministic scoring behavior only. Runtime proof remains scoped to later EDGE-36/EDGE-37 work.

## Agent Work Contract

### Scope

Implement an execution-first scoring adjustment so executable candidates with weak execution quality are capped or penalized even when signal quality is high.

### Files changed

- `core/execution_first_scoring.py`
- `core/__init__.py`
- `tests/test_execution_first_scoring.py`
- `docs/agent_reviews/EDGE-34-execution-first-scoring-reweight.md`

### Out of scope

- No strategy changes.
- No broker/live order placement changes.
- No feed recovery rewrite.
- No dashboard changes.
- No ML/ranker changes.
- No auto-threshold tuning.

## Grill Me Review

### Hard questions

1. Can high signal override bad execution?
   - No. Weak execution score caps executable candidates.

2. Can stale quote, missing liquidity, spread uncertainty, or low data confidence silently survive scoring?
   - No. They apply explicit execution-first penalties.

3. Are non-executable/advisory rows reweighted?
   - No. The adjustment applies only to executable candidate class.

4. Does this prove profitability?
   - No. It prevents fake high scores from weak tradability; it does not prove strategy edge.

## Hermes Review

### Broker boundary

- No broker APIs are called.
- No order placement, modification, cancellation, or live adapter behavior changed.
- The scoring adjustment is deterministic and side-effect free except for installing the wrapper at package import.

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
- imported `compute_final_score` uses execution-first wrapper

### Regression risk

The main risk is import-order sensitivity. The integration test imports `core.trade_scoring.compute_final_score` normally and proves the wrapper is active.

## GSD Review

### What this improves

This PR prevents false ranking confidence where signal score masks weak execution quality.

### What this does not improve

- It does not improve strategy logic.
- It does not prove live fill quality.
- It does not fix feed recovery.
- It does not guarantee profitability.

## Scope Guard

The implementation is limited to score adjustment and tests. No strategy, broker, dashboard, feed, or threshold-learning behavior is changed.

## Approval + Evidence

### Local commands to run

```bash
pytest tests/test_execution_first_scoring.py -q
pytest tests/test_opportunity_engine.py tests/test_trade_scoring.py -q
```

## Acceptance Proof

Acceptance requires:

- High-signal weak-execution executable candidates are capped.
- Execution-not-ok executable candidates are capped.
- Non-executable/advisory candidates are not reweighted by this helper.
- Imported `compute_final_score` path is covered.

## Runtime Proof Required After Merge

Later PRs must prove scoring impact using runtime/replay evidence:

- EDGE-37: executable trade quality report
- EDGE-39: paper outcome journal
- EDGE-40: strategy expectancy review gate

## What This PR Does Not Prove

This PR does not prove live feed health, broker readiness, strategy expectancy, profitability, or live fill quality.

## Human Approval

Human approval required before merge: verify CI is green and confirm ranking changes are intended because weak execution should reduce/cap high-signal candidates.
