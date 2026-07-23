# Constituent Lead–Lag Catch-Up V1

## Status

Research only. Not registered as a production strategy and not eligible for live execution.

## Why this exists

The previous 30-minute campaigns repeatedly transformed NIFTY and BANKNIFTY index candles. This hypothesis introduces a genuinely different information source: point-in-time weighted returns of the index constituents.

## Frozen V1 hypothesis

At a completed five-minute cutoff between 10:00 and 14:15:

- calculate weighted constituent returns over five and ten minutes;
- compare the weighted basket with the corresponding index;
- standardize the lead gap using the previous 20 sessions at the same decision time;
- require broad participation, breadth and limited dispersion;
- enter the index at the next five-minute bar only when the basket has moved materially more than the index.

Long and short rules are symmetric.

Frozen thresholds:

- lead-gap z-score: 2.0;
- participation: 70%;
- weighted breadth magnitude: 40%;
- catch-up ratio: at most 0.60;
- dispersion: no higher than historical 80th percentile;
- range consumed: at most 0.60;
- authoritative weight coverage: at least 80%;
- maximum hold: 20 minutes;
- stop: 0.35 times prior rolling median absolute 30-minute index move;
- reward/risk: 1.5;
- assumed underlying round-trip sensitivity: 5 bps.

## Required inputs

### Five-minute bars

`timestamp, session, symbol, open, high, low, close`

The file must contain the index and its constituents with aligned, causal timestamps.

### Point-in-time weights

`index_symbol, constituent_symbol, effective_from, effective_to, weight`

Current constituent lists must never be backfilled into older dates. Missing historical weights are a hard blocker.

## Authoritative-source position

NSE publishes current constituent lists and describes NIFTY 50 as free-float-market-cap weighted. Historical constituent names, identifiers, market capitalization, weights and prices are offered through NSE Indices data products. The public repository currently has no authoritative point-in-time constituent-weight history, so no historical edge verdict is claimed.

Official references:

- NIFTY 50 index page and constituent download;
- NIFTY Bank index page and constituent download;
- NSE Indices data-subscription page for historical constituent weights.

## Run

```bash
python scripts/run_constituent_lead_lag_research.py \
  --bars /absolute/path/constituent_5m.parquet \
  --weights /absolute/path/point_in_time_weights.csv \
  --index NIFTY \
  --output /absolute/path/evidence
```

Without both authoritative inputs, the runner exits with:

```text
NEED_AUTHORITATIVE_CONSTITUENT_DATA
```

## Acceptance gate

Do not promote unless:

- at least 150 independent signals;
- positive combined chronological OOF mean and median after costs;
- positive in at least four of five folds;
- one-bar delayed entry remains positive;
- matched-control lift is positive;
- no month contributes more than 25%;
- no five sessions contribute more than 30%;
- NIFTY and BANKNIFTY results are reported separately;
- real option bid/ask replay remains positive.

## Explicit non-claims

This package does not prove profitability, does not call a broker, does not place orders, and does not alter production TradeBot behavior.
