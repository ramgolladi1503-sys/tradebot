# EDGE-04 — Runtime Paper Terminal Outcome Hook

## Evidence Contract

mode: PAPER
candidate_id: EDGE-04-runtime-terminal-outcome-hook
decision: ADD_EXPLICIT_RUNTIME_TERMINAL_OUTCOME_HOOK
reason: EDGE-03 added terminal order to journal wiring, but runtime owners need a safe explicit hook that preserves the pure state-machine boundary.
timestamp: 2026-05-20T19:35:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/EDGE-04-runtime-terminal-outcome-hook.md

## Agent Work Contract

### Purpose
Provide a narrow callable hook for runtime owners to transition paper orders and record journal outcomes only when the resulting paper order state is terminal.

### Scope

- Add an explicit hook wrapper around `transition_paper_order()`.
- Preserve the pure paper order state-machine module.
- Record a journal outcome only after terminal states.
- Keep non-terminal transitions journal-silent.
- Return JSON-friendly hook evidence.
- Add tests for non-terminal and terminal transitions.

### Explicit non-scope

- No strategy changes.
- No scoring changes.
- No ranking changes.
- No dashboard changes.
- No broker calls.
- No live execution behavior.
- No paper fill/slippage model changes.
- No automatic runtime loop insertion in this PR.

## Grill Me Review

### Hard question
Does this automatically make live paper sessions populate the journal?

### Answer
No. It provides the safe hook that the runtime/session owner can call. A later PR must replace the actual terminal transition call site with this hook.

### Hard question
Why not just modify `transition_paper_order()` to write the journal?

### Answer
Because the state-machine module explicitly promises no file writes or runtime wiring. Changing that would destroy a clean boundary and create hidden side effects.

### Hard question
What can still silently kill the product?

### Answer
If the runtime never uses this hook, the journal remains empty. The next PR must identify and update the real runtime call site.

## Hermes Review

### Boundary status

- Pure state machine preserved.
- Broker boundary untouched.
- Live boundary untouched.
- Dashboard boundary untouched.
- Strategy behavior untouched.
- Scoring behavior untouched.

### Safety fields

Hook result emits non-action flags as false:

- `is_order_action`
- `broker_api_called`
- `live_order_action`
- `broker_order_action`

## GSD Plan / Review

### Files changed

- `core/paper_runtime_outcome_hook.py`
- `tests/test_paper_runtime_outcome_hook.py`
- `docs/agent_reviews/EDGE-04-runtime-terminal-outcome-hook.md`

### Tests

```bash
python -m pytest tests/test_paper_runtime_outcome_hook.py tests/test_paper_terminal_outcome_wiring.py tests/test_paper_outcome_journal.py tests/test_edge_baseline_audit.py
```

### Proof added

- Non-terminal transition does not write journal records.
- Terminal transition writes a journal record.
- Journal record uses existing `family_outcomes.jsonl` path.
- Family learning state sample count updates.
- Hook evidence remains non-action and JSON-friendly.

## Scope Guard

Allowed:

- Explicit transition-and-record hook.
- Terminal-only journal append behavior.
- Tests proving terminal and non-terminal behavior.

Blocked:

- Mutating the pure state machine to write files.
- Broker integration.
- Dashboard display.
- Strategy/scoring/ranking changes.
- Fake seeded production records.

## Approval + Evidence

### Acceptance checks

- CREATED -> SUBMITTED does not write a journal record.
- SUBMITTED -> FILLED writes one journal record.
- Hook does not call broker APIs.
- Hook does not create live actions.
- State-machine purity is preserved.

### Next PR
EDGE-05 should update the actual runtime/session call site to use `transition_paper_order_and_record_outcome()` when paper orders reach terminal states.
