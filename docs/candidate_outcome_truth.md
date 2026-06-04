# Candidate Outcome Truth Contract

This is a pure, deterministic, read-only contract that derives what happened after a candidate signal using synthetic price observations.

## Purpose

The contract creates a foundation for future edge validation by turning candidate inputs plus offline observations into a reproducible outcome truth record.

This PR does **not** prove trading edge.
It does **not** wire into runtime.
It does **not** read or write live artifacts.

## Closed-environment scope

- Offline only
- Deterministic fixtures only
- No live market data
- No websocket/session dependency
- No broker API dependency
- No runtime writes

## What the contract derives

- Outcome status
- Outcome reason
- Target / stop / timeout flags
- First hit epoch
- MFE / MAE
- Gross R
- Estimated-cost R
- Cost-adjusted R
- Observation counts
- Blocks and warnings

## Supported outcome statuses

- `TARGET_HIT`
- `STOP_HIT`
- `TIMEOUT`
- `NO_OBSERVATIONS`
- `INVALID_INPUT`
- `NOT_EXECUTABLE`
- `AMBIGUOUS_SAME_BAR`

## BUY / LONG rules

- Target hit when `ltp >= target_price`
- Stop hit when `ltp <= stop_loss_price`
- Only observations with `observed_epoch >= signal_epoch` count
- Observations before `signal_epoch` are ignored
- If both target and stop are hit on the same observation timestamp, the contract returns `AMBIGUOUS_SAME_BAR`
- If neither target nor stop is hit by timeout, the contract returns `TIMEOUT`
- `mfe_abs = max(observed_ltp) - entry_price`
- `mae_abs = entry_price - min(observed_ltp)`
- `gross_r` is derived deterministically from the realized path

## Read-only safety flags

Every returned truth object remains safe and non-actionable:

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `live_order_action=false`
- `broker_order_action=false`

## Non-goals

- No strategy changes
- No ranking/scoring changes
- No Phase2 changes
- No broker/order changes
- No websocket or runtime behavior changes
- No FeedTruth behavior changes
- No edge claim or profitability claim

## Future consumers

Future PRs may consume this contract for offline replay, candidate validation, or edge auditing, but only after they add their own deterministic tests and keep the runtime boundary intact.

