# Unified NIFTY Underlying Feature Warehouse V1

Final verdict: `UNDERLYING_WAREHOUSE_PARTIALLY_READY`

Selected source: `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`

The selected source contains NIFTY one-minute Upstox V3 historical-candle files covering the target option period from `2024-09-26T09:15:00+05:30` through `2026-07-21T15:29:00+05:30`.

Built local warehouses:

- canonical one-minute rows: `166251`
- canonical five-minute rows: `33245`
- causal feature rows: `166251`
- option-aligned smoke rows: `392832`
- option-aligned smoke sessions: `386`
- trusted-option joint builder rows: `395923`
- trusted-option joint builder sessions: `386`

The verdict is partial, not ready, because:

- `11` sessions have incomplete one-minute coverage.
- NIFTY index volume is zero throughout this source, so volume-derived signals are proxy-only.
- Full one-minute to five-minute reconciliation cannot pass while incomplete sessions remain.

Large parquet warehouses are local artifacts only and are intentionally not committed. The branch commits code, schemas, hashes, manifests, reports, and compact evidence.

Safety flags remained:

- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
