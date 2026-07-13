# VWAP Data Contract

This document defines the strict data contract for Volume Weighted Average Price (VWAP) across the TradeBot pipeline, ensuring parity between live execution and replay mode.

## Core Principles

1. **No Silent Fallbacks**: VWAP must never silently fall back to `close` or `spot` prices when unavailable. Missing VWAP must result in explicit strategy rejection.
2. **Session Reset**: VWAP accumulates from zero volume at the start of each trading session. Prior day data does not carry over.
3. **Single Source of Truth**: Both live and replay modes must use the same `SessionVwapAccumulator` logic to accumulate typical price and volume.

## Normalized Snapshot Schema

The `vwap` field in the market snapshot is a structured object, not a primitive float.

```json
{
  "vwap": {
    "value": 150.25,
    "source": "LIVE_INCREMENTAL",
    "as_of": 1782969042.612,
    "session_date": "2026-07-02",
    "sample_count": 450,
    "cumulative_volume": 250000.0
  }
}
```

### Fields

- `value` (float | null): The computed VWAP value. Null if volume is zero or data is unavailable.
- `source` (str):
  - `LIVE_INCREMENTAL`: Computed from the live tick feed.
  - `REPLAY_RECONSTRUCTED`: Computed by accumulating historical ticks during replay.
  - `UNAVAILABLE`: VWAP could not be calculated (e.g., zero volume or missing data).
- `as_of` (float): The UTC epoch timestamp of the last tick that contributed to this VWAP.
- `session_date` (str): The local (IST) date string for the trading session this VWAP applies to (e.g., `YYYY-MM-DD`).
- `sample_count` (int): Number of ticks that have contributed to this session's VWAP.
- `cumulative_volume` (float): Total session volume accumulated.

## Strategy Explicit Rejections

Strategies depending on VWAP (e.g., `vwap_reclaim_rejection_v1`) must explicitly handle missing or invalid VWAP data by returning a `NO_TRADE` candidate with an appropriate suppression reason:

- `VWAP_UNAVAILABLE`: The `value` field is null.
- `VWAP_INVALID`: The `value` field is <= 0.
- `VWAP_STALE`: (Future capability) The `as_of` timestamp is too old compared to the current evaluation time.

## Live Mode Pipeline

In live mode, `insert_tick` inside `core/tick_store.py` feeds ticks directly into `get_global_vwap_accumulator(token)`. `fetch_live_market_data` polls this accumulator.

## Replay Mode Pipeline

In replay mode, `run_nifty_vertical_slice_replay.py` reconstructs the session VWAP by sequentially processing all historical ticks for the session into a localized `SessionVwapAccumulator` prior to evaluating the target event.
