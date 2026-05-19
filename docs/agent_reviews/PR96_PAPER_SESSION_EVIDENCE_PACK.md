# PR #96 — Paper Session Evidence Pack

## Agent Work Contract

### Scope

Add a deterministic, read-only paper session evidence pack assembler that composes already-built reports into one JSON-friendly evidence object.

### Files changed

- `core/paper_session_evidence_pack.py`
- `tests/test_paper_session_evidence_pack.py`
- `docs/agent_reviews/PR96_PAPER_SESSION_EVIDENCE_PACK.md`

### Hard boundaries

- No runtime wiring.
- No file reads.
- No file writes.
- No persistence/event writing.
- No broker calls.
- No live execution behavior.
- No paper order creation.
- No paper order mutation.
- No paper risk ledger mutation.
- No fill/slippage changes.
- No dashboard changes.
- No external agent auto-calling, webhook, API, auto-merge, or dashboard agent work.

### Contract

The evidence pack must include:

- session gate report
- risk ledger snapshot
- optional paper decision reports
- optional paper order records
- optional fill decisions
- optional extra artifacts
- stable section names
- artifact count
- safety flags fixed false
- blockers/warnings/reasons

### Fail-closed rules

The pack must block if:

- session gate report is missing
- session gate did not pass
- session gate evidence is incomplete
- risk ledger snapshot is missing
- risk ledger halt is active
- nested reports carry action/live/broker/append flags
- supplied order/fill evidence exceeds gate counts
- optional report sections are not lists

## Grill Me Review

### Challenge

An evidence pack that merely bundles JSON can create fake confidence. It must reject unsafe/missing prerequisite evidence and not pretend to run or validate a live session.

### Findings

- Good: requires a passing session gate.
- Good: requires a risk ledger snapshot.
- Good: rejects unsafe nested flags.
- Good: checks supplied evidence counts against gate counts.
- Constraint: no IO or runtime wiring in this PR.

### Result

Approved with no-runtime/no-persistence constraint.

## Hermes Review

### Scope verification

- No broker imports.
- No live execution enablement.
- No dashboard files touched.
- No runtime files touched.
- No filesystem reads/writes.
- No order state machine mutation.
- No ledger mutation.

### Safety verification

- Output remains read-only and non-action.
- Unsafe nested reports are rejected.
- Missing gate/ledger evidence blocks pack readiness.

### Result

Approved.

## GSD Review

### Implementation plan

1. Add evidence pack dataclass.
2. Add `build_paper_session_evidence_pack(...)` pure assembler.
3. Normalize optional report lists.
4. Validate safety flags in all supplied reports.
5. Add tests for ready and blocked paths.

### Test command

```bash
PYTHONPATH=. pytest -q tests/test_paper_session_evidence_pack.py
```

### Result

Approved.

## Scope Guard

### In scope

- Pure evidence pack assembler.
- Tests.
- 3-agent evidence.

### Out of scope

- Runtime wiring.
- Persistence.
- File IO.
- Dashboard.
- Broker calls.
- Live execution.
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
- Grill Me: PASS with no-runtime/no-persistence constraint
- Hermes: PASS
- GSD: PASS
- Scope Guard: PASS
