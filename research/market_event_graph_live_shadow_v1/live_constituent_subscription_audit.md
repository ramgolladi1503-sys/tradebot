# Live Constituent Subscription Audit

Verdict: `BLOCKED_BY_LIVE_CONSTITUENT_SUBSCRIPTION`

This audit is read-only. The repaired bridge no longer infers a live certification universe from `snapshot_rows`, `cfg.SYMBOLS`, token lookup, or sample replay manifests. A versioned authoritative NIFTY 50 universe contract is available, but no accepted live-source row can be exported until the real feed lifecycle proves requested, callback-applied, full-mode-applied, and live-tick-observed identities for the exact universe.

## Runtime Integration

- `core/market_data.py`
  - `fetch_live_market_data()` calls `core.market_event_graph_live_runtime_bridge.get_live_source_bridge().observe_cycle(...)` only when `MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE=true`.
- `core/market_event_graph_live_runtime_bridge.py`
  - `LiveSourceRuntimeBridge.observe_cycle()` enforces live-universe, subscription, interval-alignment, and provenance truth before writing.
  - Default subscription evidence is read from `core.kite_depth_ws.market_event_graph_subscription_evidence_for_tokens(...)`; token lookup alone is not proof.
  - Rejections are written to a durable JSONL rejection ledger separate from accepted live-source rows. Rejection-ledger write failures do not affect runtime output.
  - `build_live_constituent_subscription_audit()` reports unresolved universe or unapplied subscription evidence without claiming success.
- `core/market_event_graph_live_source.py`
  - `validate_live_captured_metadata_row()` now checks expected identities and universe hash, not only count equality.
- `core/ohlc_buffer.py`
  - `update_tick(..., provenance=...)` preserves live/historical provenance on bars.
  - `seed_bars()` marks historical seed provenance so seeded bars cannot certify live evidence.

## Universe Contract Status

- Required source: `MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH`
- Builder: `scripts/build_market_event_graph_live_universe_v1.py`
- Official source: `https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv`
- Preserved raw source: `runtime/reference/market_event_graph/official_nse/ind_nifty50list_9fb8832853c27944.csv`
- Universe contract: `runtime/reference/market_event_graph/nifty50_live_universe_9fb8832853c27944.json`
- Reconciliation report: `runtime/reference/market_event_graph/nifty50_live_universe_reconciliation_9fb8832853c27944.json`
- Official raw SHA-256: `9fb8832853c279448d2bc05f0e7dd5f460ed2ff35332fea8c40fc1250362ad28`
- Canonical universe SHA-256: `1e83284e578caaaef41d68f64ebf095d525c7073dd28d56f2a48609a80668992`
- HTTP last-modified observed: `Thu, 30 Jul 2026 03:30:53 GMT`
- Parser version: `market_event_graph_live_universe_builder_v1`
- Official rows: `50`; unique symbols: `50`; duplicates: none; required series: `EQ`
- Broker master used for offline crosswalk: `runtime/upstox_instruments/complete.json`
- Broker master SHA-256: `5da2bc38bc0f54c9fccd14ad5cd6712c6b9f066766d3c621fb82330e6292fe40`
- Crosswalk verdict: `PASS_AUTHORITATIVE_LIVE_UNIVERSE_MAPPING`
- Stable universe hash excludes runtime feed session / capture session identity; `capture_session_id` remains `null` in the contract.

## Subscription Truth Status

Token resolution is not subscription proof. A row is rejected unless the runtime subscription evidence has the exact set, no duplicates, no extras, and exact token identity match for:

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
