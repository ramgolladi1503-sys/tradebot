# EDGE-75 — Zero Hero Expiry Strategy Rebuild

## Purpose

EDGE-75 adds a pure Zero Hero expiry CandidateIntent generator.

This is the fourth strategy-family rebuild after the CandidateIntent contract, pool validator, passive strategy-output adapter, breakout generator, VWAP generator, and mean-reversion generator were merged.

The implementation is intentionally narrow: it builds expiry-momentum hypotheses from a market-state snapshot and emits a read-only CandidateIntent validated through the CandidateIntent pool.

## Added

- `core/zero_hero_candidate_generator.py`
- `ZeroHeroCandidateGenerationReport`
- `build_zero_hero_candidate_intents(...)`

## Inputs

The generator reads a market-state mapping with fields such as:

- symbol / instrument / tradingsymbol / underlying
- option_ltp / premium / ltp / last_traded / last
- dte / days_to_expiry / expiry_days
- is_expiry_day / expiry_day / same_day_expiry
- underlying_momentum / spot_momentum / momentum / move_bps
- vol_z / volume_z / volume_confirmation
- regime / market_regime / regime_state

## Candidate behavior

### Expiry call momentum

If expiry context is present, premium is within configured bounds, upward momentum is confirmed, and volume is confirmed, the generator emits a BUY_CALL ENTRY CandidateIntent.

### Expiry put momentum

If expiry context is present, premium is within configured bounds, downward momentum is confirmed, and volume is confirmed, the generator emits a BUY_PUT ENTRY CandidateIntent.

### Blocked hypotheses

If the snapshot is outside expiry context, premium is outside bounds, momentum is weak, volume is weak, or required evidence is absent, the generator still emits a visible NO_TRADE CandidateIntent with blockers.

The blocked intent is kept in the pool report so the reason is auditable.

## Safety model

The generator is read-only and pure.

Safety flags are asserted in tests and in generated payloads. The generator metadata records that it does not import strategy modules, execute strategy callables, rank candidates, score edge, or touch runtime.

## Out of scope

EDGE-75 does not add:

- runtime strategy wiring
- ranking
- scoring
- executable selection
- dashboard changes
- external execution integration
- paper journal writes

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_75_zero_hero_candidate_generator.py
```

## Next PR

EDGE-76 — Option Chain Confirmation Layer.
