# CE/PE Evidence Pivot: No Free Historical Bid/Ask Assumption

## Decision

TradeBot will not depend on a free historical Indian index-option bid/ask archive, and it will not fabricate one.

The research program is split into three distinct evidence lanes:

1. historical signal evidence;
2. conservative candle-proxy economics;
3. forward-captured executable quote evidence.

These lanes must never be collapsed into one verdict.

## Why this pivot exists

Broker historical endpoints provide option candles such as timestamp, OHLC, volume and open interest. They do not provide a free historical top-of-book archive suitable for reconstructing real ask-entry and bid-exit fills.

NSE distributes historical order/trade data and real-time depth as paid market-data products. No paid purchase is authorized by this decision.

Official references reviewed on 2026-07-26:

- https://upstox.com/developer/api-documentation/v3/get-historical-candle-data/
- https://upstox.com/developer/api-documentation/v3/get-market-data-feed/
- https://www.nseindia.com/static/market-data/eod-historical-data-subscription
- https://www.nseindia.com/static/market-data/real-time-data-subscription

## Lane A: Historical signal evidence

Purpose: determine whether a directional mechanism exists before execution assumptions.

Allowed inputs:

- underlying index candles;
- constituent candles when required by the mechanism;
- actual option OHLC/volume/OI candles when available;
- frozen instrument and expiry metadata.

Required mapping:

- bullish signal -> long CE candidate;
- bearish signal -> long PE candidate;
- neutral signal -> no trade.

Required controls:

- chronological train/validation/sealed-holdout split;
- purge and embargo;
- direction flip;
- delayed entry;
- matched random timestamps;
- time-of-day controls;
- parameter and threshold freeze before validation outcomes;
- deterministic pre-outcome signal ledger.

Strongest allowed verdict:

`STRUCTURAL_SIGNAL_CANDIDATE`

This lane cannot claim executable profitability.

## Lane B: Conservative candle-proxy economics

Purpose: reject obviously uneconomic mechanisms before waiting for months of forward quote capture.

Allowed fill proxy:

- actual option candle data only;
- pessimistic next-bar execution;
- explicit brokerage, taxes, fees and slippage stress;
- no fill better than observable candle bounds;
- no same-bar signal/fill coupling.

Forbidden:

- treating option LTP as ask-entry or bid-exit;
- synthesizing a historical spread and labelling it observed;
- using underlying index points as option P&L;
- selecting CE/PE, expiry or strike after seeing outcomes;
- publishing proxy results as strict option replay certification.

Strongest allowed verdict:

`CANDLE_PROXY_ECONOMICS_SURVIVED`

This remains exploratory evidence.

## Lane C: Forward-captured executable quote evidence

Purpose: establish actual CE/PE execution behaviour without buying historical order-book data.

Existing starting point:

`scripts/capture_upstox_market_daily.py`

The Upstox V3 full market-data stream supplies real-time best bid/ask depth and option Greeks. Normal subscriptions support up to 2,000 full-mode instrument keys on one category, subject to the documented combined limits.

The current collector is not yet certification authority. A certification-grade forward campaign must record and bind:

- feed-generated timestamp (`currentTs`);
- local receipt timestamp;
- last-trade timestamp (`ltpc.ltt`);
- best bid price and quantity;
- best ask price and quantity;
- instrument key;
- underlying, option type, strike and expiry from a frozen BOD master;
- subscription-mode and subscribed-key manifest;
- BOD master hash;
- file hashes and row counts;
- first/last feed timestamps;
- reconnect, parse-failure and missing-update evidence;
- crossed/locked/zero quote counts;
- per-contract quote coverage and staleness;
- market-open/closed status evidence.

Minimum milestones:

- 20 valid sessions: adapter and spread-distribution calibration only;
- 60 valid sessions: development execution calibration candidate;
- 100 valid sessions across at least six calendar months: eligible for contract/partition review;
- final certification additionally requires expiry and non-expiry representation, deterministic contract availability, strict loader acceptance, frozen partitions and an untouched holdout.

Even at 100 sessions, inventory alone does not authorize strategy development. Contract availability, expiry coverage, strict loading and chronological partition gates remain separate.

Strongest eventual verdict after untouched forward holdout:

`PASSED_FORWARD_OPTION_QUOTE_CERTIFICATION`

This is research certification, not live-trading readiness.

## Combined strategy decision

A strategy may advance while forward data accumulates only when:

- Lane A finds a stable structural signal candidate;
- Lane B survives pessimistic candle-proxy economics;
- no negative control reproduces the effect;
- thresholds remain frozen;
- the result is explicitly labelled non-executable pending Lane C.

Final CE/PE trust requires Lane C.

## Permanent prohibitions

- No fake bid/ask reconstruction.
- No midpoint fills presented as executable truth.
- No LTP-only certification.
- No option P&L derived from underlying points.
- No paid data purchase without explicit user approval.
- No promotion from signal evidence directly to live readiness.
- No reopening a sealed holdout after seeing results.

## Current status

- Historical structural research may proceed using candle data.
- Strict historical ask-entry/bid-exit certification remains unavailable without paid data.
- Forward bid/ask capture is the approved free execution-evidence path.
- PR #717 remains draft and unmerged.
