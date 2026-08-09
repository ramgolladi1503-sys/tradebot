# HUNT V1 Closure

Status: `NO_CANDIDATE_ADVANCED_TO_HOLDOUT`

Research only. Runtime authority: `NONE`. Broker actions permitted: `false`. Edge claimed: `false`.

## Frozen generation

- Generation: `HUNT_V1_GENERATION_FREEZE`
- Dataset: `BANKNIFTY_NIFTY_SENSEX_SYNC_5M_V1`
- Dataset SHA-256: `66ddbfead966388262b9a1e49937fb227b711ce32f70eaf715a93a5e32572b32`
- Sealed certification kernel identity: `46dd4f7df9b63486eb633a12baf25412cd4f761d`
- Candidate family size: 5

## Development outcome

Four candidates were rejected in development. One candidate, `HUNT_V1_LEADER_REVERSAL_TRANSMISSION`, was nominated for validation using only development outcomes.

Frozen nominated configuration:

- `from_open_min_bps = 40`
- `reversal_bar_min_bps = 15`
- `horizon_bars = 3`

Development metrics for the nomination:

- trades: 65
- mean net bps/trade: approximately +0.234

## Validation outcome

The validation policy was frozen before validation outcomes were opened. It required at least 20 validation trades and positive mean/total net bps under the same frozen 2 bps round-trip cost.

Observed validation evidence:

- validation sessions: 98
- trades: 8
- mean net bps/trade: +1.5025925645535076
- win rate: 0.5
- total net bps: +12.020740516428061
- verdict: `VALIDATION_FAIL`
- reason: insufficient validation trade count under the predeclared minimum

## Holdout

`holdout_outcomes_accessed = false`.

The holdout remains unopened and must not be inspected for HUNT V1. A positive small-sample validation mean does not authorize promotion or retuning.

## Terminal rule

HUNT V1 is closed. No HUNT V1 parameter, threshold, horizon, signal rule, or validation gate may be changed and rerun under this generation identity. Any further research must create a new pre-frozen hypothesis generation and must not use HUNT V1 holdout outcomes for design or selection.
