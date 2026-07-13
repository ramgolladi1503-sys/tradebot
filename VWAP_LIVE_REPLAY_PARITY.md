# VWAP Live vs. Replay Parity

This document provides proof of parity between Live execution and Replay modes for VWAP calculation and Strategy execution.

## Architectural Goal

Previously, Replay mode was manually constructing market snapshots which caused the VWAP strategy to use silent fallbacks (`candle close` instead of true VWAP) without raising any red flags during Replay. This gap meant we could not rely on Replay mode as authoritative proof of Live behaviour.

By removing the silent fallback and making VWAP an explicit dependency calculated identically in both modes, parity is now enforced by architecture rather than convention.

## How Parity is Achieved

### The Accumulator (`SessionVwapAccumulator`)

A single Python class (`core/vwap_accumulator.py`) is used by both pipelines to calculate the Session VWAP:

1. **State**: Maintains running totals of typical price * volume (`_cumulative_price_volume`) and `_cumulative_volume`.
2. **Session Resets**: Automatically drops accumulated state if a tick's timestamp crosses over to a new trading session.
3. **Delta Volume**: Interprets cumulative session volume updates by taking the difference against the previous cumulative volume.

### Live Mode Path

1. Live websocket stream (`core/kite_depth_ws.py`) invokes `insert_tick` for every tick.
2. `insert_tick` (`core/tick_store.py`) retrieves a global token-keyed accumulator: `get_global_vwap_accumulator(token)`.
3. The tick's timestamp, ltp, and cumulative volume are fed into the accumulator.
4. When `fetch_live_market_data` polls for a market snapshot, it retrieves the current VWAP state.

### Replay Mode Path

1. Replay script (`scripts/run_nifty_vertical_slice_replay.py`) is given an event ID or row index to process.
2. The script processes the raw historical feed sequentially from the beginning of the file up to the target event.
3. Each historical tick is passed into a local `SessionVwapAccumulator`, rebuilding the exact same sequence of state mutations that occurred in live mode.
4. The strategy context is evaluated with the fully reconstructed VWAP state.

## Parity Proof Checklist

- **Same Class**: Both live and replay use `SessionVwapAccumulator`.
- **Same Inputs**: Both modes feed `(timestamp, ltp, cumulative_volume)` from the raw tick.
- **Same Rejection Logic**: The strategy `vwap_reclaim_rejection_v1` strictly checks for VWAP validity. If VWAP is missing or invalid in either mode, an explicit `NO_TRADE` candidate with reason `VWAP_UNAVAILABLE` or `VWAP_INVALID` is emitted.

This guarantees that a candidate produced in Replay Mode for a particular historical event *exactly* mirrors what Live Mode would have produced at that same millisecond, provided both had ingested the same ticks.
