# EDGE-41 - Fallback Execution Firewall

## Purpose

EDGE-41 prevents fallback, stale, subscription-failed, and price-mismatch data from becoming execution-grade or rankable as a top executable opportunity.

The runtime diagnosis showed fallback and degraded quote sources in candidate/advisory paths. This PR hardens the existing executable-truth firebreak so those signals fail closed before execution quality and selector decisions can treat them as executable.

## Bug fixed

Observed runtime evidence included candidate rows with combinations such as:

```text
quote_source=rest_fallback
option_ltp_source=rest_fallback
option_ltp_source=subscription_failed
quote_validation_status=STALE_OPTION_LTP
quote_validation_status=PRICE_MISMATCH
score_inputs_used.rr_source=fallback_estimated
```

These rows must remain diagnostic/advisory only. They may be visible for debugging, but they must not become execution-grade, selected for execution, or top executable opportunities.

## Implementation boundary

This PR changes the existing execution-truth boundary only:

```text
core/executable_truth.py
```

It adds explicit detection for:

```text
rest_fallback
fallback_estimated RR
recovered_fallback / fallback_recovered
PRICE_MISMATCH
STALE_OPTION_LTP
subscription_failed
fallback markers inside quote truth snapshots
fallback / stale / price mismatch blocker text
```

The existing execution-quality layer already calls `classify_executable_truth()` before allowing execution quality to proceed. EDGE-41 uses that existing firebreak instead of creating a new selector or strategy path.

## Safety rules

```text
fallback-driven data -> not execution-grade
fallback-estimated RR -> not execution-grade
price mismatch -> not execution-grade
stale option LTP -> not execution-grade
subscription failure -> not execution-grade
```

These conditions can still be displayable or advisory for debugging, but they cannot be executable.

## What this PR does not do

- Does not change broker behavior.
- Does not place, modify, cancel, or exit trades.
- Does not change strategy generation.
- Does not tune scores for profitability.
- Does not fix websocket recovery.
- Does not unify quote truth fully; that belongs to EDGE-42.
- Does not solve feed split-brain; that belongs to EDGE-43.

## Acceptance tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge41_fallback_execution_firewall.py
PYTHONPATH=. python -m pytest tests/observability/test_fallback_execution_block.py
PYTHONPATH=. python -m pytest tests/test_opportunity_engine.py
```

## Expected proof

The tests prove:

```text
rest_fallback blocks executable truth
fallback_estimated RR blocks execution quality
PRICE_MISMATCH blocks even when entry is derivable
STALE_OPTION_LTP blocks executable truth
subscription_failed blocks executable truth
fallback candidate cannot become top executable opportunity
```

## Next PR

After EDGE-41 is merged, continue with:

```text
EDGE-44 - Feed Recovery Runtime Wiring
```
