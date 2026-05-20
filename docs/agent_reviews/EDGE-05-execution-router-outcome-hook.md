# EDGE-05 — Execution Router Paper Outcome Hook

## Evidence Contract

mode: PAPER
candidate_id: EDGE-05-execution-router-outcome-hook
decision: WIRE_EXECUTION_ROUTER_PAPER_OUTCOMES_TO_JOURNAL
reason: EDGE-04 added a safe hook, but the real runtime owner is `core/execution_router.py`; PAPER runtime terminal entry-order states need to append journal records.
timestamp: 2026-05-20T19:55:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/EDGE-05-execution-router-outcome-hook.md

## Agent Work Contract

### Purpose
Wire the real PAPER execution-router terminal entry-order path to the EDGE-02 paper outcome journal so `family_outcomes.jsonl` can receive runtime records.

### Scope

- Add PAPER-only outcome journal write after execution-router terminal entry-order states.
- Map runtime order states to journal terminal statuses.
- Keep SIM and LIVE out of journal writes.
- Preserve broker/live safety boundaries.
- Add focused tests for mapping and fail-safe behavior.

### Explicit non-scope

- No strategy changes.
- No scoring changes.
- No ranking changes.
- No dashboard changes.
- No live placement behavior.
- No broker API calls.
- No exit/target/stop outcome proof yet.

## Grill Me Review

### Hard question
Does this prove profitability?

### Answer
No. Runtime `FILLED` here means entry-order fill, not target-hit or stop-hit. This creates entry-execution truth only. Profitability still requires exit-outcome journaling.

### Hard question
Why touch `execution_router.py`?

### Answer
Because it is the actual SIM/PAPER execution owner. It records intents, simulates fills, transitions order state, emits fill events, and aborts unsafe paper attempts. The standalone paper-order hook existed, but runtime was not using it.

### Hard question
Could this crash trading if journal write fails?

### Answer
No. The journal write is fail-safe: exceptions are caught, warning is logged once, and execution-router behavior continues.

## Hermes Review

### Boundary status

- PAPER-only write path.
- SIM excluded.
- LIVE excluded.
- Broker behavior untouched.
- Dashboard untouched.
- Strategy/scoring/ranking untouched.

### Important limitation
This is entry-order lifecycle truth, not full trade outcome truth.

- `FILLED` maps to `executed`.
- `REJECTED` maps to `rejected-saved-loss`.
- `EXPIRED` maps to `expired-no-move`.
- `CANCELLED` maps to `timed-exit`.

`target-hit` and `stopped` require a later exit lifecycle hook.

## GSD Plan / Review

### Files changed

- `core/execution_router.py`
- `tests/test_execution_router_paper_outcomes.py`
- `docs/agent_reviews/EDGE-05-execution-router-outcome-hook.md`

### Tests

```bash
python -m pytest tests/test_execution_router_paper_outcomes.py tests/test_paper_runtime_outcome_hook.py tests/test_paper_terminal_outcome_wiring.py tests/test_paper_outcome_journal.py tests/test_edge_baseline_audit.py
```

### Proof added

- PAPER filled entry order maps to `executed`.
- PAPER rejected/expired/cancelled entry orders map to safe terminal statuses.
- Non-terminal partial state is ignored.
- Journal write failure does not crash runtime.

## Scope Guard

Allowed:

- Execution-router PAPER terminal outcome journal write.
- Defensive catch around journal write.
- Tests for mapping and failure behavior.

Blocked:

- Real broker placement.
- Dashboard changes.
- Strategy/scoring/ranking changes.
- Treating entry fill as profit.
- Fake seeded production records.

## Approval + Evidence

### Acceptance checks

- PAPER entry fill can create a journal record.
- PAPER abort can create a terminal journal record.
- Non-terminal state does not create a journal record.
- Journal failure does not break execution flow.
- Entry-order outcome limitation is documented.

### Next PR
The next actual edge-quality PR should add exit outcome truth: target-hit, stopped, timed-exit after position lifecycle, not just entry execution.
