# Reversal Trap Probability Bands — Public NIFTY Proxy Result V1

## Verdict

`PRELIMINARY_NO_STRUCTURAL_EDGE`

This is a preliminary falsification result using a third-party public NIFTY 50 one-minute dataset. It is not broker-data certification and does not authorize paper or live integration.

The repository-native workflow remains `DATA_BLOCKED` because the GitHub checkout contains no usable multi-session OHLC corpus.

## Public proxy corpus

- Source: `sandeepkapri/Nifty50-Minute-Data`
- Source file: `nifty50_candlestick_data.csv`
- Source SHA-256: `9b347479bb242e8cea8f85011a4d53e8938c1bfea1697fa25d8ef25d8888784d`
- Initial rows: 852,087
- Valid retained rows: 851,076
- Eligible sessions: 2,270
- Retained range: 2015-01-09 09:15 through 2024-03-26 15:29
- Three short/incomplete sessions were excluded because they contained fewer than 300 one-minute bars.

## Canonical mechanism

- EMA basis: 55
- ATR length: 14
- Assumed envelope: basis ± 2 ATR
- Maximum excursion-to-re-entry window: 10 bars
- Entry: immediate next-bar open
- Target: signal-time EMA basis, frozen before entry
- Stop: two-bar extreme plus/minus one ATR
- Maximum hold: 30 minutes
- Same-bar stop and target: stop assumed first
- Cost stress: 5 basis points per completed trade
- Chronological split: 60% train, 20% validation, 20% test by session

The complete Pine source and exact default multiplier were not available through the TradingView page parser, so this is a mechanism replication rather than a byte-for-byte port.

## Canonical one-minute result

| Split | Trades | Gross expectancy | Net expectancy after 5 bps |
|---|---:|---:|---:|
| Train | 18,033 | -0.1995 bps | -5.1995 bps |
| Validation | 6,058 | +0.0190 bps | -4.9810 bps |
| Test | 5,765 | -0.1372 bps | -5.1372 bps |

Additional untouched test metrics:

- 95% session-bootstrap expectancy interval: `[-5.3158, -4.9402]` bps
- Net win rate: `27.34%`
- Profit factor: `0.1167`
- Long trades: 2,772
- Short trades: 2,993
- Direct outside-band fade test expectancy: `-4.9792` bps
- Trap uplift over direct fading: `-0.1581` bps

The trap sequence was slightly worse than direct band fading. More importantly, gross test expectancy was already negative before transaction costs.

## Timeframe robustness

| Timeframe | Test trades | Net test expectancy | 95% session-bootstrap interval |
|---|---:|---:|---:|
| 1 minute | 5,765 | -5.1372 bps | [-5.3158, -4.9402] |
| 3 minutes | 1,951 | -5.2838 bps | [-5.6149, -4.6065] |
| 5 minutes | 1,190 | -5.4959 bps | [-5.8427, -4.1074] |
| 15 minutes | 435 | -5.9521 bps | [-7.1671, -3.9259] |

All four timeframes failed.

## Neighbouring-parameter robustness

Eighteen fixed neighbouring combinations were tested:

- EMA: 34, 55, 89
- Envelope multiplier: 1.5, 2.0, 2.5
- Re-entry window: 5, 10 bars

All 18 combinations produced negative test expectancy after costs. Net test expectancy ranged from approximately `-5.0249` to `-5.1887` bps. Because five basis points were subtracted uniformly, every combination also had negative gross test expectancy, ranging from approximately `-0.0249` to `-0.1887` bps.

## RSI probability audit

The RSI bucket probabilities were fitted only on the training split with Laplace smoothing and evaluated on the untouched test split.

For the canonical one-minute model:

- Bucket-model Brier score: `0.1995272`
- Constant train-base-rate Brier score: `0.1995000`
- Improvement: `-0.0000273`

The RSI buckets added no out-of-sample probability information. The same conclusion held at 3-, 5-, and 15-minute timeframes.

## Fixed causal refinements

Only a small predeclared family was checked to avoid parameter fishing:

- Flat EMA regime
- Strong re-entry toward the basis
- Core trading hours
- Flat plus strong re-entry
- Flat plus strong re-entry during core hours

Every refinement remained negative on the untouched test split. The best-looking validation subgroup did not persist into test.

Long and short traps were both negative in test before costs. Test-period gross expectancy was also negative in 2022 and 2023 and effectively zero in 2024.

## Decision

Do not integrate this indicator into TradeBot as a strategy or ranking signal.

The published sequence—volatility-band excursion, re-entry, and mean-reversion target—does not demonstrate incremental forecasting information in this proxy study. The displayed RSI percentage also failed as an out-of-sample probability model.

A broker-certified rerun can confirm the rejection, but the current evidence does not justify more parameter search around this family.

## Limitations

- Third-party public index data; source-provider provenance is not independently certified.
- Underlying-index bars, not actual option premium or executable bid/ask data.
- Five-basis-point underlying cost stress is a proxy, not an option-chain fill model.
- Exact Pine implementation and exact default envelope multiplier were unavailable.
- Results do not cover constituent breadth, option IV, order-book pressure, or market-event context.

These limitations prevent production certification. They do not rescue the basic result, because the canonical mechanism and all eighteen neighbours were already negative before costs on the untouched test period.
