# Gravity-Well Hypothesis Correctness Audit V2

## Executive verdict

The previous campaign **did not faithfully evaluate the published Gravity Well Trend indicator**. It evaluated custom structural extensions inspired by the indicator and then used an EMA price-only substitute because the archive has no usable volume, constituents, or real option contracts.

The corrected campaign evaluates the published-description modes separately:

- `SOURCE_TREND_SLOPE`: ATR escape plus a centre moving in the same direction;
- `SOURCE_TREND_ACCEL_STRICT`: stricter sensitivity lane for the overview's acceleration wording;
- `SOURCE_MIDLINE`: above/below-centre state flips;
- `SOURCE_BANDS_RECLAIM`: cross above the lowest outer band to turn long, then remain long until a cross below the highest outer band turns short.

The source describes a VWMA gravity centre, ATR-normalized distance, and these three selectable modes. It does not describe the earlier failed-escape and HTF-cluster families as its built-in modes.

## What was wrong before

1. Midline mode was omitted.
2. Bands reclaim hysteresis was omitted.
3. Failed escape and HTF cluster break were custom extensions but were presented too close to the source hypothesis.
4. EMA was used as the centre proxy. A uniform-volume SMA is the closer neutral analogue to VWMA when volume is unavailable.
5. The first corrected draft still reset directional state each session. That could manufacture daily flips. The final runner preserves indicator state across sessions while forcing trade outcomes to remain intraday.
6. The old repository primary families also did not fully implement their own custom frozen contract: pullback, opposing-level room, two-level clustering, compression, 30-minute location and explicit next-bar entry were incomplete or absent.

## Corrected contract

- 493 NIFTY sessions and 36,849 completed five-minute bars;
- chronological 295 development / 99 validation / 99 sealed-holdout sessions;
- state preserved across sessions;
- entry strictly on the next bar;
- outcome forced to the same session;
- maximum hold six bars / 30 minutes;
- 2 bps primary and 5 bps severe underlying costs;
- `TRUE_VWMA` implemented and fail-closed when positive volume is absent;
- current archive executes only `UNIFORM_VOLUME_SMA` and `EMA_SENSITIVITY` proxy lanes;
- no mock-option P&L and no real-option edge claim;
- exact source-code replication is not claimed because only the published description, not an independently verified Pine implementation, was reproduced.

## Corrected validation results

| Centre mode | Published mode | Dev expectancy | Validation trades / sessions | Validation expectancy | PF | 95% session CI | Severe-cost expectancy | Remove top 5 | Remove top 2 sessions |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| UNIFORM_VOLUME_SMA | SOURCE_TREND_SLOPE | -2.68 | 181 / 85 | -1.77 | 0.73 | [-3.02, 1.83] | -4.77 | -2.86 | -2.31 |
| UNIFORM_VOLUME_SMA | SOURCE_TREND_ACCEL_STRICT | -2.61 | 179 / 85 | -1.69 | 0.74 | [-2.92, 1.84] | -4.69 | -2.78 | -2.23 |
| UNIFORM_VOLUME_SMA | SOURCE_MIDLINE | -2.16 | 808 / 99 | -1.81 | 0.64 | [-1.17, 1.09] | -4.81 | -2.07 | -1.97 |
| UNIFORM_VOLUME_SMA | SOURCE_BANDS_RECLAIM | -1.30 | 181 / 86 | -2.36 | 0.65 | [-5.33, -1.03] | -5.36 | -3.38 | -2.88 |
| EMA_SENSITIVITY | SOURCE_TREND_SLOPE | -3.30 | 152 / 78 | -1.92 | 0.69 | [-3.12, 2.41] | -4.92 | -3.28 | -2.62 |
| EMA_SENSITIVITY | SOURCE_TREND_ACCEL_STRICT | -3.30 | 152 / 78 | -1.92 | 0.69 | [-3.12, 2.41] | -4.92 | -3.28 | -2.62 |
| EMA_SENSITIVITY | SOURCE_MIDLINE | -2.20 | 811 / 99 | -1.81 | 0.65 | [-1.45, 0.66] | -4.81 | -2.06 | -1.97 |
| EMA_SENSITIVITY | SOURCE_BANDS_RECLAIM | -1.36 | 151 / 80 | -4.82 | 0.39 | [-9.08, -4.09] | -7.82 | -5.84 | -5.30 |

## Interpretation

Every executed published-mode lane has negative validation expectancy after 2 bps and a profit factor below one.

- **Bands reclaim is a clear failure on this price-only archive.** Its bootstrap interval is entirely below zero under both SMA and EMA centre proxies.
- **Midline and Trend are not validated.** Their point estimates and profit factors are negative; some confidence intervals cross zero, so the correct statement is “no evidence of edge,” not “universally impossible.”
- **True VWMA remains untested.** The archive has zero nonzero-volume rows, so the actual volume-weighted hypothesis cannot be evaluated honestly.
- **Option profitability remains untested.** The option files are mock-named and lack immutable contract identity.

## Corrected verdict

```text
PREVIOUS_SOURCE_FIDELITY_CLAIM_INVALID
PUBLISHED_DESCRIPTION_MODES_REBUILT
STATE_PRESERVED_ACROSS_SESSIONS
NO_PRICE_ONLY_PUBLISHED_MODE_VALIDATION_SURVIVOR
TRUE_VWMA_HYPOTHESIS_NOT_EVALUATED
REAL_OPTION_EDGE_NOT_EVALUATED
HOLDOUT_SEALED
NO_STRATEGY_INTEGRATION
```

## Strategy change

The research implementation is now split correctly:

### Published-description lane

- `SOURCE_TREND_SLOPE`
- `SOURCE_TREND_ACCEL_STRICT`
- `SOURCE_MIDLINE`
- `SOURCE_BANDS_RECLAIM`

### Separate structural-extension lane

- `EXT_ESCAPE_PULLBACK`
- `EXT_FAILED_ESCAPE`
- `EXT_HTF_CLUSTER_BREAK`

These families must never be pooled into one Gravity-Well result.

The next authoritative campaign must use a volume-bearing underlying, preferably a governed NIFTY futures contract or continuous futures series. It should calculate true VWMA on futures, produce source-mode state flips there, and only then map the direction to real NIFTY CE/PE contracts with expiry, strike, option type, delayed entry, costs and expiry/non-expiry separation.

## Integrity

- focused semantic and safety tests: **7/7 passed**;
- state is continuous across session boundaries;
- no next-bar entry can cross into a new session;
- TRUE_VWMA fails closed without positive volume;
- uniform-volume proxy is verified as SMA, not EMA;
- corrected event ledger has **10,971 events plus header**;
- holdout outcomes remain sealed.
