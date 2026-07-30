# Live Constituent Subscription Audit

This audit is code-based and read-only. It documents the runtime bridge added in this PR and the current evidence boundary. It does not claim live subscription truth that the process has not observed.

## Exact files and functions

- `core/market_data.py`
  - `fetch_live_market_data()`: opt-in bridge hook added at the end of the live data cycle.
- `core/market_event_graph_live_runtime_bridge.py`
  - `LiveSourceRuntimeBridge.observe_cycle()`
  - `LiveSourceRuntimeBridge._assemble_snapshot()`
  - `build_live_constituent_subscription_audit()`
  - `flush_live_source_bridge()`
  - `get_live_source_bridge()`
- `core/market_event_graph_live_source.py`
  - `LiveCapturedMetadataExporter`
  - `build_live_captured_metadata_row()`
  - `validate_live_captured_metadata_row()`
- `core/kite_depth_ws.py`
  - `_begin_option_feed_verification()`
  - `_option_feed_verification_overlay_payload()`
  - `_tick_option_feed_verification()`

## Exact runtime integration point

- `fetch_live_market_data()` now performs an opt-in call to `get_live_source_bridge().observe_cycle(...)` after the symbol loop completes.
- The bridge is disabled by default through `MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE=false`.
- The bridge is advisory only and does not affect market-data return values, strategy decisions, execution, or risk.

## Exact universe identities

- Index symbol source: `MARKET_EVENT_GRAPH_LIVE_SOURCE_INDEX_SYMBOL` default `NIFTY`
- Constituent symbol source:
  - `MARKET_EVENT_GRAPH_LIVE_SOURCE_CONSTITUENT_SYMBOLS` when explicitly configured
  - otherwise `cfg.SYMBOLS` excluding the index symbol

## Exact instrument tokens

- Token identity is resolved via `core.market_data.get_token_for_symbol()`.
- The bridge records token presence in `subscription_evidence.token_by_symbol`.
- The current static audit cannot prove live acceptance or callback application without runtime execution.

## Requested, accepted, rejected

- Requested count: computed from index symbol plus resolved constituent symbols.
- Accepted count: symbol/token pairs whose tokens resolve non-null.
- Rejected count: symbols whose tokens do not resolve.

## Callback-applied status

- Current status: `UNPROVEN_IN_STATIC_AUDIT`
- Evidence source: the repository does not yet contain a live execution log for the new bridge path.

## Mode-applied status

- Current status: `UNPROVEN_IN_STATIC_AUDIT`
- Evidence source: the bridge is opt-in and mode-gated by config only.

## Completed-bar availability status

- Current status: `UNPROVEN_IN_STATIC_AUDIT`
- Evidence source: the bridge queries `ohlc_buffer.get_completed_bars(symbol, as_of=cycle_cutoff)` and rejects incomplete or misaligned snapshots, but no live session has been captured through the path yet.

## Evidence source for every conclusion

- Code inspection of the files listed above.
- Existing partial-session artifacts under `research/market_event_graph_live_shadow_v1/live_20260730_partial_103840_ist/` show Stage A remained `INSUFFICIENT_LIVE_BREADTH_EVIDENCE` before the bridge existed.
- No live capture file was observed in the runtime path at the time of this audit.

## Operational note

The bridge is intentionally fail-closed for evidence capture. If it cannot assemble a complete synchronized snapshot, it exports nothing and leaves the primary runtime unchanged.

