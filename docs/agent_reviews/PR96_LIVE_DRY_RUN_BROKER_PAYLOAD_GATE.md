# PR #96 — Live Dry-Run Broker Payload Gate

## Agent Work Contract

### Scope

Add a pure/read-only gate that validates a broker-order-shaped payload in dry-run mode before any later broker dry-run proof work.

### Files changed

- `core/live_dry_run_broker_payload_gate.py`
- `tests/test_live_dry_run_broker_payload_gate.py`
- `docs/agent_reviews/PR96_LIVE_DRY_RUN_BROKER_PAYLOAD_GATE.md`

### Hard boundaries

- No broker calls.
- No live order submission.
- No submit/modify/cancel/exit behavior.
- No runtime wiring.
- No dashboard changes.
- No file writes.
- No persistence/event writing.
- No paper order mutation.
- No paper risk ledger mutation.
- No fill/slippage changes.
- No external agent auto-calling, webhook, API, auto-merge, or dashboard agent work.

### Contract

The gate must:

- require `dry_run=true`
- reject all action flags
- validate required broker payload fields
- validate supported exchange, transaction type, order type, product, variety, and validity
- validate quantity and price/trigger-price semantics
- preserve upstream blockers/warnings
- emit a stable JSON-friendly non-action report

## Grill Me Review

### Challenge

A broker dry-run payload gate is dangerous if it gets confused with broker execution. It must validate shape only and never submit anything.

### Findings

- Good: no broker imports or calls.
- Good: dry-run is mandatory.
- Good: action/live/broker flags fail closed.
- Good: malformed payloads fail closed.
- Constraint: no runtime wiring and no broker adapter integration in this PR.

### Result

Approved with no-broker/no-runtime constraint.

## Hermes Review

### Scope verification

- No broker adapter imports.
- No live execution enablement.
- No dashboard files touched.
- No runtime files touched.
- No order state machine mutation.
- No ledger mutation.
- No file writes.

### Safety verification

- Output is read-only and non-action.
- Input action flags are rejected.
- Unsupported payload values are blocked.
- The gate cannot place, modify, cancel, or exit orders.

### Result

Approved.

## GSD Review

### Implementation plan

1. Add gate report dataclass.
2. Add pure `build_live_dry_run_broker_payload_gate_report(...)`.
3. Validate required broker-shaped fields.
4. Validate price/trigger-price semantics by order type.
5. Add positive and negative tests.

### Test command

```bash
PYTHONPATH=. pytest -q tests/test_live_dry_run_broker_payload_gate.py
```

### Result

Approved.

## Scope Guard

### In scope

- Pure dry-run payload validation.
- Stable gate report.
- Tests and evidence.

### Out of scope

- Broker API calls.
- Runtime wiring.
- Dashboard.
- File writes.
- Persistence.
- Paper order mutation.
- Ledger mutation.
- Fill/slippage changes.
- PR #97+ work.

### Result

PASS.

## Approval + Evidence

PR #96 is approved for PR creation once targeted tests pass.

Evidence summary for PR body/comment:

- Agent Work Contract: PASS
- Grill Me: PASS with no-broker/no-runtime constraint
- Hermes: PASS
- GSD: PASS
- Scope Guard: PASS
