# EDGE-03 — Terminal Paper Outcome Journal Wiring

## Evidence Contract

mode: PAPER
candidate_id: EDGE-03-terminal-paper-outcome-wiring
decision: WIRE_TERMINAL_PAPER_OUTCOMES_TO_JOURNAL
reason: EDGE-01 still reports zero records after EDGE-02 because no terminal paper order path calls the journal contract yet.
timestamp: 2026-05-20T19:05:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/EDGE-03-terminal-paper-outcome-wiring.md

## Agent Work Contract

### Purpose
Convert already-terminal paper order records into EDGE-02 journal records so the edge audit can receive real paper outcome data.

### Scope

- Build one terminal outcome draft from an already-terminal paper order record.
- Map terminal paper order states to EDGE-02 terminal outcomes.
- Append valid terminal outcomes through `record_paper_outcome()`.
- Preserve `family_outcomes.jsonl` as the source of truth.
- Add tests proving non-terminal records are rejected and terminal records are appended.

### Explicit non-scope

- No runtime loop wiring.
- No paper order state transition changes.
- No fill simulation changes.
- No strategy changes.
- No scoring changes.
- No ranking changes.
- No dashboard changes.
- No broker calls.
- No live execution behavior.

## Grill Me Review

### Hard question
Does this make EDGE-01 show non-zero records immediately after merge?

### Answer
No. It creates the wiring function and tests it with terminal paper order records. A later runtime integration must call this function during actual paper sessions.

### Hard question
Does this prove edge?

### Answer
No. It only closes the gap between terminal paper order records and the journal. Edge proof still requires real journal samples and score-bucket validation.

### Hard question
What can still silently kill the product?

### Answer
If the runtime never passes terminal paper orders into this function, the production journal remains empty. The next PR must connect the actual session runner or terminal order owner.

## Hermes Review

### Boundary status

- Broker boundary: untouched.
- Live boundary: untouched.
- Dashboard boundary: untouched.
- Strategy behavior: untouched.
- Scoring behavior: untouched.
- Runtime loop behavior: untouched.

### Safety fields

The output record exposes non-action flags as false through read-only properties and serialized dictionary fields:

- `is_order_action`
- `broker_api_called`
- `live_order_action`
- `broker_order_action`

## GSD Plan / Review

### Files changed

- `core/paper_terminal_outcome_wiring.py`
- `tests/test_paper_terminal_outcome_wiring.py`
- `docs/agent_reviews/EDGE-03-terminal-paper-outcome-wiring.md`

### Tests

```bash
python -m pytest tests/test_paper_terminal_outcome_wiring.py tests/test_paper_outcome_journal.py tests/test_edge_baseline_audit.py
```

### Proof added

- Filled terminal paper order maps to `executed`.
- Rejected terminal paper order maps to `rejected-saved-loss` by default.
- Non-terminal paper order is rejected.
- Strategy family and direction are required.
- Terminal paper outcome appends to the existing family outcome journal.

## Scope Guard

Allowed:

- Terminal paper order to journal mapping.
- Journal append through EDGE-02.
- Tests around terminal and non-terminal behavior.

Blocked:

- Runtime session integration.
- Broker integration.
- Dashboard display.
- Strategy/scoring/ranking changes.
- Fake seeded production records.

## Approval + Evidence

### Acceptance checks

- Already-terminal paper order can become a journal outcome.
- Non-terminal paper order cannot become a journal outcome.
- Journal output remains non-action evidence.
- Valid terminal paper order writes to `family_outcomes.jsonl` through the existing EDGE-02 path.

### Next PR
EDGE-04 should locate the actual paper session owner and call `record_terminal_paper_outcome()` when paper orders become terminal.
