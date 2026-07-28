# Four-Session Upstox Refetch Final Certification V1

Final verdict: `REPAIR_FAILED`

The task authorized read-only Upstox historical-candle retrieval for exactly four NIFTY sessions:

- `2024-12-12`, missing `09:42`
- `2025-03-25`, missing `10:42`
- `2025-04-04`, missing `11:57`
- `2025-04-23`, missing `10:36`

The pre-refetch defect state was independently reverified from the existing source files. Four authenticated read-only historical-candle responses were recorded for the authorized sessions. Each response returned HTTP 200 with 374 one-minute rows from `09:15` through `15:29`, but each still omitted the specific required missing timestamp.

Overlap comparison found 374 matching timestamps per session and zero OHLC mismatches, so the refetch did not create a data-divergence blocker. No patch was applied because the required bars were absent from the authorized provider responses.

Safety state:

- `read_only=true`
- `is_order_action=false`
- `broker_api_called=true`
- `broker_api_scope=historical_market_data_only`
- `allowed_for_live_execution=false`

Exact next action: manual data-provider review is required for the four missing one-minute bars. Do not broaden discovery or promote the warehouse from this evidence package.
