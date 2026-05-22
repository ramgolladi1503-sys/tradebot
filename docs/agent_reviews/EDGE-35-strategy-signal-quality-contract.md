# EDGE-35 — Strategy Signal Quality Contract

mode: PAPER
candidate_id: EDGE-35
source: docs/agent_reviews/EDGE-35-strategy-signal-quality-contract.md
timestamp: 2026-05-22T13:05:00+05:30
decision: require executable candidates to prove strategy signal quality before passing executable truth
reason: signal existence alone is not sufficient; weak, absent, rejected, or conflicting signals must not become executable trades
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Market-state note

This PR does not claim live market validation. It adds deterministic strategy signal validation using candidate fields and tests. Runtime proof remains scoped to later EDGE work.

## Agent Work Contract

### Scope

Implement a strategy signal quality contract that blocks execution-capable candidates when the strategy signal is absent, weak, explicitly rejected, directionless, or conflicting.

### Files changed

- `core/strategy_signal_quality.py`
- `core/executable_truth.py`
- `tests/test_strategy_signal_quality_contract.py`
- `docs/agent_reviews/EDGE-35-strategy-signal-quality-contract.md`

### Out of scope

- No strategy rewrite.
- No broker or live order behavior changes.
- No feed recovery rewrite.
- No dashboard changes.
- No ML/ranker changes.
- No automatic threshold tuning.

## Grill Me Review

### Hard questions

1. Can a row execute just because some strategy emitted it?
   - No. It must carry signal quality proof.

2. Can a weak signal pass because data/feed/spread is good?
   - No. Strategy signal quality is a separate executable truth requirement.

3. Can an explicit weak-signal or no-signal reject become executable?
   - No. Explicit reject markers block executable truth.

4. Does this prove strategy edge?
   - No. It prevents bad/no/conflicting signals from being executable; it does not prove expectancy.

## Hermes Review

### Broker boundary

- No broker APIs are called.
- No order placement, modification, cancellation, or live adapter behavior is changed.
- The signal classifier is pure and deterministic.

### Safety behavior

- Missing strategy family blocks strict executable candidates.
- Missing direction blocks strict executable candidates.
- Absent signal blocks strict executable candidates.
- Weak signal blocks strict executable candidates.
- Explicit reject markers block strict executable candidates.
- Conflicting direction/signal markers block strict executable candidates.

## QA / Safety Review

### Tests added

`tests/test_strategy_signal_quality_contract.py` covers:

- strong signal candidate passes
- live candidate without signal proof blocks
- weak signal blocks
- absent strategy family blocks
- absent direction blocks
- explicit weak-signal reject blocks
- conflicting signal blocks
- legacy offline fixture compatibility
- read-only safety assertion

### Regression risk

Existing unit fixtures may not carry strategy signal fields. The classifier is strict for LIVE and for candidates carrying explicit signal-contract payloads. Legacy offline fixtures without signal fields remain compatible.

## GSD Review

### What this improves

This PR prevents false executable confidence where a row exists but the strategy signal itself is weak, absent, rejected, or conflicted.

### What this does not improve

- It does not rewrite strategies.
- It does not prove expectancy.
- It does not prove live fill quality.
- It does not fix feed recovery.
- It does not guarantee profitability.

## Scope Guard

The implementation is limited to a pure signal-quality classifier, executable-truth integration, tests, and this evidence file. No strategy, broker, dashboard, feed, or threshold-learning behavior is changed.

## Approval + Evidence

### Local commands to run

```bash
pytest tests/test_strategy_signal_quality_contract.py -q
pytest tests/test_executable_truth_firebreak.py tests/test_opportunity_engine.py tests/test_decision_engine.py -q
```

## Acceptance Proof

Acceptance requires:

- Strong signal executable candidates pass.
- Absent/weak/rejected/conflicting signals block executable truth.
- Legacy offline fixtures without signal-contract fields remain compatible.
- Existing EDGE-31/32/33 behavior remains intact.

## Runtime Proof Required After Merge

Later PRs must prove signal quality impact using runtime or replay evidence:

- executable trade quality report
- paper outcome journal
- strategy expectancy review gate

## What This PR Does Not Prove

This PR does not prove live feed health, broker readiness, strategy expectancy, profitability, runtime ranking impact, or live fill quality.

## Human Approval

Human approval required before merge: verify CI is green and confirm weak/no/conflicting strategy signals should block executable truth.