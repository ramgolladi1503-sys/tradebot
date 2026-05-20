# EDGE-06 — Paper Exit Outcome Truth

## Evidence Contract

mode: PAPER
candidate_id: EDGE-06-paper-exit-outcome-truth
decision: ADD_PAPER_EXIT_OUTCOME_TRUTH_CONTRACT
reason: EDGE-05 records entry-order truth only; edge validation needs closed paper exit truth for target-hit, stopped, and timed-exit outcomes.
timestamp: 2026-05-20T20:25:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/EDGE-06-paper-exit-outcome-truth.md

## Agent Work Contract

### Purpose
Add a fail-closed contract for closed PAPER exit outcomes so the journal can carry actual trade outcome truth, not only entry-order fill truth.

### Scope

- Normalize PAPER exit outcomes: `target-hit`, `stopped`, `timed-exit`.
- Compute gross P&L from entry price, exit price, quantity, and direction.
- Compute slippage-adjusted P&L.
- Compute realized R multiple when risk per unit or stop price is available.
- Append valid exit outcomes through the existing paper outcome journal path.
- Add focused tests for bullish, bearish, target, stop, invalid, and journal append behavior.

### Explicit non-scope

- No runtime position monitor.
- No strategy changes.
- No scoring changes.
- No ranking changes.
- No dashboard changes.
- No broker calls.
- No live execution behavior.
- No fake production records.

## Grill Me Review

### Hard question
Does this make the bot profitable?

### Answer
No. It only records closed exit truth so profitability can be measured later. It does not improve entries, exits, or strategy selection.

### Hard question
Does this wire real runtime exits yet?

### Answer
No. This PR adds the contract and journal writer. Runtime/position lifecycle wiring should be a later PR once the actual exit owner is identified.

### Hard question
What can still silently kill edge validation?

### Answer
If candidates lack setup identity or runtime never calls this contract, the journal remains incomplete. Setup identity and runtime exit wiring are still required before expectancy reporting.

## Hermes Review

### Boundary status

- PAPER-only evidence contract.
- Broker boundary untouched.
- Live boundary untouched.
- Dashboard untouched.
- Strategy/scoring/ranking untouched.

### Important limitation
This PR creates exit outcome truth from explicit input facts. It does not discover exits from live market monitoring.

## GSD Plan / Review

### Files changed

- `core/paper_exit_outcome.py`
- `tests/test_paper_exit_outcome.py`
- `docs/agent_reviews/EDGE-06-paper-exit-outcome-truth.md`

### Tests

```bash
python -m pytest tests/test_paper_exit_outcome.py tests/test_execution_router_paper_outcomes.py tests/test_paper_outcome_journal.py tests/test_edge_baseline_audit.py
```

### Proof added

- Target-hit computes positive bullish P&L and R multiple.
- Stopped computes negative R multiple.
- Bearish direction reverses P&L calculation correctly.
- Bad exit outcomes fail closed.
- Invalid or blank numeric fields fail closed.
- Valid exit outcome appends through the existing journal.

## Scope Guard

Allowed:

- Exit outcome contract.
- P&L and R-multiple calculations.
- Journal append through existing paper outcome path.
- Tests and evidence documentation.

Blocked:

- Runtime exit wiring.
- Strategy/scoring/ranking changes.
- Broker integration.
- Dashboard display.
- Fake seeded runtime records.

## Approval + Evidence

### Acceptance checks

- `target-hit`, `stopped`, and `timed-exit` are valid exit outcomes.
- Unknown exit outcome is rejected.
- Entry price, exit price, and quantity are required.
- Slippage-adjusted P&L is calculated.
- Realized R is calculated when risk is known.
- Output remains non-action evidence.

### Next PR
EDGE-07 should add setup hypothesis identity (`setup_id`, `entry_rule_id`, `exit_rule_id`, `cost_model_version`) before setup expectancy reporting.
