# Gravity-Well Location + Participation Research V1

## Objective

Falsify whether higher-timeframe location, movement away from a gravity centre, centre acceleration and NIFTY constituent participation contain incremental forecasting information for buy-only NIFTY options.

This is a semantic mechanism study, not an exact Pine port and not an indicator-integration change.

## Current verdict

```text
DATA_BLOCKED_MISSING_VOLUME_CONSTITUENTS_AND_REAL_OPTIONS
NO_PRICE_ONLY_VALIDATION_SURVIVOR
HOLDOUT_SEALED
NO_STRATEGY_INTEGRATION
```

The complete mechanism remains untested because the available multi-session archive has zero underlying volume, no NIFTY constituent bars and no authoritative expired-option contract identity. A separately frozen price-only diagnostic was tested and produced no validation survivor.

## Source progression

### Initial Drive audit

The first run used two bounded 2026 Drive extracts and found only one complete session. Its historical evidence remains in:

```text
data_manifest.json
evidence/report.json
schema_inspection_manifest.json
```

Those files are retained as the **initial source audit**, not the current campaign verdict.

### Multi-session replay update

The uploaded `kite_candidate_replay(11).zip` was then fully audited:

```text
source ZIP SHA-256: f5912a89547dbca1c2b1243f239445bca79d474f21d020d87eb7ab5b33a9310d
Parquet files:        1,509 / 1,509 parsed
parse failures:       0
underlying files:     1,479
option files:         30, all explicitly OPT_MOCK
NIFTY sessions:       493
NIFTY 5m rows:        36,849
session range:        2024-07-09 through 2026-07-08
nonzero volume rows:  0
constituent rows:     0
real option identity: absent
```

The authoritative current evidence is:

```text
RESULTS.md
data_manifest_multi_session_20260804.json
frozen_price_only_diagnostic_spec_20260804.json
evidence/multi_session_replay_20260804.json
```

## Frozen primary mechanism

### `GW_ESCAPE_ACCEPTANCE`

Price escapes an ATR-normalized volume-weighted centre, centre slope and acceleration agree, constituent participation expands, and the first causal pullback holds.

### `GW_FAILED_ESCAPE`

Price reaches extreme displacement, centre movement or participation fails to support continuation, and price returns inside the band.

### `GW_CLUSTER_BREAK_ACCEPTANCE`

Price accepts a prior-completed higher-timeframe level, room remains to the next opposing cluster, and the centre plus constituent participation confirm.

The primary implementation returns zero certifiable events when volume, constituents or authoritative option identity are unavailable. Tick count, option activity and synthetic breadth are not substitutes.

## Frozen price-only diagnostic

Because the primary data gate failed before outcomes, one bounded fallback diagnostic was frozen before evaluation:

- completed NIFTY five-minute bars;
- EMA-centre length 20 with neighbours 14 and 30;
- Wilder ATR 14, 1.5 ATR outer band and 2.0 ATR extreme band;
- prior-completed 15-minute and 30-minute levels plus previous-session high/low;
- next-bar entry and no cross-session outcomes;
- primary 30-minute horizon;
- 2 bps primary and 5 bps severe cost stress;
- chronological 295 development / 99 validation / 99 sealed-holdout sessions;
- session bootstrap, winner removal, session-concentration and matched-random controls.

## Validation results at 2 bps

| Family | Validation trades / sessions | Expectancy | PF | 95% session CI | Decision |
|---|---:|---:|---:|---:|---|
| Escape acceptance | 134 / 79 | -3.49 bps | 0.39 | [-5.23, -1.90] | reject |
| Failed escape | 7 / 7 | +0.77 bps | 1.38 | [-3.29, 4.60] | reject: sparse and concentrated |
| Cluster-break acceptance | 20 / 20 | -3.96 bps | 0.46 | [-10.74, 2.24] | reject |

The failed-escape slice is not a survivor. It becomes negative under 5 bps costs, top-winner removal, top-session removal and both predeclared centre-length neighbours.

All simple validation baselines were also negative:

```text
EMA cross:              -2.07 bps
ATR displacement:       -1.81 bps
direct outer-band fade: -2.19 bps
HTF cluster break:      -2.23 bps
```

## Integrity

- 10/10 focused integrity checks passed;
- future HTF mutation cannot alter past levels;
- entries occur strictly after completed signals;
- `OPT_MOCK` files are excluded from option P&L;
- holdout outcomes were never calculated;
- deterministic event-ledger SHA-256: `37a21a64f74f632f1c31ecc3bf14cefd4e2d2eeeb8c732c23e3e2c4c26d8ae4d`;
- deterministic certification SHA-256: `5c830f4cc18b1a3c57593f89b65938cf91a822063e082caa065f4adffc961846`.

## Decision

Do not integrate or tune the price-only variants. Further threshold changes against this validation set would be post-selection.

The complete mechanism may be reopened only with:

- trustworthy nonzero centre input or a separately justified frozen centre definition;
- timestamp-aligned NIFTY constituent bars;
- real expired-option OHLC or bid/ask with expiry, strike, CE/PE and immutable contract identity;
- the preserved Market Event Graph corpus for incremental comparison.

## Safety boundary

Research only. No strategy registration, TradeBuilder, ranking, dashboard, feed runtime, risk, approval, broker, order, execution or live-launcher code is changed. Keep draft and unmerged.
