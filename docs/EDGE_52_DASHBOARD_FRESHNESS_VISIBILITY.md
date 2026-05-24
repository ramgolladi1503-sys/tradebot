# EDGE-52 — Dashboard Freshness Visibility

## Purpose

Expose latest artifact freshness evidence through the dashboard snapshot reader.

This makes stale, missing, invalid, and fresh states available to UI callers without changing dashboard layout or runtime decision behavior in this PR.

## Implementation

Updated `dashboard/readers/snapshot_reader.py`.

`read_snapshot_payload(path)` now includes these fields for all success and failure states:

- `fresh`
- `freshness_status`
- `freshness_age_seconds`
- `freshness_timestamp_source`
- `freshness_blockers`
- `freshness`

## Compatibility

Existing fields are preserved:

- `state`
- `path`
- `errors`
- `payload`
- `generated_at`
- `producer`
- `schema_version`

## Scope Guard

Out of scope:

- no dashboard layout migration
- no Streamlit rendering changes
- no runtime decision gating
- no artifact writer changes
- no strategy changes
- no threshold changes
- no live behavior changes

## Tests

```bash
PYTHONPATH=. python -m pytest tests/test_edge52_dashboard_snapshot_freshness_visibility.py
```

The tests prove:

- fresh snapshots expose freshness fields
- stale snapshots expose stale status and blockers
- missing files expose missing freshness status
- invalid JSON exposes invalid freshness status
- existing success payload fields remain available
