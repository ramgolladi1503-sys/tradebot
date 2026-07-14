# EDGE-36 — Feed Staleness Recovery Evidence

mode: PAPER
candidate_id: EDGE-36
source: docs/agent_reviews/EDGE-36-feed-recovery-evidence.md
timestamp: 2026-05-22T13:35:00+05:30
decision: add deterministic evidence contract for stale-feed recovery proof
reason: stale-feed incidents need proof of detection, recovery attempt, recovery result, and fail-closed behavior before execution confidence is trusted
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Market-state note

This PR does not claim live market validation. It adds a deterministic evidence evaluator for runtime snapshots or event payloads. It does not reconnect feeds or call broker APIs.

## Agent Work Contract

### Scope

Implement a read-only feed recovery evidence contract that validates whether a stale-feed incident proves:

- stale-feed detection
- recovery attempt
- recovery result
- fail-closed behavior
- no unsafe execution after failed recovery

### Files changed

- `core/feed_recovery_evidence.py`
- `tests/test_feed_recovery_evidence.py`
- `docs/agent_reviews/EDGE-36-feed-recovery-evidence.md`

### Out of scope

- No websocket rewrite.
- No reconnect implementation.
- No broker or live order behavior changes.
- No dashboard changes.
- No strategy changes.
- No auto-healing loop.

## Grill Me Review

### Hard questions

1. Does this actually reconnect the feed?
   - No. It validates evidence that a recovery attempt/result was recorded.

2. Can stale feed still allow execution?
   - Evidence fails if stale feed recovery fails and execution remains allowed.

3. Can a runtime claim recovery without a result?
   - No. Recovery attempt without result is blocked by the evidence contract.

4. Does this prove live feed stability?
   - No. It proves the evidence contract only. Live runtime proof remains a later step.

## Hermes Review

### Broker boundary

- Broker API flag remains false.
- Broker mutation behavior is unchanged.
- The evaluator is pure and deterministic.
- No reconnect, resubscribe, refresh, submit, modify, cancel, or exit operation is performed.

### Safety behavior

- Healthy feed requires no recovery.
- Stale feed without attempt blocks evidence.
- Stale feed with no recovery result blocks evidence.
- Failed recovery without fail-closed behavior blocks evidence.
- Successful recovery requires post-recovery freshness proof and execution still blocked during incident handling.

## QA / Safety Review

### Tests added

`tests/test_feed_recovery_evidence.py` covers:

- read-only safety assertion
- healthy feed needs no recovery
- stale feed without attempt blocks
- stale feed without recovery result blocks
- failed recovery with unsafe execution blocks
- successful recovery with fail-closed proof passes

### Regression risk

This PR is isolated. It does not change runtime feed behavior. The main risk is false confidence if runtime code never emits payloads consumed by this evaluator. That wiring is intentionally deferred.

## GSD Review

### What this improves

This PR converts stale-feed recovery from hand-waving into a deterministic evidence contract.

### What this does not improve

- It does not fix websocket reconnection.
- It does not alter live feed runtime.
- It does not prove broker readiness.
- It does not prove strategy expectancy.
- It does not guarantee profitability.

## Scope Guard

The implementation is limited to a pure evidence evaluator, tests, and this evidence file. No strategy, broker, dashboard, feed runtime, or threshold-learning behavior is changed.

## Approval + Evidence

### Local commands to run

```bash
pytest tests/test_feed_recovery_evidence.py -q
pytest tests/test_candidate_quote_freshness_contract.py tests/test_option_spread_truth_gate.py tests/test_strategy_signal_quality_contract.py -q
```

## Acceptance Proof

Acceptance requires:

- Healthy feed does not require recovery.
- Stale feed without recovery proof fails evidence.
- Failed recovery with unsafe execution fails evidence.
- Successful recovery with fail-closed proof passes evidence.
- No broker or order behavior changes.

## Runtime Proof Required After Merge

Later PRs must wire runtime/feed snapshots into this evaluator and persist evidence records.

## What This PR Does Not Prove

This PR does not prove live feed health, websocket recovery, broker readiness, strategy expectancy, profitability, runtime ranking impact, or live fill quality.

## Human Approval

Human approval required before merge: verify CI is green and confirm this PR is accepted as an evidence contract, not runtime reconnection implementation.

## High-Risk Path Review

N/A
