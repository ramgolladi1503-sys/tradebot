# Live Constituent Subscription Audit

Verdict: `BLOCKED_BY_AUTHORITATIVE_LIVE_UNIVERSE`

This audit is read-only. The repaired bridge no longer infers a live certification universe from `snapshot_rows`, `cfg.SYMBOLS`, token lookup, or sample replay manifests. Without a versioned authoritative live-universe contract at `MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH`, no accepted live-source row can be exported.

## Runtime Integration

- `core/market_data.py`
  - `fetch_live_market_data()` calls `core.market_event_graph_live_runtime_bridge.get_live_source_bridge().observe_cycle(...)` only when `MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE=true`.
- `core/market_event_graph_live_runtime_bridge.py`
  - `LiveSourceRuntimeBridge.observe_cycle()` enforces live-universe, subscription, interval-alignment, and provenance truth before writing.
  - `build_live_constituent_subscription_audit()` reports unresolved universe or unapplied subscription evidence without claiming success.
- `core/market_event_graph_live_source.py`
  - `validate_live_captured_metadata_row()` now checks expected identities and universe hash, not only count equality.
- `core/ohlc_buffer.py`
  - `update_tick(..., provenance=...)` preserves live/historical provenance on bars.
  - `seed_bars()` marks historical seed provenance so seeded bars cannot certify live evidence.

## Universe Contract Status

- Required source: `MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH`
- Required fields: universe name, version, effective date, index symbol/token, ordered constituents/tokens, expected count, canonical SHA-256, source provenance, capture session ID.
- Current repository/runtime status: no authoritative live NIFTY constituent contract is configured in this PR.
- Requested count: `0`
- Applied count: `0`
- Missing identities: all certification identities are unresolved until the authoritative contract is supplied.
- Evidence source: code inspection and local tests only.

## Subscription Truth Status

Token resolution is not subscription proof. A row is rejected unless the runtime subscription evidence has the exact ordered set for:

- token resolved;
- subscription requested;
- subscription callback acknowledged/applied;
- mode applied;
- live tick observed.

Current status:

- callback-applied status: `UNPROVEN`
- mode-applied status: `UNPROVEN`
- completed-bar availability status: `UNPROVEN`
- live tick provenance status: `UNPROVEN`
- subscription evidence ID: unavailable without a live runtime session.

Failure reason when token resolution exists but callback/mode/tick proof is missing: `BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION`.

## Interval And Provenance Truth

Accepted rows must use the completed source interval end as `interval_end` and `source_bar_end_epoch`. Observation time remains separate as `observed_at_epoch` / `ts_epoch`. The index bar and every constituent bar must share the same source interval boundary.

Accepted bars must prove:

- source type is `live_websocket` or `tick_store_live`;
- live feed session ID is present;
- first and last contributing live tick timestamps are present;
- not historical seed;
- not replay;
- not non-live fallback;
- not recovered synthetic data.

Failure reason when this is missing: `LIVE_BAR_PROVENANCE_UNPROVEN`.

## Safety Boundary

- read_only=true
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false
- normal runtime continues when evidence capture rejects or writer fails.

Stage A remains `INSUFFICIENT_LIVE_BREADTH_EVIDENCE`. Stage B remains `PASS_GRAPH_FORWARD_SHADOW_CORRECTNESS`.
