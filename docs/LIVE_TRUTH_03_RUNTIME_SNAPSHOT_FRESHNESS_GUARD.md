# LIVE-TRUTH-03 — Runtime Snapshot Freshness Guard

## Purpose

LIVE-TRUTH-03 adds read-only evidence for runtime snapshot freshness.

A latest artifact is not automatically trustworthy just because it exists. If `feed_runtime`, `market_snapshot`, `top_opportunities`, or runtime health evidence is old, later lifecycle and promotion logic can consume stale truth.

This PR adds a deterministic freshness reducer before any later runtime-health or lifecycle governance consumes those artifacts.

## Scope

In scope:

- Evaluate runtime snapshots by artifact name.
- Accept numeric epoch timestamps.
- Accept ISO timestamp strings.
- Detect missing timestamps.
- Detect stale timestamps by max-age threshold.
- Detect future timestamps beyond tolerance.
- Support per-artifact max-age overrides.
- Emit read-only freshness evidence.

Out of scope:

- Refreshing feeds.
- Reconnecting WebSockets.
- Runtime loop wiring.
- Market-close quiescence; that belongs to LIVE-TRUTH-05.
- Candidate generation changes.
- Strategy scoring changes.
- Dashboard changes.

## Module

```text
core/live_truth_runtime_snapshot_freshness.py
```

Main functions:

```python
build_runtime_snapshot_freshness_report(...)
write_runtime_snapshot_freshness_evidence(...)
```

Status values:

- `RUNTIME_SNAPSHOT_FRESH`
- `RUNTIME_SNAPSHOT_STALE`
- `RUNTIME_SNAPSHOT_FRESHNESS_BLOCKED`

Reason codes:

- `ok`
- `no_runtime_snapshots`
- `invalid_runtime_snapshot`
- `missing_runtime_snapshot_timestamp`
- `runtime_snapshot_timestamp_in_future`
- `runtime_snapshot_stale`
- `invalid_freshness_config`

## Timestamp fields

The reducer accepts common timestamp field names, including:

- `generated_epoch`
- `updated_epoch`
- `last_update_epoch`
- `timestamp_epoch`
- `generated_at`
- `updated_at`
- `timestamp`
- `ts`

## Safety behavior

This PR is evidence only.

It does not refresh any snapshot, reconnect feeds, change market state, create candidates, score candidates, place orders, or update dashboards.

## Test proof

Focused tests cover:

- all snapshots fresh
- one snapshot stale
- missing timestamp blocking
- invalid snapshot blocking
- future timestamp blocking
- ISO timestamp parsing
- per-artifact max-age override
- empty snapshot input blocking
- invalid freshness config blocking
- evidence file writing
- JSON serialization and read-only/no-append metadata

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_live_truth_03_runtime_snapshot_freshness.py
```

## Next

After LIVE-TRUTH-03 merges green, continue to LIVE-TRUTH-04 — Feed Runtime Writer Liveness / WebSocket Recovery Evidence.
