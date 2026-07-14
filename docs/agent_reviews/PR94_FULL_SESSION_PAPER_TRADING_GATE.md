# PR #94 — Full-Session Paper Trading Gate

## Agent Work Contract

### Scope

Add a deterministic, read-only full-session paper trading gate that evaluates a completed paper session snapshot and returns a stable PASS/FAIL report.

### Files changed

- `core/paper_session_gate.py`
- `tests/test_paper_session_gate.py`
- `docs/agent_reviews/PR94_FULL_SESSION_PAPER_TRADING_GATE.md`

### Hard boundaries

- No broker calls.
- No live execution behavior.
- No paper order creation.
- No paper order mutation.
- No paper risk ledger mutation.
- No fill/slippage changes.
- No runtime wiring.
- No dashboard changes.
- No persistence/event writing.
- No external agent auto-calling, webhook, API, auto-merge, or dashboard agent work.

### Contract

The gate must expose a JSON-friendly report with:

- session state: `SESSION_GATE_PASS` or `SESSION_GATE_FAIL`
- feed uptime
- stale feed duration
- websocket disconnect count
- restart count
- crash-loop status
- evidence completeness
- candidate count
- paper order count
- paper fill count
- paper rejection count
- fallback paper fill count
- stale-feed paper fill count
- unresolved-contract paper fill count
- missing-evidence trade count
- realized PnL
- max drawdown
- explicit pass criteria
- safety flags fixed false: `broker_order_action`, `live_order_action`, `is_order_action`, `append`

### Hard pass/fail conditions

The session must fail if any of the following are true:

- fallback paper fills > 0
- stale-feed paper fills > 0
- unresolved-contract paper fills > 0
- missing-evidence trades > 0
- evidence incomplete
- crash loop detected
- feed uptime below threshold
- stale-feed duration above threshold
- websocket disconnect count above threshold
- restart count above threshold
- count relationships are impossible
- unsafe action flags appear in input

## Grill Me Review

### Challenge

A session gate that only records metrics is useless. It must block unsafe or unproven paper sessions, otherwise the system graduates fake confidence.

### Findings

- Good: unsafe paper fills fail the session explicitly.
- Good: missing evidence fails closed.
- Good: crash-loop and feed-stability checks are encoded.
- Good: impossible count relationships fail.
- Constraint: this PR must not wire runtime or read files. Runtime integration belongs to a later scoped PR.

### Result

Approved with constraint: pure gate/report only, no runtime wiring.

## Hermes Review

### Scope verification

- No broker imports.
- No live execution enablement.
- No dashboard files touched.
- No runtime files touched.
- No order state machine mutation.
- No ledger mutation.
- No filesystem writes.
- No append behavior.

### Security/safety verification

- Input flags `broker_order_action`, `live_order_action`, `is_order_action`, and `append` are rejected as blockers.
- Output report keeps all action flags false.

### Result

Approved.

## GSD Review

### Implementation plan

1. Add `PaperSessionGateReport` dataclass.
2. Add `build_paper_session_gate_report(...)`.
3. Encode feed/session/evidence/fill pass criteria.
4. Add tests for clean pass path.
5. Add negative tests for fallback fills, stale fills, unresolved-contract fills, missing evidence, crash loop, bad counts, action flags, and invalid thresholds.

### Test command

```bash
PYTHONPATH=. pytest -q tests/test_paper_session_gate.py
```

### Result

Approved.

## Scope Guard

### In scope

- Pure read-only session gate.
- Stable report contract.
- Deterministic pass/fail logic.
- Tests and evidence.

### Out of scope

- Runtime wiring.
- Persistence.
- File IO.
- Paper order lifecycle changes.
- Ledger mutation.
- Broker calls.
- Dashboard.
- Strategy/scoring/ranking changes.
- Fill/slippage changes.
- PR #95+ work.

### Result

PASS.

## Approval + Evidence

PR #94 is approved for PR creation once targeted tests pass.

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
