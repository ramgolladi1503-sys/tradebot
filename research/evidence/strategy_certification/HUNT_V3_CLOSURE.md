# HUNT V3 Closure

Status: `NO_CANDIDATE_ADVANCED_TO_HOLDOUT`

Research only. Runtime authority: `NONE`. Broker actions permitted: `false`. Edge claimed: `false`.

## Frozen generation

- Generation: `HUNT_V3_GENERATION_FREEZE`
- Dataset: `BANKNIFTY_NIFTY_SENSEX_SYNC_5M_V1`
- Dataset SHA-256: `66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32`
- Sealed certification kernel identity: `46dd4f7df9b63486eb633a12baf25412cd4f761d`
- Candidate family size: 5

## Development outcome

Two candidates were nominated for validation using development outcomes only:

1. `HUNT_V3_WICK_REJECTION_REVERSAL`
   - range_bps = 35
   - wick_fraction = 0.45
   - horizon_bars = 6
   - development trades = 83
   - development mean net bps/trade = +1.8324007409203202

2. `HUNT_V3_FAILED_RANGE_ESCAPE_REVERSAL`
   - escape_bps = 2
   - prior_range_bps = 30
   - horizon_bars = 6
   - development trades = 122
   - development mean net bps/trade = +1.4435254261184982

The other three HUNT V3 passports were rejected in development.

## Validation outcome

The validation gate was frozen before validation outcomes were opened. It required at least 20 validation trades plus positive mean and total net bps under the same frozen 2 bps round-trip cost.

### Wick Rejection Reversal

- validation sessions: 98
- trades: 11
- mean net bps/trade: -2.279843832974987
- win rate: 0.7272727272727273
- total net bps: -25.078282162724857
- verdict: `VALIDATION_FAIL`
- reasons: insufficient validation trades; nonpositive validation mean; nonpositive validation total

### Failed Range Escape Reversal

- validation sessions: 98
- trades: 18
- mean net bps/trade: +3.7577377819783626
- win rate: 0.5
- total net bps: +67.63928007561053
- verdict: `VALIDATION_FAIL`
- reason: insufficient validation trade count under the predeclared minimum of 20

The positive 18-trade validation result is explicitly non-promotable. It must not be used to relax the minimum-trade gate, alter thresholds, change horizon, or justify opening holdout for HUNT V3.

## Holdout

`holdout_outcomes_accessed = false`.

The final 100-session HUNT V3 holdout remains unopened and must not be inspected for design, rescue, or retrospective selection.

## Terminal rule

HUNT V3 is closed. No HUNT V3 parameter, threshold, horizon, signal rule, sample-size gate, or validation criterion may be changed and rerun under this generation identity. Any further research must create a new pre-frozen hypothesis generation and must not use HUNT V3 holdout outcomes for design or selection.
