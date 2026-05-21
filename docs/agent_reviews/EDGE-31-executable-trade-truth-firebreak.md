# EDGE-31 — Executable Trade Truth Firebreak

## Market-state note

The market is closed during this implementation. This PR does not claim live feed validation, live executable trade quality, or live broker readiness. It proves deterministic guard behavior only.

## Agent Work Contract

### Scope

Implement a strict executable-truth firebreak that prevents fallback, recovered fallback, degraded advisory data, stale quotes, missing or unverified spread, missing liquidity validation, planning/debug/advisory rows, and low data confidence from passing pre-trade execution quality.

### Files changed

- `core/executable_truth.py`
- `core/execution_quality.py`
- `tests/test_executable_truth_firebreak.py`
- `docs/ops/EXECUTABLE_QUALITY_ROADMAP.md`
- `docs/agent_reviews/EDGE-31-executable-trade-truth-firebreak.md`

### Out of scope

- No new strategies.
- No broker/live order placement changes.
- No feed recovery rewrite.
- No dashboard redesign.
- No ML ranker work.
- No threshold loosening.

## Grill Me Review

### Hard questions

1. Can a fallback candidate still pass because it has `execution_entry_status=executable`?
   - Expected answer: no. The new pure classifier blocks fallback flags and fallback chain sources before slippage/order-policy logic.

2. Can PAPER/SIM degraded advisory data still be treated as executable?
   - Expected answer: no. The previous permissive degraded-data path is now blocked by the firebreak.

3. Does this prove live market quality?
   - Expected answer: no. Market is closed. This PR only proves deterministic behavior.

4. Could this reduce candidate count?
   - Yes. That is intentional. Fake executable trades are worse than zero trades.

## Hermes Review

### Boundary check

- The change is pure/read-only from a broker perspective.
- No broker APIs are called.
- No order placement, modification, cancellation, or live adapter behavior changed.
- The firebreak is deterministic and side-effect free.

### Safety behavior

- Unsafe data fails closed.
- Fallback/degraded rows become non-executable.
- Clean fresh candidates are still allowed by the classifier.

## GSD Review

### What this actually improves

This PR reduces false executable confidence. It does not create strategy edge. It creates the guardrail needed before strategy edge can be measured honestly.

### Remaining gaps

- Per-candidate quote freshness contract still belongs to EDGE-32.
- Bid/ask/spread hard gate depth belongs to EDGE-33.
- Scoring reweight belongs to EDGE-34.
- Live feed recovery evidence belongs to EDGE-36.

## Scope Guard

This PR intentionally avoids touching strategy generation and feed subscription logic. It only blocks bad data from being treated as executable by execution-quality evaluation.

## Approval + Evidence

### Tests added

`tests/test_executable_truth_firebreak.py` covers:

- clean fresh candidate allowed by classifier
- fallback candidate blocked
- recovered fallback source blocked
- degraded advisory PAPER data blocked
- stale quote blocked
- unverified spread blocked
- low data confidence blocked

### Local commands to run

```bash
pytest tests/test_executable_truth_firebreak.py -q
pytest tests/test_execution_quality.py tests/test_opportunity_engine.py -q
```

### Acceptance statement

EDGE-31 is acceptable only if the new test file passes and existing execution-quality/opportunity-engine tests do not regress.
