# Live Constituent Subscription Audit

Verdict: `BLOCKED_BY_KITE_AUTH`

This audit is read-only. The repaired bridge no longer infers a live certification universe from `snapshot_rows`, `cfg.SYMBOLS`, token lookup, sample replay manifests, or cross-broker Upstox token domains. A Kite-domain NIFTY 50 universe contract is not yet available in this worktree because the authorized read-only Kite instruments call failed closed with `BLOCKED_BY_KITE_AUTH`.

## Runtime Integration

- `core/market_data.py`
  - `fetch_live_market_data()` calls `core.market_event_graph_live_runtime_bridge.get_live_source_bridge().observe_cycle(...)` only when `MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE=true`.
  - Enabling `MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE` no longer changes production `ohlc_buffer` update timing or candidate/risk/execution inputs.
- `core/market_event_graph_live_runtime_bridge.py`
  - `LiveSourceRuntimeBridge.observe_cycle()` reads the isolated live-source shadow OHLC buffer and enforces live-universe, subscription, interval-alignment, and provenance truth before writing.
  - Default subscription evidence is read from `core.kite_depth_ws.market_event_graph_subscription_evidence_for_tokens(...)`; token lookup alone is not proof.
  - Rejections are written to a durable JSONL rejection ledger separate from accepted live-source rows. Rejection-ledger write failures do not affect runtime output.
  - `build_live_constituent_subscription_audit()` reports unresolved universe or unapplied subscription evidence without claiming success.
- `core/market_event_graph_live_source.py`
  - `validate_live_captured_metadata_row()` now checks expected identities and universe hash, not only count equality.
- `core/market_event_graph_live_ohlc_buffer.py`
  - Owns the opt-in shadow `OhlcBuffer` for live-source evidence only.
  - Repeated cached LTP polling does not advance shadow bars.
- `core/ohlc_buffer.py`
  - `update_tick(..., provenance=...)` preserves live/historical/session/generation provenance on bars.
  - `seed_bars()` marks historical seed provenance so seeded bars cannot certify live evidence.

## Universe Contract Status

- Required source: `MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH`
- Builder: `scripts/build_market_event_graph_live_universe_v1.py`
- Official source: `https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv`
- Preserved raw source: `runtime/reference/market_event_graph/official_nse/ind_nifty50list_9fb8832853c27944.csv`
- Previous Upstox-derived contract: invalidated for Kite by `runtime/reference/market_event_graph/invalid_cross_broker_token_domain/nifty50_live_universe_9fb8832853c27944.invalidated.json`
- Kite master acquisition: `scripts/acquire_kite_instrument_master_v1.py`
- Kite master status: `BLOCKED_BY_KITE_AUTH` in this run; no preserved Kite master exists in the worktree.
- Kite-domain universe contract: not produced.
- Expected future contract token domain: `kite_instrument_token`
- Official raw SHA-256: `9fb8832853c279448d2bc05f0e7dd5f460ed2ff35332fea8c40fc1250362ad28`
- Canonical universe SHA-256: `1e83284e578caaaef41d68f64ebf095d525c7073dd28d56f2a48609a80668992`
- HTTP last-modified observed: `Thu, 30 Jul 2026 03:30:53 GMT`
- Parser version: `market_event_graph_live_universe_builder_v1`
- Official rows: `50`; unique symbols: `50`; duplicates: none; required series: `EQ`
- Upstox master SHA-256, invalid for Kite: `5da2bc38bc0f54c9fccd14ad5cd6712c6b9f066766d3c621fb82330e6292fe40`
- Current crosswalk verdict: `BLOCKED_BY_KITE_AUTH`, before `BLOCKED_BY_KITE_INSTRUMENT_MASTER`
- Stable universe hash excludes runtime feed session / capture session identity; `capture_session_id` remains `null` in the contract.

## Subscription Truth Status

Token resolution is not subscription proof. A row is rejected unless the runtime subscription evidence has the exact set, no duplicates, no extras, and exact token identity match for:

- token resolved;
- subscription requested;
- subscription callback acknowledged/applied;
- mode applied;
- live tick observed.

Current status:

- subscription request succeeded status: `UNPROVEN`
- mode request succeeded status: `UNPROVEN`
- full-payload observed status: `UNPROVEN`
- completed-bar availability status: `UNPROVEN`
- live tick provenance status: `UNPROVEN`
- subscription evidence ID: unavailable without a live runtime session.

Failure reasons now distinguish missing request/full proof from broad identity failure, including `SUBSCRIPTION_REQUEST_FAILED`, `MODE_REQUEST_FAILED`, `MISSING_POST_REQUEST_TICK`, `MISSING_POST_MODE_FULL_PAYLOAD`, `FEED_SESSION_ID_MISMATCH`, and `RECONNECT_GENERATION_MISMATCH`.

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
