# EDGE-01 — Trading Edge Baseline Audit Report

## Agent Work Contract

### Scope
Add a read-only baseline audit report for trading-edge measurement.

The report answers, from the paper outcome journal only:

- strategy family
- regime
- direction
- score bucket
- sample count
- win rate
- average R
- median R
- max drawdown
- slippage-adjusted P&L

### Explicit non-scope

- No strategy changes
- No new strategy families
- No scoring changes
- No ranking changes
- No dashboard changes
- No broker calls
- No live execution behavior
- No paper execution behavior mutation

## Grill Me Review

### Hard question
Does this PR prove profitability?

### Answer
No. It only creates the measurement layer required before profitability claims are allowed.

### Hard question
Can this create fake confidence?

### Answer
It reduces fake confidence by exposing whether higher score buckets outperform lower buckets. If 0.75-1.00 does not beat 0.50-0.75 on average R, win rate, and slippage-adjusted P&L, the report marks scoring as not predictive on available data.

### Hard question
What can still be weak?

### Answer
If the paper outcome journal has missing/invalid terminal statuses, the report cannot fix that. It exposes invalid terminal status counts instead of hiding them.

## Hermes Review

### Safety boundaries

- Read-only source: paper outcome journal / family outcome records
- Output only: JSON audit report
- No order placement path touched
- No broker adapter touched
- No runtime candidate mutation
- No UI rendering path touched

### Data integrity

The report includes journal integrity fields:

- total records
- analyzed records
- valid terminal-status records
- invalid terminal-status records
- terminal-status counts
- allowed terminal statuses

## GSD Plan / Review

### Files changed

- `core/edge_baseline_audit.py`
- `scripts/edge_baseline_audit.py`
- `tests/test_edge_baseline_audit.py`
- `docs/agent_reviews/EDGE-01-baseline-audit.md`

### Test plan

Run:

```bash
python -m pytest tests/test_edge_baseline_audit.py
```

Optional usage:

```bash
python scripts/edge_baseline_audit.py
python scripts/edge_baseline_audit.py --strategy-family orb
python scripts/edge_baseline_audit.py --records-path runtime/analytics/family_outcomes.jsonl --out runtime/reports/edge_baseline_audit.json
```

## Scope Guard

This PR is intentionally boring. That is the point.

It does not try to improve trades. It measures whether the current trades have edge.

Blocked temptations:

- adding a new strategy
- changing thresholds
- improving dashboard presentation
- re-ranking candidates
- hiding invalid records
- relaxing lifecycle requirements

## Approval + Evidence

### Acceptance checks

- The audit groups by `strategy_family x regime x direction x score_bucket`.
- The audit reports sample count, win rate, average R, median R, max drawdown, and slippage-adjusted P&L.
- The audit validates whether score bucket `0.75-1.00` outperforms `0.50-0.75`.
- The audit can filter to one strategy family for focused validation.
- The audit exposes invalid terminal statuses.
- The audit is read-only.

### Status
Ready for PR review after CI/test execution.
