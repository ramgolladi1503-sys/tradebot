# Agent Review — EDGE-60 BUY/PE/CE Directional Bias Audit

mode: PAPER
candidate_id: EDGE-60-DIRECTIONAL-BIAS-AUDIT
decision: APPROVED_FOR_READ_ONLY_AUDIT_PR
reason: Adds deterministic read-only directional bias evidence without broker, live, order, scoring, strategy, or allocation behavior.
timestamp: 2026-05-24T17:50:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge_60_buy_pe_ce_directional_bias_audit.md

## Agent Work Contract

### Scope

Implement a pure/read-only directional bias audit for ranked/top opportunity payloads and candidate rows.

### Files changed

- `core/directional_bias_audit.py`
- `tests/test_edge60_directional_bias_audit.py`
- `docs/EDGE_60_BUY_PE_CE_DIRECTIONAL_BIAS_AUDIT.md`
- `docs/agent_reviews/edge_60_buy_pe_ce_directional_bias_audit.md`

### Explicit non-goals

- No strategy tuning
- No score-weight changes
- No threshold loosening
- No capital allocation
- No selection policy
- No broker imports
- No broker API calls
- No submit, modify, cancel, or exit behavior
- No dashboard rewrite

## Grill Me Review

### Challenge 1 — Is this just another fake metric?

Risk: A directional report could become vanity evidence if it only counts rows and misses fallback/advisory pollution.

Answer: The audit separates executable, advisory, and fallback buckets. Fallback and advisory concentration warnings are separate from executable skew warnings.

Proof:

- `test_mixed_fallback_and_advisory_candidates_are_counted_separately_from_executable`

### Challenge 2 — Can unknown direction silently pass?

Risk: Rows with no directional labels could look neutral and avoid warnings.

Answer: Unknown direction is counted and emits a fail-closed warning.

Proof:

- `test_unknown_or_missing_direction_fails_closed_into_audit_warning_not_execution_truth`

### Challenge 3 — Can contradictory labels hide bias?

Risk: A row with `action=BUY` and `side=SELL` or `option_type=CE` and `contract_type=PE` could be counted incorrectly.

Answer: Multiple action or option-side labels are treated as inconsistent and fail closed to `UNKNOWN` with warnings.

Proof:

- `test_inconsistent_direction_labels_fail_closed_into_warning`

## Hermes Review

### Contract quality

The module exposes one small public function, `audit_directional_bias(...)`, and immutable dataclass outputs. It avoids hidden global state except fixed label sets.

### Determinism

Counts and warnings are sorted. Output is deterministic except `generated_epoch`, which is intentionally runtime evidence.

Proof:

- `test_audit_output_is_deterministic_except_generated_epoch`

### Backward compatibility

No existing runtime/strategy/dashboard behavior is modified. The module is additive.

## GSD Review

### What changed

Added a read-only contract that makes directional concentration visible before allocation or selection logic exists.

### Why this matters

The product previously risked showing clean-looking top rows while being directionally biased because everything looked like `BUY` or because fallback/advisory rows polluted the top list.

### Smallest useful implementation

A pure audit module plus tests and docs. No UI integration, no allocation, no strategy changes.

## QA / Safety Review

### Safety boundaries checked

- No broker import was added.
- No live runtime path was modified.
- No order-action function was added.
- No strategy score or threshold was changed.
- The report exposes `is_order_action=false` and `broker_api_called=false`.

### Negative and edge-case tests

- All one-sided BUY/CALL rows trigger skew warnings.
- Fallback and advisory rows are counted separately.
- Unknown direction fails closed into warning evidence.
- Inconsistent direction labels fail closed into warning evidence.
- Flat rows and wrapped top-opportunity payloads are both supported.

## Scope Guard

### In scope

- Add read-only directional bias audit module.
- Add focused unit tests.
- Add docs and agent-review evidence.

### Out of scope

- Strategy tuning.
- Scoring changes.
- Capital allocation.
- Runtime execution wiring.
- Broker behavior.
- Dashboard rewrite.

### Files not touched

- `core/execution_engine.py`
- `core/execution_router.py`
- `core/kite_client.py`
- `core/risk_engine.py`
- `strategies/*`
- `dashboard/streamlit_app.py`
- `dashboard/streamlit_app_runtime.py`

## Acceptance Proof

Required command:

```bash
PYTHONPATH=. python -m pytest tests/test_edge60_directional_bias_audit.py
```

Expected proof:

- Balanced CE/PE candidates produce no bias warning.
- All BUY/CALL candidates produce directional-skew warning.
- Mixed fallback/advisory candidates are counted separately from executable candidates.
- Unknown direction fails closed into audit warning, not executable truth.
- Audit output is deterministic except timestamp evidence.
- Existing tests remain green in CI.

## Runtime Proof Required After Merge

EDGE-60 has no runtime wiring, so runtime proof is limited to confirming no runtime behavior changed.

Required after merge:

1. Confirm the dashboard and runtime still start from the same existing entrypoints.
2. Confirm no new broker calls appear in logs because this PR has no broker path.
3. Confirm the audit can be imported in a local shell without side effects.

## What This PR Does Not Prove

- It does not prove the strategies have real alpha.
- It does not prove the top opportunity is profitable.
- It does not prove capital allocation is safe.
- It does not prove regime selection is correct.
- It does not prove feed freshness is solved.
- It does not prove dashboard visibility for this audit.

## Human Approval

Human approval required before merge:

- Reviewer must verify this PR remains audit-only.
- Reviewer must verify CI is green.
- Reviewer must verify no broker/live/order scope entered the patch.

## Remaining Risk

Direction extraction is intentionally conservative, but candidate schemas may evolve. Future PRs that introduce `CandidateIntent` or strategy-specific contracts should wire canonical direction fields into this audit instead of relying on loose row extraction.
