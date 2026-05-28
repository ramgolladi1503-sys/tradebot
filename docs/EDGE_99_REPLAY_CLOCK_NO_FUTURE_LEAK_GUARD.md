# EDGE-99 — Replay Clock and No-Future-Leak Guard

## Purpose

EDGE-99 adds a read-only replay-time authority for backtest and replay work. The guard exposes only data that is available at the current replay timestamp and blocks access to future snapshots, incomplete candle derived fields, and full-session aggregates before the session is complete.

## Scope

Implemented in `core/backtest_replay_clock.py`:

- Configured session start and end validation.
- UTC-normalized replay timestamp handling.
- Monotonic replay clock advancement.
- Snapshot visibility decisions based on current replay timestamp.
- Configurable lookback policy for past snapshot access.
- Future candle high/low/close rejection until the candle is complete.
- Full-session aggregate blocking before session end.
- Monotonic replay data validation for historical timestamp sequences.
- Read-only decision payloads with explicit non-action markers.

## Contract

The replay clock is intentionally strict:

- Session end must be after session start.
- All timestamps must be timezone-aware.
- Current timestamp must stay inside the configured session.
- Clock advancement cannot move backward.
- Requested snapshots later than current replay time are blocked.
- Requested snapshots older than the configured lookback are blocked.
- Candle fields that require the full candle (`high`, `low`, `close`, `hlc3`, `ohlc4`) are blocked until the candle end is visible.
- Full-session aggregates are blocked until `current_timestamp >= session_end`.
- Non-monotonic replay timestamp sequences fail closed.

## Non-Action Guarantees

`ReplayAccessDecision.to_payload()` includes:

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_action=false`
- `broker_order_action=false`

This PR does not call brokers, submit orders, update the dashboard, run strategies, or write paper/live execution state.

## Failure Modes

The contract raises `ReplayClockContractError` for invalid configuration or invalid replay data. Access checks return deterministic `ALLOW` or `BLOCK` decisions with explicit reason codes, so future replay consumers can fail closed instead of silently leaking future data.

Important reason codes include:

- `NON_MONOTONIC_ADVANCE`
- `SNAPSHOT_IN_FUTURE`
- `LOOKBACK_EXCEEDED`
- `CANDLE_FIELD_IN_FUTURE`
- `FULL_SESSION_AGGREGATE_UNAVAILABLE`
- `NON_MONOTONIC_REPLAY_DATA`

## Test Evidence

Focused local command:

```bash
pytest tests/test_edge_99_replay_clock_no_future_leak.py -q
# 9 passed
```

The tests prove:

- Replay clock starts at the configured session timestamp.
- Clock advancement is monotonic.
- Same-timestamp snapshot access is allowed.
- Future snapshot access is blocked.
- Past snapshots are allowed only inside the configured lookback.
- Future candle high/low/close access is blocked until the candle is complete.
- Full-session aggregate access is blocked before session completion.
- Non-monotonic replay data fails closed.
- Snapshot filtering does not expose future data.

## Non-Goals

- No strategy execution.
- No feed adapter changes.
- No candidate runner.
- No ranking.
- No metrics.
- No broker integration.
- No dashboard/UI.
