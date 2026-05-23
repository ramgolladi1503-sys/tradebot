# EDGE-42 — Quote Truth Single Source of Truth

## Purpose

EDGE-42 centralizes quote truth into one contract so source trust, quote validation status, reported age, timestamp-derived age, and rank/execution eligibility are not interpreted differently across modules.

The runtime diagnosis showed quote fields disagreeing across paths:

- `quote_source`: `unknown`, `rest_fallback`, `tick_store`, `live`
- `option_ltp_source`: `rest_fallback`, `subscription_failed`, `tick_store`
- validation: `STALE_OPTION_LTP`, `PRICE_MISMATCH`, `OK`

This PR makes `core.quote_truth.classify_quote_truth()` the canonical read-only decision contract for quote truth.

## Implementation

### `core/quote_truth.py`

Adds:

- `QuoteTruthDecision`
- `classify_quote_truth(payload, ...)`
- source trust classes:
  - `trusted_live`
  - `trusted_cache`
  - `fallback`
  - `subscription_failed`
  - `unknown`
- quote truth reasons:
  - `fallback_quote_source`
  - `subscription_failed_quote`
  - `price_mismatch_quote`
  - `stale_option_ltp`
  - `quote_age_timestamp_mismatch`
  - `quote_source_unknown`

The decision includes:

- `truth_ok`
- `rank_eligible`
- `execution_eligible`
- `reason_code`
- `reasons`
- `quote_source`
- `option_ltp_source`
- `source_trust`
- `quote_validation_status`
- `effective_age_sec`
- `age_reason_code`
- `context`

### `core/executable_truth.py`

Execution truth now consumes the canonical quote-truth decision and maps quote-truth reasons to existing executable-firebreak reasons:

- fallback quote source → `fallback_driven_data`
- subscription failure → `subscription_failed_quote`
- price mismatch → `price_mismatch_quote`
- stale quote → `stale_option_ltp`

The old field checks remain as compatibility support, but the canonical decision is now always present under `context["quote_truth"]`.

## Tests

`tests/test_edge42_quote_truth_contract.py` proves:

- fresh live quote is eligible
- REST fallback source is blocked
- subscription-failed source is blocked
- price mismatch is blocked
- timestamp/report-age mismatch is blocked
- executable truth consumes the canonical quote-truth payload

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge42_quote_truth_contract.py
```

## Safety

- No broker imports
- No runtime mutation
- No strategy tuning
- No dashboard work
- No threshold loosening
- No order behavior changes

This PR only adds deterministic quote-truth classification and wires existing execution evidence to consume that classification.

## Out of scope

- Feed health split-brain fix remains EDGE-43.
- Symbol-level execution safety remains EDGE-45.
- Candidate status cleanup remains EDGE-47.
- Scoring truth hardening remains EDGE-48.
- Strategy validation remains later roadmap work.
