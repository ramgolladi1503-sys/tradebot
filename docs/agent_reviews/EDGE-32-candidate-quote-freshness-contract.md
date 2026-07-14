# EDGE-32 — Candidate Quote Freshness Contract

mode: PAPER
candidate_id: EDGE-32
source: docs/agent_reviews/EDGE-32-candidate-quote-freshness-contract.md
timestamp: 2026-05-22T09:58:00+05:30
decision: require per-candidate quote freshness proof before execution-capable candidates can pass truth validation
reason: broad feed health is not enough to prove a specific option candidate is executable
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Market-state note

This PR does not claim live market validation. It adds deterministic quote freshness enforcement using candidate fields and tests. Live stale-feed recovery evidence remains scoped to later EDGE-36/EDGE-37 work.

## Agent Work Contract

### Scope

Implement a candidate-level quote freshness contract that blocks execution-capable rows unless the row itself carries fresh option quote evidence.

Required candidate evidence fields:

- `ltp_age_sec`
- `bid_age_sec`
- `ask_age_sec`
- `quote_age_sec`
- `chain_snapshot_age_sec`
- `option_token` or `instrument_token`
- `last_option_tick_epoch`
- feed blocker field equals the allowed sentinel value

### Files changed

- `core/candidate_quote_freshness.py`
- `core/executable_truth.py`
- `tests/test_candidate_quote_freshness_contract.py`
- `docs/agent_reviews/EDGE-32-candidate-quote-freshness-contract.md`

### Out of scope

- No strategy changes.
- No broker/live order placement changes.
- No feed recovery rewrite.
- No dashboard changes.
- No ML/ranker changes.
- No auto-threshold tuning.

## Grill Me Review

### Hard questions

1. Can broad WebSocket/feed health make a candidate executable?
   - No. The contract ignores broad feed health and requires the candidate row to carry quote-age evidence.

2. Can an advisory/watchlist row be blocked just because it lacks quote-age fields?
   - No. The contract applies to execution-capable candidates only.

3. Can a candidate with fresh LTP but stale bid/ask pass?
   - No. `ltp_age_sec`, `bid_age_sec`, `ask_age_sec`, and `quote_age_sec` must all be within SLA.

4. Does this prove live feed recovery?
   - No. It only proves the deterministic candidate-level contract.

## Hermes Review

### Broker boundary

- No broker APIs are called.
- No order placement, modification, cancellation, or live adapter behavior changed.
- The contract is pure and deterministic.

### Safety behavior

- Absent option token blocks execution-capable rows.
- Absent last option tick epoch blocks execution-capable rows.
- Stale quote-age fields block execution-capable rows.
- Non-allowed feed blocker state blocks execution-capable rows.
- Stale chain snapshot blocks execution-capable rows.

## QA / Safety Review

### Tests added

`tests/test_candidate_quote_freshness_contract.py` covers:

- fresh executable candidate passes
- non-executable advisory rows are ignored by the freshness gate
- absent option token blocks
- absent last tick epoch blocks
- stale ltp/bid/ask/quote ages block
- feed blocker blocks
- stale chain snapshot blocks

### Regression risk

Existing tests may construct executable candidates without quote-age fields. If those tests are meant to represent real executable trades, they must add freshness proof. If they are advisory/test scaffolds, they must be marked non-executable.

## GSD Review

### What this improves

This PR prevents false executable confidence caused by broad feed-health assumptions. Every candidate must prove its own option quote freshness.

### What this does not improve

- It does not fix live feed staleness recovery.
- It does not improve strategy edge.
- It does not validate broker execution.
- It does not guarantee profitability.

## Scope Guard

The implementation is limited to a pure candidate quote freshness classifier and integration into the existing EDGE-31 executable truth firebreak.

## Approval + Evidence

### Local commands to run

```bash
pytest tests/test_candidate_quote_freshness_contract.py -q
pytest tests/test_executable_truth_firebreak.py tests/test_execution_quality.py tests/test_opportunity_engine.py -q
```

## Acceptance Proof

Acceptance requires:

- Fresh executable candidates pass.
- Absent candidate-level quote freshness proof blocks execution-capable candidates.
- Advisory/non-executable rows are not blocked only because freshness fields are absent.
- Existing EDGE-31 firebreak behavior remains intact.

## Runtime Proof Required After Merge

Later PRs must prove real runtime population of these fields from live/replay data:

- EDGE-36: feed staleness recovery evidence
- EDGE-37: executable trade quality report

## What This PR Does Not Prove

This PR does not prove live feed health, live broker readiness, live executable trade quality, strategy expectancy, or profitability.

## Human Approval

Human approval required before merge: verify CI is green and confirm that tests failing due to absent freshness fields are updated only when the test is meant to model real executable candidates.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
