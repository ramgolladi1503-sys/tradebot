# EDGE-40 - Quote Timestamp/Age Consistency Guard

mode: PAPER
candidate_id: EDGE-40
source: docs/agent_reviews/EDGE-40-quote-timestamp-age-consistency-guard.md
timestamp: 2026-05-22T21:49:00+05:30
decision: reject execution-capable candidates when reported quote age contradicts timestamp-derived quote age
reason: May 22 diagnostic evidence showed quote_age_sec could look fresh while quote_ts_epoch proved stale data
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

### Scope

Add canonical quote-age truth classification and wire it into candidate quote freshness so execution-capable candidates fail closed on timestamp/age contradiction.

### Files changed

- `core/quote_age_truth.py`
- `core/candidate_quote_freshness.py`
- `tests/test_quote_age_truth.py`
- `docs/EDGE_TODO.md`
- `docs/agent_reviews/EDGE-40-quote-timestamp-age-consistency-guard.md`

### Out of scope

- No fallback execution firewall. That is EDGE-41.
- No quote truth consolidation across every module. That is EDGE-42.
- No feed recovery wiring. That is EDGE-44.
- No strategy rewrite.
- No dashboard changes.

## Grill Me Review

### Hard questions

1. Does this fix all stale quote paths?
   - No. It fixes timestamp/age contradiction in the execution-capable candidate freshness gate.

2. Does this block advisory-only diagnostics?
   - No. Non-execution-capable rows remain diagnostics and do not fail just because they carry stale quote metadata.

3. Can a fresh-looking age hide an old timestamp now?
   - No. The effective age is the larger of reported age and timestamp-derived age, and contradiction beyond tolerance adds `quote_age_timestamp_mismatch`.

4. Does this add broker or feed calls?
   - No. It is pure classification logic.

5. Does this replace the future quote truth single-source module?
   - No. This is the guard needed now; EDGE-42 will centralize broader quote truth later.

## Hermes Review

### Boundary review

- `broker_api_called=false`
- `is_order_action=false`
- `live_order_action=false`
- `broker_order_action=false`
- No broker adapters imported.
- No execution engine changes.
- No strategy changes.
- No dashboard changes.

## GSD Review

### What this improves

- Adds `core/quote_age_truth.py` as a pure quote-age classifier.
- Calculates timestamp-derived age from quote timestamp and observation timestamp.
- Produces `quote_age_timestamp_mismatch` when reported age and timestamp age disagree beyond tolerance.
- Uses effective age in candidate freshness checks.
- Blocks execution-capable candidates when timestamp proves stale quote data.
- Preserves diagnostic/non-executable rows.
- Removes EDGE-40 from remaining TODO.

### What this does not improve

- Does not block all fallback sources.
- Does not fix price mismatch classification.
- Does not wire runtime feed recovery.
- Does not prove strategy profitability.

## Scope Guard

The production behavior change is intentionally limited to candidate quote freshness. The new helper is pure and testable.

## QA / Safety Review

### Tests added

- Timestamp-only age is used when reported age is missing.
- Fresh reported age with stale timestamp is blocked.
- Matching reported/timestamp age passes.
- Execution-capable candidate blocks on quote age mismatch.
- Timestamp-derived effective age triggers stale quote rejection.
- Non-execution candidate does not block on quote age mismatch.

### Commands to run locally

```bash
pytest tests/test_quote_age_truth.py -q
```

## Acceptance Proof

Acceptance requires:

- Focused tests pass.
- A candidate with reported `quote_age_sec=1` and stale `quote_ts_epoch` fails freshness.
- Effective age uses timestamp-derived age when it is larger.
- Non-execution diagnostics are not incorrectly blocked.
- No broker/order/feed runtime side effects are introduced.

## Runtime Proof Required After Merge

After merge, run EDGE-37 evidence replay and inspect future diagnostic rows for `quote_age_timestamp_mismatch` style failures when timestamp and reported age contradict each other.

Required runtime proof:

- No execution-capable candidate can pass if quote timestamp proves stale data.
- The May 22-style contradiction is classified as a hard freshness failure.

## What This PR Does Not Prove

This PR does not prove live trading readiness, strategy profitability, fallback firewall completeness, feed recovery success, dashboard correctness, or paper-trading expectancy.

It only proves quote timestamp/age contradiction fails closed for execution-capable candidate freshness.

## Human Approval

Human approval required before merge: confirm CI is green and focused tests pass locally or in CI.


## High-Risk Path Review

N/A
