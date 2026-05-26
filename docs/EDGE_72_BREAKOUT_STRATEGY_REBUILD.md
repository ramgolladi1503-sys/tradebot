# EDGE-72 — Breakout Strategy Rebuild

## Purpose

EDGE-72 adds a pure breakout CandidateIntent generator.

This is the first strategy-family rebuild after the CandidateIntent contract, pool validator, and passive strategy-output adapter were merged.

The implementation is intentionally narrow: it builds breakout hypotheses from a market-state snapshot and emits a read-only CandidateIntent that is validated through the CandidateIntent pool.

## Added

- `core/breakout_candidate_generator.py`
  - `BreakoutCandidateGenerationReport`
  - `build_breakout_candidate_intents(...)`

## Inputs

The generator reads a market-state mapping with fields such as:

- symbol / instrument / tradingsymbol / underlying
- ltp / last_traded / last
- orb_high / range_high / opening_range_high
- orb_low / range_low / opening_range_low
- vol_z / volume_z / volume_confirmation
- regime / market_regime / regime_state

## Candidate behavior

### Upside breakout

If LTP clears the opening range high and volume confirmation meets the configured threshold, the generator emits a BUY_CALL ENTRY CandidateIntent.

### Downside breakout

If LTP breaks the opening range low and volume confirmation meets the configured threshold, the generator emits a BUY_PUT ENTRY CandidateIntent.

### Blocked hypotheses

If the market is inside the range, missing required evidence, has an invalid range, or lacks volume confirmation, the generator still emits a visible NO_TRADE CandidateIntent with blockers.

The blocked intent is kept in the pool report so the reason is auditable.

## Safety model

The generator is read-only and pure.

It serializes:

```json
{
  "read_only": true,
  "append": false,
  "is_order_action": false,
  "broker_api_called": false,
  "live_order_action": false,
  "broker_order_action": false
}
```

The metadata explicitly records:

- does not import strategy modules
- does not execute strategy callables
- does not rank candidates
- does not score edge
- does not touch runtime

## Out of scope

EDGE-72 does not add:

- runtime strategy wiring
- ranking
- scoring
- executable selection
- dashboard changes
- broker integration
- paper journal writes

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_72_breakout_candidate_generator.py
```

## Next PR

EDGE-73 — VWAP Strategy Rebuild.
