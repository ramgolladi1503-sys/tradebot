# EDGE-33 — Option Bid/Ask and Spread Truth Gate

mode: PAPER
candidate_id: EDGE-33
source: docs/agent_reviews/EDGE-33-option-bid-ask-spread-truth-gate.md
timestamp: 2026-05-22T11:10:00+05:30
decision: require option bid/ask/spread truth before execution-capable candidates can pass truth validation
reason: LTP-only rows are not executable option trades
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Market-state note

This PR does not claim live market validation. It adds deterministic spread truth enforcement using candidate fields and tests. Live market proof remains scoped to later EDGE-36/EDGE-37 work.

## Agent Work Contract

### Scope

Implement an option bid/ask/spread truth gate that blocks execution-capable rows unless the row carries usable bid/ask and acceptable spread evidence.

Required candidate evidence:

- bid greater than zero
- ask greater than zero
- ask greater than or equal to bid
- calculated spread within configured ceiling
- quote completeness is full or complete
- spread source is not fallback/synthetic
- LTP, when present, is within acceptable bid/ask drift range

### Files changed

- `core/option_spread_truth.py`
- `core/executable_truth.py`
- `tests/test_option_spread_truth_gate.py`
- `docs/agent_reviews/EDGE-33-option-bid-ask-spread-truth-gate.md`

### Out of scope

- No strategy changes.
- No broker/live order placement changes.
- No feed recovery rewrite.
- No dashboard changes.
- No ML/ranker changes.
- No auto-threshold tuning.

## Grill Me Review

### Hard questions

1. Can an LTP-only row become executable?
   - No. The spread truth gate requires bid and ask.

2. Can a wide-spread option pass because its signal score is high?
   - No. Wide spread blocks before selection quality can treat it as executable.

3. Can a fallback/synthetic spread pass?
   - No. Fallback and synthetic spread sources are blocked.

4. Does this prove live fill quality?
   - No. This only proves deterministic bid/ask/spread truth gating.

## Hermes Review

### Broker boundary

- No broker APIs are called.
- No order placement, modification, cancellation, or live adapter behavior changed.
- The spread truth classifier is pure and deterministic.

### Safety behavior

- Missing bid blocks execution-capable rows.
- Missing ask blocks execution-capable rows.
- Inverted bid/ask blocks execution-capable rows.
- Wide spreads block execution-capable rows.
- Partial quotes block execution-capable rows.
- Fallback spread sources block execution-capable rows.

## QA / Safety Review

### Tests added

`tests/test_option_spread_truth_gate.py` covers:

- clean bid/ask candidate passes
- LTP-only candidate blocks
- inverted bid/ask blocks
- wide spread blocks
- LTP outside bid/ask range blocks
- partial quote blocks
- fallback spread source blocks
- read-only safety assertion

### Regression risk

Existing tests may construct executable candidates with only LTP/entry price. If those tests model real executable candidates, they must add bid/ask/spread proof. If they are advisory or non-execution fixtures, they must be marked non-executable.

## GSD Review

### What this improves

This PR prevents false executable confidence caused by LTP-only option rows. It makes bid/ask/spread evidence mandatory for executable candidates.

### What this does not improve

- It does not fix live feed staleness recovery.
- It does not prove fill probability.
- It does not improve strategy edge.
- It does not guarantee profitability.

## Scope Guard

The implementation is limited to a pure option spread truth classifier and integration into the existing executable truth firebreak.

## Approval + Evidence

### Local commands to run

```bash
pytest tests/test_option_spread_truth_gate.py -q
pytest tests/test_candidate_quote_freshness_contract.py tests/test_executable_truth_firebreak.py tests/test_execution_quality.py tests/test_opportunity_engine.py -q
```

## Acceptance Proof

Acceptance requires:

- Clean bid/ask executable candidates pass.
- LTP-only execution-capable candidates are blocked.
- Invalid/wide/fallback/partial quote candidates are blocked.
- Existing EDGE-31 and EDGE-32 behavior remains intact.

## Runtime Proof Required After Merge

Later PRs must prove real runtime population of bid/ask/spread fields from live/replay data:

- EDGE-36: feed staleness recovery evidence
- EDGE-37: executable trade quality report

## What This PR Does Not Prove

This PR does not prove live fill quality, live market liquidity, broker readiness, strategy expectancy, or profitability.

## Human Approval

Human approval required before merge: verify CI is green and confirm that tests failing due to LTP-only executable fixtures are updated only when the test is meant to model real executable candidates.


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
