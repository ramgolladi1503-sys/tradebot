# LIVE-TRUTH-04 — Feed Runtime Writer Liveness / WebSocket Recovery Evidence

## Purpose

LIVE-TRUTH-04 adds read-only evidence for feed runtime writer liveness and recovery visibility.

The feed runtime artifact can exist while still being stale, frozen, disconnected, or missing recovery evidence after WebSocket/subscription failures. This PR proves that condition explicitly before later runtime-health and lifecycle work consumes feed truth.

## Scope

In scope:

- Evaluate feed runtime writer heartbeat freshness.
- Detect stale writer heartbeat evidence.
- Detect missing writer heartbeat evidence.
- Detect future writer heartbeat evidence.
- Detect WebSocket disconnect evidence without recovery visibility.
- Detect subscription failure evidence without recovery visibility.
- Preserve subscribed token and option-token counts in evidence.
- Emit read-only liveness evidence.

Out of scope:

- Reconnecting WebSockets.
- Refreshing feeds.
- Resubscribing tokens.
- Runtime loop wiring.
- Market-close quiescence; that belongs to LIVE-TRUTH-05.
- Candidate generation changes.
- Strategy scoring changes.
- Dashboard changes.

## Module

```text
core/live_truth_feed_runtime_writer_liveness.py
```

Main functions:

```python
build_feed_runtime_writer_liveness_report(...)
write_feed_runtime_writer_liveness_evidence(...)
```

Status values:

- `FEED_RUNTIME_WRITER_ALIVE`
- `FEED_RUNTIME_WRITER_STALE`
- `FEED_RUNTIME_RECOVERY_EVIDENCE_MISSING`
- `FEED_RUNTIME_WRITER_LIVENESS_BLOCKED`

Reason codes:

- `feed_runtime_writer_recent`
- `feed_runtime_writer_stale`
- `missing_feed_runtime_writer_heartbeat`
- `invalid_feed_runtime_snapshot`
- `invalid_feed_runtime_writer_liveness_config`
- `websocket_recovery_evidence_missing`
- `subscription_recovery_evidence_missing`
- `feed_runtime_writer_heartbeat_in_future`

## Timestamp fields

The reducer accepts common timestamp fields for writer heartbeat, WebSocket disconnect/reconnect, and subscription failure/recovery evidence.

Examples:

- `generated_epoch`
- `last_write_epoch`
- `heartbeat_epoch`
- `last_ws_disconnect_epoch`
- `last_ws_reconnect_epoch`
- `last_subscription_failure_epoch`
- `last_subscription_success_epoch`
- ISO variants such as `generated_at` and `last_ws_reconnect_at`

## Safety behavior

This PR is evidence only.

It does not reconnect feeds, subscribe tokens, refresh runtime artifacts, create candidates, score candidates, place orders, or update dashboards.

## Test proof

Focused tests cover:

- writer alive
- writer stale
- missing heartbeat
- invalid snapshot
- future heartbeat
- WebSocket recovery missing
- WebSocket recovery visible
- subscription recovery missing
- ISO timestamps
- invalid config
- evidence file writing
- JSON serialization and read-only/no-append metadata

Command:

```bash
PYTHONPATH=. python -m pytest tests/test_live_truth_04_feed_runtime_writer_liveness.py
```

## Next

After LIVE-TRUTH-04 merges green, continue to LIVE-TRUTH-05 — Market Close State Consistency / Off-Hours Quiescence.
