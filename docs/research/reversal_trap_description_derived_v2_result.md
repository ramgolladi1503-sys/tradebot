# Reversal Trap Description-Derived V2 Result

## Verdict

`NO_DEVELOPMENT_SURVIVOR_HOLDOUT_UNOPENED`

This result evaluates the strategy contract derived from the published description of **Reversal Trap Probability Bands [BigBeluga]**. It corrects the earlier replica by removing the unsupported canonical 30-minute exit and by searching the unresolved ATR length and envelope multiplier rather than assuming one pair.

It remains a description-derived interpretation, not a byte-for-byte Pine port.

## Reproducibility

- Workflow: `Reversal Trap Description-Derived V2`
- Successful run: `30733583665`
- Branch head tested: `2cd3884d6b50dfd84d2bff7999891afccd85a397`
- Runner SHA-256: `313cb8e0010e8e5343d1d69abc18964b64e305f8803c7b2969fe3d107e865cbc`
- Evidence semantic SHA-256: `fcc5ba7532524f2b638241c8398dd375ec7576698b5cb8a56ed190a07674117b`
- Artifact ZIP SHA-256: `fcd5718965565e32fc0ae1a82483e02c0120a2899743beac1d9d60bd2e742c76`
- Focused causal tests: `4 passed`

## Data boundary

Pinned third-party NIFTY 50 one-minute corpus:

- Source commit: `81800ba10cf47e9c7806b6a40e300ef389187846`
- Source SHA-256: `9b347479bb242e8cea8f85011a4d53e8938c1bfea1697fa25d8ef25d8888784d`
- Initial rows: `852,087`
- Retained valid rows: `851,076`
- Eligible sessions: `2,270`
- Retained period: `2015-01-09 09:15` through `2024-03-26 15:29`
- Duplicate timestamps: `0`
- Three incomplete sessions with fewer than 300 one-minute bars were excluded.

The final 20% of sessions was sealed as holdout and could be opened only after a candidate passed every development gate.

## Predeclared search

The study evaluated `225` configurations:

- ATR lengths: `7, 14, 21, 34, 55`
- Envelope multipliers: `1.0, 1.5, 2.0, 2.5, 3.0`
- Nine interpretation families:
  - canonical first-outside trap with frozen basis target and session exit;
  - most-recent-outside timing;
  - dynamic basis target;
  - most-recent timing plus dynamic target;
  - wick-outside/close-inside rejection;
  - 10-bar time stop;
  - 30-bar time stop;
  - 60-bar time stop;
  - direct outside-band fade.

Development used the first 80% of sessions and four chronological folds. The candidate had to be positive after five basis points of cost, positive in at least three of four folds, sufficiently supported, at least 0.5 bps better than the same-geometry direct fade, and positive across at least half of its parameter neighbours.

## Outcome across the entire grid

- Development survivors: `0 / 225`
- Net-positive candidates after five-basis-point cost: `0 / 225`
- Gross-positive candidates before cost: `30 / 225`
- Best gross expectancy anywhere: only `+0.2406 bps/trade`
- Net expectancy range: `-5.3715` to `-4.7594 bps/trade`

Even the strongest gross result was less than one-quarter of one basis point per trade and was produced by direct band fading, not by the reversal-trap sequence.

## Canonical strategy result

The strongest canonical parameter pair by development mean was:

- ATR length: `34`
- Multiplier: `3.0`
- Development trades: `17,695`
- Gross expectancy: `-0.0813 bps/trade`
- Net expectancy after five bps: `-5.0813 bps/trade`
- Uplift over equivalent direct fade: `-0.2980 bps/trade`
- Positive development folds: `0 / 4`

The description-derived trap therefore had negative expectancy even before costs and underperformed the simpler direct-fade baseline.

## Least-bad fold-stable interpretation

Selection among failed non-direct candidates prioritized the least-negative worst chronological fold, not the most attractive overall mean. That candidate was:

- Family: `wick_rejection`
- ATR length: `7`
- Multiplier: `3.0`
- Development trades: `21,375`
- Gross expectancy: `-0.0204 bps/trade`
- Net expectancy after five bps: `-5.0204 bps/trade`
- Fold net expectancies: `-4.8820`, `-4.9908`, `-5.1165`, `-5.0825` bps/trade
- Win rate: `42.77%`
- Profit factor: `0.3863`
- Uplift over equivalent direct fade: `-0.2199 bps/trade`
- Positive parameter-neighbour fraction: `0%`

This was not a candidate edge. It was simply the failed interpretation with the least-negative worst fold.

## Best result by interpretation family

| Family | Best ATR / multiplier | Gross bps/trade | Net bps/trade |
|---|---:|---:|---:|
| Direct fade | 55 / 3.0 | +0.2406 | -4.7594 |
| Wick rejection | 34 / 3.0 | +0.0580 | -4.9420 |
| 10-bar time stop | 34 / 3.0 | -0.0011 | -5.0011 |
| Recent-outside timing | 34 / 3.0 | -0.0774 | -5.0774 |
| Canonical trap | 34 / 3.0 | -0.0813 | -5.0813 |
| 60-bar time stop | 34 / 3.0 | -0.0845 | -5.0845 |
| 30-bar time stop | 34 / 3.0 | -0.1033 | -5.1033 |
| Recent timing + dynamic target | 34 / 3.0 | -0.1364 | -5.1364 |
| Dynamic target | 34 / 3.0 | -0.1429 | -5.1429 |

Changing the target behaviour, excursion timing, holding period, or wick definition did not reveal a positive development edge.

## RSI probability audit

The causal RSI-bucket probability model did not add useful out-of-sample information inside development:

- Bucket Brier score: `0.2466373`
- Constant-base-rate Brier score: `0.2471170`
- Improvement: `0.0004797`
- `adds_information`: `false`

Predeclared probability thresholds from 45% to 60%, with minimum historical counts from 20 to 100, all remained negative after costs. Sparse higher thresholds occasionally showed positive gross expectancy in tiny samples, but no stable positive fold structure and no executable post-cost edge.

## Holdout decision

The final 20% holdout remains unopened.

Opening it after all 225 configurations failed development would convert the sealed test period into another optimization dataset. No further parameter mutation against this corpus is permitted under this study.

## Decision

Do not integrate this description-derived indicator as a TradeBot strategy, ranking feature, or confidence score.

The result is stronger than the invalidated first replica because it covers the unresolved ATR geometry and all six requested interpretation ablations without opening holdout. However, it is still a public underlying-index proxy—not broker-certified option execution evidence and not an exact Pine-source parity result.

Research only. No paper or live authority.