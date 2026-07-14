# PR #95 — Paper Trading Runbook Command

## Agent Work Contract

### Scope

Add a local/manual paper trading runbook command that validates an already-produced paper session snapshot through the full-session paper trading gate and prints a JSON report.

### Files changed

- `core/paper_trading_runbook_command.py`
- `scripts/paper_trading_runbook.py`
- `tests/test_paper_trading_runbook_command.py`
- `docs/agent_reviews/PR95_PAPER_TRADING_RUNBOOK_COMMAND.md`

### Hard boundaries

- No broker calls.
- No live execution behavior.
- No runtime start.
- No runtime wiring.
- No file writes.
- No persistence/event writing.
- No dashboard changes.
- No paper order creation.
- No paper order mutation.
- No paper risk ledger mutation.
- No fill/slippage changes.
- No external agent auto-calling, webhook, API, auto-merge, or dashboard agent work.

### Contract

The command must:

- accept a completed paper session snapshot JSON file
- validate it through `build_paper_session_gate_report(...)`
- emit a stable JSON report
- return exit code `0` only when the runbook state is ready
- return exit code `2` when the gate/report is blocked
- keep safety flags fixed false

## Grill Me Review

### Challenge

A runbook command is dangerous if it silently starts trading runtime, writes files, or pretends to generate evidence. It should be a local/manual validation wrapper only.

### Findings

- Good: command validates supplied snapshots only.
- Good: blocked gate means blocked runbook.
- Good: unsafe snapshot flags are rejected.
- Constraint: no runtime start and no file writes in this PR.

### Result

Approved with no-runtime/no-write constraint.

## Hermes Review

### Scope verification

- No broker imports.
- No live execution enablement.
- No dashboard files touched.
- No runtime files touched.
- No order state machine mutation.
- No ledger mutation.
- No file writes.

### Safety verification

- Output is read-only and non-action.
- CLI blocked path exits non-zero.
- The command cannot submit, modify, cancel, or place orders.

### Result

Approved.

## GSD Review

### Implementation plan

1. Add runbook report dataclass.
2. Add pure `build_paper_trading_runbook_report(...)`.
3. Add CLI wrapper under `scripts/`.
4. Add tests for ready and blocked states.
5. Add tests for unsafe flags and CLI exit codes.

### Test command

```bash
PYTHONPATH=. pytest -q tests/test_paper_trading_runbook_command.py
```

### Result

Approved.

## Scope Guard

### In scope

- Local/manual runbook command.
- Pure runbook report builder.
- CLI stdout JSON.
- Tests and evidence.

### Out of scope

- Runtime wiring.
- Runtime start.
- File writes.
- Persistence.
- Dashboard.
- Broker calls.
- Live execution.
- Paper order mutation.
- Ledger mutation.
- Fill/slippage changes.
- PR #96+ work.

### Result

PASS.

## Approval + Evidence

PR #95 is approved for PR creation once targeted tests pass.

Evidence summary for PR body/comment:

- Agent Work Contract: PASS
- Grill Me: PASS with no-runtime/no-write constraint
- Hermes: PASS
- GSD: PASS
- Scope Guard: PASS


## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A
