# Dynamic Trend Overlay Edge Research V1 — Final Results

## Principal verdict

`NO_EDGE_IN_TESTED_DTO_FAMILY`

The public Dynamic Trend Overlay description was recreated semantically and causally. The exact Pine source was not copied or claimed to be reproduced.

No tested baseline or adjacent hypothesis passed the frozen development-plus-validation gates. The sealed 20% holdout was therefore never opened.

## Corpus and replay boundary

- Index: NIFTY.
- Underlying/constituent source: preserved five-minute constituent-index warehouse.
- Option source: preserved Upstox expired-option one-minute OHLCV corpus.
- Eligible option-covered sessions: 134.
- Chronological outcome-blind split: 80 development / 27 validation / 27 sealed holdout.
- Entry: one-minute option open at the completed five-minute signal timestamp.
- Exit: option close nine minutes later.
- Primary friction: 1.0% of option return.
- Severe friction: 1.5%.
- Maximum two signals per variant per session; 20-minute cooldown.
- Historical candle proxy only; no bid/ask or depth certification.

## Corrected session-reset campaign — V3

The corrected initialized and ratcheting EMA/ATR trail produced:

- 735 development option trades.
- 210 validation option trades.
- No survivor.

Notable failures:

- `DTO_REENTRY_STOCH`: +3.19% development mean, then -7.07% validation mean.
- `DTO_COMPRESSION_RELEASE`: -4.50% development mean; its +1.45% validation mean failed bootstrap and top-winner-removal controls.
- `DTO_FLIP_MTF`: -3.44% development and -22.44% validation.
- Every participation, breadth, option-lag, premium-confirmation and exhaustion-filtered branch failed.

Runner SHA-256:

`875aefba6d64b72638c2cfdcbfae705d07ddfb9a88351e6190eaa4a93ef6e84f`

## Final continuous-state campaign — V4

V4 retained only past EMA, ATR, StochRSI and trail state across session boundaries, matching the normal persistence of a chart overlay. Intraday returns, breakouts and compression windows still reset each session.

It produced:

- 1,087 development candidates; 858 replayed trades.
- 355 validation candidates; 272 replayed trades.
- No survivor.

| Variant | Development trades | Development mean | Validation trades | Validation mean | Validation PF | Passed |
|---|---:|---:|---:|---:|---:|---|
| DTO_FLIP_MTF | 40 | -1.40% | 13 | -14.80% | 0.113 | No |
| DTO_REENTRY_STOCH | 71 | -0.84% | 27 | -3.32% | 0.516 | No |
| DTO_TREND_STATE | 143 | -0.14% | 48 | -3.23% | 0.485 | No |
| DTO_PULLBACK_REACCEL | 141 | -0.62% | 46 | -2.64% | 0.520 | No |
| DTO_BREADTH_LEAD | 101 | -1.44% | 32 | -4.45% | 0.225 | No |
| DTO_COMPRESSION_RELEASE | 94 | -3.06% | 24 | +6.79% | 2.593 | No |
| DTO_OPTION_LAG | 56 | +0.36% | 14 | -5.68% | 0.001 | No |
| DTO_PREMIUM_CONFIRMATION | 80 | -3.37% | 24 | -3.51% | 0.390 | No |
| DTO_EXHAUSTION_FILTERED | 132 | -0.88% | 44 | -2.64% | 0.431 | No |

### Why compression release is not an edge

Its validation average was dominated by a few extreme winners:

- Largest trade: +133.09%.
- Mean after removing the largest trade: +1.30%.
- Mean after removing the three largest trades: -2.18%.
- Mean after removing the five largest trades: -4.17%.
- Validation bootstrap lower bound: -1.34%.
- Development mean: -3.06%.

This is winner concentration and sample instability, not repeatable expectancy.

### Why option lag is not an edge

`DTO_OPTION_LAG` was the only V4 branch with a slightly positive development mean (+0.36%), but it reversed to -5.68% in validation with a profit factor near zero. It failed immediately out of development.

Runner SHA-256:

`eea3fd88d813acd14770f74a96ddefd85f8158d3d1dc4d5b251b6e0d787a0317`

## Decision

Do not register or integrate Dynamic Trend Overlay as a TradeBot strategy.

Do not continue mutating DTO thresholds or adding confirmations on the same validation period. After nine frozen variants and two legitimate state policies, further searching inside this family would be post-selection and data mining.

DTO may remain a chart visualization or non-authoritative descriptive feature. It has not demonstrated incremental option-buying edge in this corpus.

## Authority boundary

- Research only.
- No broker API calls.
- No order actions.
- No paper-trading authorization.
- No live-trading authorization.
- No production strategy, risk, feed, ranking or execution changes.
