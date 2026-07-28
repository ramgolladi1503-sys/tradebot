# Repair 11 NIFTY Sessions V1

Final repair verdict: `REPAIR_REQUIRES_AUTHORIZED_REFETCH`

Seven of the eleven sessions were resolved locally without touching the original runtime data:

- `2024-11-01`: accepted as special evening session, 60 rows.
- `2025-10-21`: accepted as special session, 60 rows.
- `2025-04-25`, `2025-04-30`, `2025-05-08`, `2025-05-13`, `2025-05-21`: repaired by excluding out-of-regular-session rows at `15:39` and `15:59`.

Four sessions still require authorized read-only Upstox historical refetch because no complete local NIFTY one-minute replacement was found:

- `2024-12-12`, missing `09:42`
- `2025-03-25`, missing `10:42`
- `2025-04-04`, missing `11:57`
- `2025-04-23`, missing `10:36`

No API calls were made because `UPSTOX_ACCESS_TOKEN` was not present in the process. No credentials were modified.

Rebuilt repaired-scope counts:

- canonical one-minute rows: `164745`
- canonical five-minute rows: `32949`
- causal feature rows: `164745`
- option alignment rows: `392006`
- option alignment sessions: `382`
- trusted option joint rows: `392006`
- trusted option joint sessions: `382`

Safety flags remained:

- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
