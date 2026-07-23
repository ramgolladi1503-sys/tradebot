# Constituent Lead–Lag Catch-Up V1

## Status

Research only. Not registered as a production strategy and not eligible for live execution.

The package now contains two distinct lanes:

1. **Weighted constituent lead–lag** — remains blocked until authoritative point-in-time constituent weights are available.
2. **Unweighted constituent-breadth lead–lag** — implemented for immediate research using an explicit point-in-time constituent universe and aligned index/constituent five-minute OHLCV.

Neither lane has a profitability or edge verdict yet.

## Why this exists

The previous 30-minute campaigns repeatedly transformed NIFTY and BANKNIFTY index candles. These hypotheses introduce a genuinely different information source: movement across the individual index constituents.

## Shared causal contract

At a completed five-minute cutoff between 10:00 and 14:15:

- calculate constituent returns over five and ten minutes;
- compare the constituent basket with the corresponding index;
- standardize the lead gap using the previous 20 sessions at the same decision time;
- require broad participation, breadth and limited dispersion;
- enter the index at the next five-minute bar only when constituents have moved materially more than the index.

Long and short rules are symmetric.

Shared frozen thresholds:

- lead-gap z-score: 2.0;
- participation: 70%;
- breadth magnitude: 40%;
- catch-up ratio: at most 0.60;
- dispersion: no higher than historical 80th percentile;
- range consumed: at most 0.60;
- constituent availability: at least 80%;
- minimum history: 20 completed prior sessions;
- maximum hold: 20 minutes;
- stop: 0.35 times prior rolling median absolute 30-minute index move;
- reward/risk: 1.5;
- assumed underlying round-trip sensitivity: 5 bps.

## Required five-minute bars

`timestamp, session, symbol, open, high, low, close`

The file must contain the index and its constituents with aligned, causal timestamps.

## Lane A — weighted basket

Required point-in-time weights:

`index_symbol, constituent_symbol, effective_from, effective_to, weight`

Current constituent lists and weights must never be backfilled into older dates. Missing historical weights remain a hard blocker for this lane.

Run:

```bash
python scripts/run_constituent_lead_lag_research.py \
  --bars /absolute/path/constituent_5m.parquet \
  --weights /absolute/path/point_in_time_weights.csv \
  --index NIFTY \
  --output /absolute/path/weighted-evidence
```

Without both authoritative inputs, the weighted runner exits with:

```text
NEED_AUTHORITATIVE_CONSTITUENT_DATA
```

## Lane B — unweighted constituent breadth

This lane assigns equal influence to each available constituent and calculates:

- equal-weight five- and ten-minute basket returns;
- median constituent returns;
- percentage participation in the basket direction;
- signed breadth;
- cross-sectional dispersion;
- the equal-weight basket/index lead gap.

It still requires point-in-time constituent membership. A current official snapshot is valid only from its effective date forward and cannot be backfilled historically.

Required universe schema:

`index_symbol, constituent_symbol, effective_from, effective_to`

Build a dated universe snapshot from an official constituent file:

```bash
python scripts/build_constituent_universe_snapshot.py \
  --input /absolute/path/official_nse_constituents.csv \
  --index NIFTY \
  --effective-from YYYY-MM-DD \
  --snapshot-type CURRENT_OFFICIAL_SNAPSHOT \
  --output /absolute/path/nifty_universe.csv
```

Run the unweighted lane:

```bash
python scripts/run_unweighted_constituent_breadth_research.py \
  --bars /absolute/path/constituent_5m.parquet \
  --universe /absolute/path/nifty_universe.csv \
  --index NIFTY \
  --output /absolute/path/unweighted-evidence
```

Readiness statuses:

```text
INSUFFICIENT_HISTORY_FOR_SIGNAL_GENERATION
PRELIMINARY_UNWEIGHTED_RESEARCH_ONLY
UNWEIGHTED_BREADTH_RESEARCH_COMPLETE
```

At least 21 eligible sessions are needed for the first post-warm-up decision. At least 120 completed sessions and 100 post-warm-up sessions are required before the runner marks the dataset ready for historical evaluation.

## Authoritative-source position

NSE publishes current constituent lists and describes NIFTY 50 as free-float-market-cap weighted. Historical constituent names, identifiers, market capitalization, weights and prices are offered through NSE Indices data products. The public repository currently has no authoritative point-in-time constituent-weight history, so the weighted lane has no historical edge verdict.

The unweighted lane avoids the weight requirement but does not avoid point-in-time membership and survivorship-bias controls.

## Acceptance gate

Do not promote either lane unless:

- at least 150 independent signals;
- positive combined chronological mean and median after costs;
- positive in at least four of five chronological folds;
- one-bar delayed entry remains positive;
- a matched-control lift is positive;
- no month contributes more than 25%;
- no five sessions contribute more than 30%;
- NIFTY and BANKNIFTY results are reported separately;
- real option bid/ask replay remains positive.

## Explicit non-claims

This package does not prove profitability, does not call a broker, does not place orders, and does not alter production TradeBot behavior.
