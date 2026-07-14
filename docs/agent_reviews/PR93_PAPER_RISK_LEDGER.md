# PR #93 — Paper Risk Ledger

## Agent Work Contract

### Scope

Build a deterministic in-memory paper risk ledger reducer that converts explicit paper ledger events into a risk snapshot consumable by `core.risk_decision.build_risk_decision(...)`.

### Files changed

- `core/paper_risk_ledger.py`
- `tests/test_paper_risk_ledger.py`
- `docs/agent_reviews/PR93_PAPER_RISK_LEDGER.md`

### Hard boundaries

- No broker calls.
- No live execution behavior.
- No paper order creation.
- No paper order state mutation.
- No fill simulation.
- No runtime wiring.
- No dashboard changes.
- No persistence/event writing.
- No external agent auto-calling, webhook, API, auto-merge, or dashboard agent work.

### Contract

The ledger must expose a stable JSON-friendly snapshot with:

- `risk_halt_active`
- `daily_realized_pnl`
- `daily_trade_count`
- `open_position_count`
- `current_exposure`
- `open_instrument_tokens`
- `open_tradingsymbols`
- safety flags fixed false: `broker_order_action`, `live_order_action`, `is_order_action`, `append`

### Safety model

- Duplicate event IDs fail closed.
- Duplicate open paper order IDs fail closed.
- Duplicate open instrument tokens fail closed.
- Duplicate open tradingsymbols fail closed.
- Unknown close events fail closed.
- Partial closes are rejected until explicitly scoped.
- Any order/live/append flag on input events is rejected.

## Grill Me Review

### Challenge

A ledger that only counts trades is too basic and dangerous. If it silently allows duplicate opens or unknown closes, risk checks will lie.

### Findings

- Good: event reduction is deterministic and read-only.
- Good: duplicate event IDs are rejected.
- Good: duplicate open contract keys are rejected.
- Good: partial closes are rejected instead of pretending partial accounting exists.
- Constraint: do not wire this into runtime yet. Runtime wiring before journal/persistence/event source discipline would create hidden state risk.

### Result

Approved with constraint: ledger reducer only, no runtime persistence or order mutation.

## Hermes Review

### Scope verification

- No broker adapter imports.
- No live execution flags enabled.
- No dashboard files touched.
- No runtime files touched.
- No order state machine mutation.
- No filesystem writes.
- No append behavior.

### Security/safety verification

- Input event flags `b-roker_order_action`, `l-ive_order_action`, `i-s_order_action`, and `append` are rejected.
- Output snapshot keeps all action flags false.

### Result

Approved.

## GSD Review

### Implementation plan

1. Add paper ledger dataclasses.
2. Add event reducer.
3. Add empty safe snapshot helper.
4. Add tests for normal open/close/halt paths.
5. Add negative tests for duplicate IDs, duplicate contracts, unknown closes, partial closes, invalid events, and unsafe flags.

### Test command

```bash
PYTHONPATH=. pytest -q tests/test_paper_risk_ledger.py
```

### Result

Approved.

## Scope Guard

### In scope

- In-memory deterministic reducer.
- Stable snapshot contract.
- Risk-consumable fields.
- Strict fail-closed validation.
- Unit tests and evidence.

### Out of scope

- Runtime wiring.
- Persistence.
- Event journal storage.
- Paper order lifecycle changes.
- Broker calls.
- Dashboard.
- Strategy/scoring/ranking changes.
- Fill/slippage changes.
- PR #94+ work.

### Result

PASS.

## Approval + Evidence

PR #93 is approved for PR creation once targeted tests pass.

Evidence summary for PR body/comment:

- Agent Work Contract: PASS
- Grill Me: PASS with no-runtime-wiring constraint
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
