# Market Event Graph Live Source Discovery

Captured at: 2026-07-30
PR: #748
Worktree: `/Users/madhuram/tradebot-market-event-graph-live-shadow-v1`

## Verdict

Case B was implemented. No existing repository component was found that writes the exact JSONL contract consumed by `scripts/run_market_event_graph_live_shadow_v1.py`.

The smallest truthful bridge is `core.market_event_graph_live_source.LiveCapturedMetadataExporter`. It is a read-only append-only serializer for already-completed live interval metadata. It does not fetch market data, subscribe to feeds, call brokers, place orders, compute outcomes, or alter strategy/feed output.

## Discovered Runtime Boundary

`core.market_data.fetch_live_market_data()` is the live market-data construction boundary used by the runtime loop.

Call path:

1. `main.py` creates `core.orchestrator.Orchestrator`.
2. `core.orchestrator.Orchestrator.live_monitoring()` delegates into the live loop.
3. The loop calls `core.market_data.fetch_live_market_data()`.
4. `fetch_live_market_data()` updates `core.ohlc_buffer.ohlc_buffer` from live LTP/tick-store inputs.
5. `fetch_live_market_data()` calls `ohlc_buffer.get_completed_bars(symbol, as_of=cycle_cutoff)`.
6. `Orchestrator._build_cycle_market_data()` canonicalizes the returned market-data list for downstream advisory decisions.

Evidence:

- `core/orchestrator.py`: imports `fetch_live_market_data`; live loop calls it before `_build_cycle_market_data`.
- `core/market_data.py`: `fetch_live_market_data()` defines `cycle_cutoff`, calls `ohlc_buffer.update_tick()`, then reads `ohlc_buffer.get_completed_bars(symbol, as_of=cycle_cutoff)`.
- `core/ohlc_buffer.py`: `get_completed_bars()` returns only bars where `bar["ts"] + interval <= as_of`.

## Missing Source

The live runtime has completed bars for configured symbols, but no proven component currently assembles a full completed NIFTY constituent universe with:

- completed NIFTY index bar;
- completed constituent bars or constituent returns;
- expected universe identities;
- missing/stale/duplicate/misaligned/late constituent identities;
- frozen Market Event Graph provenance;
- append-only raw JSONL compatible with the Stage A/B harness.

Search evidence:

- Exact contract fields such as `completed_constituent_bars`, `constituent_ret1`, `expected_constituents`, `missing_constituents`, `stale_constituents`, `duplicate_constituents`, `misaligned_constituents`, and `late_constituents` appear in the Market Event Graph harness, producer, runtime observer, and tests.
- No non-test live writer was found that emits the required `completed_constituent_bars` JSONL input.

## Implemented Bridge

`core.market_event_graph_live_source` now provides:

- `build_live_captured_metadata_row(...)`;
- `LiveCapturedMetadataExporter.export_row(...)`;
- `validate_live_captured_metadata_row(...)`;
- `load_validated_live_jsonl(...)`;
- `independent_raw_jsonl_audit(...)`.

The bridge must be called by the earliest future runtime boundary that already has the full completed constituent snapshot. It rejects partial bars, future source timestamps, duplicate intervals, incomplete universes, unsafe authority flags, missing frozen provenance, non-live source kinds, and replay fixtures.

## Launch Order

When a real constituent snapshot source is wired:

1. Start the runtime component that produces completed NIFTY index and constituent bars.
2. At each completed interval, call `LiveCapturedMetadataExporter` with the supplied completed snapshot.
3. Verify raw source:

   ```bash
   python scripts/audit_market_event_graph_live_source_v1.py --input runtime/market_event_graph_live_shadow/captured_metadata.jsonl --out research/market_event_graph_live_shadow_v1/live_NEXT_FULL_SESSION_YYYYMMDD/raw_live_source_audit.json
   ```

4. Run the Stage A/B harness:

   ```bash
   python scripts/run_market_event_graph_live_shadow_v1.py --input runtime/market_event_graph_live_shadow/captured_metadata.jsonl --output research/market_event_graph_live_shadow_v1/live_NEXT_FULL_SESSION_YYYYMMDD --mode LIVE --session-date YYYY-MM-DD --symbol NIFTY
   ```

## Authority

The bridge emits and enforces:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=true
```

No broker, order, risk, threshold, strategy, option economics, UI ranking, confidence scoring, capital allocation, or production eligibility path was changed.
