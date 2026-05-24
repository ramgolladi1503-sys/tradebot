# EDGE-50 — Latest Artifact Freshness Guard

## Purpose

Add a read-only guard that classifies latest runtime/report artifacts as fresh, stale, missing, invalid, future-timestamped, or missing timestamp evidence.

The goal is to prevent the system from trusting old `latest` files as if they represent current runtime truth.

## Implementation

Added `core/latest_artifact_freshness_guard.py`.

The contract exposes:

- `LatestArtifactFreshnessDecision`
- `LatestArtifactFreshnessReport`
- `assess_latest_artifact_freshness(...)`
- `assess_latest_artifacts_freshness(...)`

## Freshness Rules

A latest artifact is fresh only when:

- the payload exists or the path loads as a JSON object
- a supported timestamp is present
- timestamp age is within `max_age_seconds`
- timestamp is not too far in the future

Supported timestamp fields:

- `generated_epoch`
- `updated_epoch`
- `created_epoch`
- `timestamp_epoch`
- `epoch`
- matching fields under `metadata`

## Failure Statuses

- `missing`: payload/path missing or file path missing
- `invalid`: JSON unreadable or non-object JSON
- `unknown_timestamp`: payload exists but no timestamp is present
- `future_timestamp`: timestamp is beyond allowed future tolerance
- `stale`: artifact age exceeds the configured max age

## Scope Guard

Out of scope:

- no runtime wiring
- no dashboard wiring
- no artifact writer changes
- no strategy changes
- no broker integration changes
- no live runtime behavior changes
- no order placement or order intent

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge50_latest_artifact_freshness_guard.py
```

The tests prove:

- fresh artifact detection
- stale artifact detection
- missing payload/path detection
- missing file detection
- invalid JSON-object detection
- missing timestamp detection
- future timestamp detection
- nested metadata timestamp support
- batch report aggregation
- explicit non-action safety fields
