# LIVE-TRUTH-10 — Strategy Perf Shadow Fallback Evidence

## Purpose

LIVE-TRUTH-10 adds a read-only evidence reducer that checks whether strategy performance evidence is being trusted while it is actually backed by fallback, shadow, estimated, synthetic, or recovered performance sources.

This PR is part of live evidence stabilization. It does not promote, demote, rank, score, execute, pause, resume, or retire any strategy.

## Scope

Added:

- `core/live_truth_strategy_perf_shadow_fallback.py`
- `tests/test_live_truth_10_strategy_perf_shadow_fallback.py`

The reducer accepts strategy performance rows or common container shapes such as:

- `strategy_perf`
- `strategy_performance`
- `performance_rows`
- `perf_rows`
- `strategies`
- `rows`
- `items`

It normalizes strategy identity, sample count, and low-trust performance markers.

## Evidence contract

The reducer emits:

- schema version
- source
- status
- reason code
- all reasons
- row counts
- trusted count
- fallback, shadow fallback, estimated, and recovered counts
- corresponding rates
- low-sample shadow count
- parsed rows
- metadata
- non-action markers

The output is always read-only:

```json
{
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "live_order_action": false,
  "broker_order_action": false
}
```

## Statuses

- `STRATEGY_PERF_SHADOW_FALLBACK_TRUSTED`
- `STRATEGY_PERF_SHADOW_FALLBACK_REVIEW`
- `STRATEGY_PERF_SHADOW_FALLBACK_SHADOWED`
- `STRATEGY_PERF_SHADOW_FALLBACK_BLOCKED`

## Fail-closed / review behavior

The reducer blocks when:

- no strategy performance rows exist
- row payloads are invalid
- configuration is invalid
- no valid row remains after parsing

The reducer marks performance as shadowed when:

- fallback rate exceeds the allowed limit
- shadow fallback rate exceeds the allowed limit

The reducer marks performance for review when:

- trust fields are missing
- estimated rate exceeds the allowed limit
- recovered rate exceeds the allowed limit
- low-sample rows are using fallback, shadow, estimated, or recovered sources

## Explicit non-goals

This PR does not:

- call broker APIs
- place, modify, cancel, or exit orders
- wire into live runtime
- alter ranking or scoring
- alter strategy lifecycle state
- alter feed behavior
- alter dashboard/UI behavior
- change historical performance calculations
- promote or retire strategies

## Acceptance proof

Focused tests cover:

- trusted rows
- no rows
- invalid rows
- invalid config
- fallback rate shadowing
- shadow fallback rate shadowing
- estimated-rate review
- recovered-rate review
- missing trust-field review
- low-sample shadow review
- nested container extraction
- read-only evidence writer
- JSON-serializable payload

Run:

```bash
pytest tests/test_live_truth_10_strategy_perf_shadow_fallback.py
```

## Runtime use

This module is intentionally a pure/read-only evidence reducer. Any later runtime writer or dashboard display must be scoped in a separate PR and must preserve the same non-action contract.
