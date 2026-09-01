# CAS Morning-Reversal Prospective Capture Status

## Status

`CAS_MORNING_REVERSAL_PROSPECTIVE_COLLECTION_ARMED`

The operational amendment completed flat/zero-return handling and Asia/Kolkata timezone without changing the economic hypothesis. The canonical repository underlying-tick freshness authority was recovered: `LTP_SLA_SECONDS=2.0` seconds, yielding a frozen 2000 ms entry tolerance.

## Blocking fields

- Option account-specific cost authority is incomplete; this blocks option-net claims but does not block underlying capture.

No defaults were invented. No prospective session was admitted, no aggregate outcome was inspected, and the prior holdout was not reused.

## Required before arming

Read-only capture is armed for exactly 20 admitted sessions. The 20-session gate must not be raised, lowered, or stopped early. Entry admission requires an authoritative timestamp at or after 15:14:00 IST and no more than 2000 ms late.

`CAPTURE_PIPELINE_ARMED=true`

`OPTION_CAPTURE_ARMED=true` for neutral research-surface capture only; option-net execution viability remains `UNKNOWN`.

`ADMITTED_SESSION_COUNT=0`, `AGGREGATE_OUTCOME_ANALYSIS_LOCKED=true`, `OLD_HOLDOUT_REUSED=false`.

## Safety

`BROKER_WRITE_CALLS=0`, `BROKER_ORDER_CALLS=0`, `ORDERS_PLACED=0`, `ORDERS_MODIFIED=0`, `ORDERS_CANCELLED=0`.

`broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`.
