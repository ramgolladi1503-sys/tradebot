# EDGE-02 — Paper Outcome Journal Population Contract

## Evidence Contract

mode: PAPER
candidate_id: EDGE-02-paper-outcome-journal-contract
decision: ADD_PAPER_OUTCOME_JOURNAL_CONTRACT
reason: EDGE-01 showed zero outcome records, so paper outcomes must be validated and appended to the existing family outcome journal before strategy validation can be trusted.
timestamp: 2026-05-20T18:45:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/EDGE-02-paper-outcome-journal-contract.md

## Agent Work Contract

### Purpose
Create a fail-closed contract for paper outcome records so EDGE-01 has real journal data to audit.

### Scope

- Normalize one terminal paper outcome record.
- Validate allowed terminal statuses.
- Require candidate identifier, strategy family, and direction.
- Append valid records through the existing `record_family_outcome()` path.
- Keep `family_outcomes.jsonl` as the source of truth.
- Provide read-only integrity reporting for candidate outcome records.

### Explicit non-scope

- No strategy changes.
- No scoring changes.
- No ranking changes.
- No dashboard changes.
- No broker calls.
- No live execution behavior.
- No paper order creation.
- No runtime wiring in this PR.

## Grill Me Review

### Hard question
Does this populate the journal during live paper sessions automatically?

### Answer
No. This PR creates the contract and writer. Runtime wiring should be a separate PR after this contract is accepted.

### Hard question
Does this prove edge?

### Answer
No. It only makes paper outcome records valid enough for EDGE-01 to measure edge later.

### Hard question
What can still silently kill the product?

### Answer
If runtime never calls this contract, the journal will remain empty. The next PR must wire terminal paper outcomes into this contract.

## Hermes Review

### Boundary status

- Scope pass: yes.
- Broker boundary: untouched.
- Live boundary: untouched.
- Dashboard boundary: untouched.
- Strategy behavior: untouched.
- Runtime behavior: untouched.

### Safety fields

The journal record explicitly carries non-action flags as false:

- `is_order_action`
- `broker_api_called`
- `live_order_action`
- `broker_order_action`

## GSD Plan / Review

### Files changed

- `core/paper_outcome_journal.py`
- `tests/test_paper_outcome_journal.py`
- `docs/agent_reviews/EDGE-02-paper-outcome-journal-contract.md`

### Testing note

Local test coverage was added for:

- terminal status aliases normalize correctly
- unknown terminal status fails closed
- blank identity fields fail closed
- valid record appends through `record_family_outcome()`
- integrity report exposes invalid rows

### Local commands to run after checkout

```bash
python -m pytest tests/test_paper_outcome_journal.py tests/test_edge_baseline_audit.py
```

## Scope Guard

Allowed:

- Add journal contract module.
- Validate terminal outcomes.
- Append to existing family outcome journal.
- Keep all safety/action flags false.

Blocked:

- runtime wiring
- paper order creation
- broker integration
- dashboard display
- scoring changes
- strategy changes

## Approval + Evidence

### Acceptance checks

- Allowed terminal statuses are exactly:
  - executed
  - rejected-saved-loss
  - rejected-missed-win
  - expired-no-move
  - stopped
  - target-hit
  - timed-exit
- Blank terminal status fails closed.
- Blank candidate identifier fails closed.
- Blank strategy family fails closed.
- Blank direction fails closed.
- Valid records use the existing family outcome journal path.

### Next PR
EDGE-03 should wire terminal paper outcomes into this contract so the EDGE-01 audit no longer reports zero records.