# Agent Review — EDGE-60 BUY/PE/CE Directional Bias Audit

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
- No order submit/modify/cancel/exit behavior
- No dashboard rewrite

## Grill Me Review

### Challenge 1 — Is this just another fake metric?

Risk: A directional report could become vanity evidence if it only counts rows and misses fallback/advisory pollution.

Answer: The audit separates executable, advisory, and fallback buckets. Fallback and advisory concentration warnings are separate from executable skew warnings.

Proof:

- `test_mixed_fallback_and_advisory_candidates_are_counted_separately_from_executable`

### Challenge 2 — Can unknown direction silently pass?

Risk: Missing direction fields could make a row look neutral and avoid warnings.

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

## Scope Guard

Confirmed not touched:

- broker code
- live order code
- strategy scoring
- thresholds
- capital allocation
- dashboard layout
- runtime execution paths

## Acceptance Evidence

Required tests:

```bash
PYTHONPATH=. python -m pytest tests/test_edge60_directional_bias_audit.py
```

Covered acceptance gates:

- Balanced CE/PE candidates produce no bias warning.
- All BUY/CALL candidates produce directional-skew warning.
- Mixed fallback/advisory candidates are counted separately from executable candidates.
- Unknown/missing direction fails closed into audit warning, not executable truth.
- Audit output is deterministic.
- Existing tests should remain green.

## Remaining risk

Direction extraction is intentionally conservative, but candidate schemas may evolve. Future PRs that introduce `CandidateIntent` or strategy-specific contracts should wire canonical direction fields into this audit instead of relying on loose row extraction.
