# HUNT V2 Closure

Status: `NO_CANDIDATE_ADVANCED_TO_HOLDOUT`

Research only. Runtime authority: `NONE`. Broker actions permitted: `false`. Edge claimed: `false`.

## Frozen generation

- Generation: `HUNT_V2_GENERATION_FREEZE`
- Dataset: `BANKNIFTY_NIFTY_SENSEX_SYNC_5M_V1`
- Dataset SHA-256: `66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32`
- Sealed certification kernel identity: `46dd4f7df9b63486eb633a12baf25412cd4f761d`
- Candidate family size: 5

## Development outcome

Three candidates were nominated for validation using development outcomes only:

1. `HUNT_V2_BANKNIFTY_OPENING_SHOCK_DECAY`
   - config: `counter_bar_bps=15`, `shock_bps=50`, `horizon_bars=6`
   - development trades: 104
   - development mean net bps/trade: +1.5903705660447234

2. `HUNT_V2_CROSS_MARKET_DISPERSION_COMPRESSION`
   - config: `dispersion_bps=15`, `horizon_bars=6`
   - development trades: 123
   - development mean net bps/trade: +2.0725436800154706

3. `HUNT_V2_RELATIVE_ACCELERATION_CONTINUATION`
   - config: `bar_bps=20`, `margin_bps=30`, `horizon_bars=1`
   - development trades: 121
   - development mean net bps/trade: +0.3989090855935901

Two other candidates were rejected in development.

## Validation outcome

The validation policy was frozen before validation outcomes were opened. It required at least 20 validation trades and positive mean/total net bps under the same frozen 2 bps round-trip cost.

Observed validation evidence:

### HUNT_V2_BANKNIFTY_OPENING_SHOCK_DECAY
- validation trades: 11
- mean net bps/trade: -3.8482705359428144
- win rate: 0.36363636363636365
- total net bps: -42.33097589537096
- verdict: `VALIDATION_FAIL`
- reasons: `INSUFFICIENT_VALIDATION_TRADES`, `NONPOSITIVE_VALIDATION_MEAN`, `NONPOSITIVE_VALIDATION_TOTAL`

### HUNT_V2_CROSS_MARKET_DISPERSION_COMPRESSION
- validation trades: 6
- mean net bps/trade: -8.394652465845883
- win rate: 0.3333333333333333
- total net bps: -50.36791479507531
- verdict: `VALIDATION_FAIL`
- reasons: `INSUFFICIENT_VALIDATION_TRADES`, `NONPOSITIVE_VALIDATION_MEAN`, `NONPOSITIVE_VALIDATION_TOTAL`

### HUNT_V2_RELATIVE_ACCELERATION_CONTINUATION
- validation trades: 9
- mean net bps/trade: -8.02244907230764
- win rate: 0.3333333333333333
- total net bps: -72.20204165076876
- verdict: `VALIDATION_FAIL`
- reasons: `INSUFFICIENT_VALIDATION_TRADES`, `NONPOSITIVE_VALIDATION_MEAN`, `NONPOSITIVE_VALIDATION_TOTAL`

## Holdout

`holdout_outcomes_accessed = false`.

The final 100-session holdout remains unopened and must not be inspected for HUNT V2.

## Terminal rule

HUNT V2 is closed. No HUNT V2 signal rule, threshold, horizon, cost, selection rule, or validation gate may be changed and rerun under this generation identity. Any further research must create a new pre-frozen hypothesis generation and must not use HUNT V2 holdout outcomes for design or selection.
