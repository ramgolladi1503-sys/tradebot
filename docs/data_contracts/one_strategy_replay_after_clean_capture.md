# One-Strategy Replay After Clean Capture

## Purpose

This contract gates the progression of the trading system to ensure that strategy certification only proceeds after a pristine dataset has been captured and validated.

## Prerequisites

Before ANY strategy can be replayed for certification, the following conditions MUST be met:

1. A clean live capture dataset exists, satisfying the `Next-Day Option Tick Capture Contract`.
2. The readiness validator output is `NEXT_DAY_CAPTURE_CONTRACT_VALID`.
3. The filtered dataset quality report is valid (no date mismatches, no unknown lineage, no spread outliers).
4. Token-index lineage is strictly valid.

## Execution Rules

1. **One Strategy Only**: The very first replay after a clean capture must be for **exactly one** movement strategy.
2. **Recommended Strategy**: `VWAP_RECLAIM`
3. **No Batch Replay**: Do not run a batch replay.
4. **No UI / Ranking / Runtime**: Do not integrate the replay results into the live runtime or the UI dashboard.
5. **No Paper / Live Execution**: Do not enable paper or live trading.
6. **No Broker Orders**: Do not send broker orders.

All strategy execution safety flags must remain `false`.

