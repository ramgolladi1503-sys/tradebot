# Upstox Expired Options Recovery V1

Recovery verdict: `RECOVERED_LOCAL_EVIDENCE`

Recovered evidence root: `/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1`

The recovery pass found the prior Upstox expired-options evidence locally and independently reproduced the key prior counts:

- populated raw contracts: `1199`
- normalized 1-minute partitions: `1199`
- normalized 5-minute partitions: `1199`
- missing normalized pairs: `0`
- one-minute rows: `1998358`
- five-minute rows: `399844`
- underlying: `NIFTY`
- timestamp range: `2024-09-26T09:15:00+05:30` through `2026-07-21T15:29:00+05:30`

Trusted option certification verdict: `OPTION_DATA_READY_FOR_DISCOVERY`

The joint underlying-plus-option warehouse remains empty because the existing structural-edge underlying feature warehouse in this branch ends before the recovered option evidence begins. Next action is to build or point to a trusted NIFTY underlying feature warehouse covering `2024-09-26` through `2026-07-21`, then rerun the joint certification before discovery.

Safety flags remained:

- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
