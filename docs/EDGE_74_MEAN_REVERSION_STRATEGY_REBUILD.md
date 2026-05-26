# EDGE-74 — Mean Reversion Strategy Rebuild

## Purpose

EDGE-74 adds a pure mean-reversion CandidateIntent generator.

This is the third strategy-family rebuild after the CandidateIntent contract, pool validator, passive strategy-output adapter, breakout generator, and VWAP generator were merged.

The implementation is intentionally narrow: it builds mean-reversion hypotheses from a market-state snapshot and emits a read-only CandidateIntent validated through the CandidateIntent pool.

## Added

- `core/mean_reversion_candidate_generator.py`
- `MeanReversionCandidateGenerationReport`
- `build_mean_reversion_candidate_intents(...)`

## Inputs

The generator reads a market-state mapping with fields such as:

- symbol / instrument / tradingsymbol / underlying
- ltp / last_traded / last
- vwap / session_vwap / mean_anchor / anchor_price
- rsi_mom / rsi_momentum / oscillator / momentum
- regime / market_regime / regime_state

## Candidate behavior

### Upper extension reversal

If price is sufficiently above the anchor and reversal confirmation is present, the generator emits a BUY_PUT ENTRY CandidateIntent.

### Lower extension reversal

If price is sufficiently below the anchor and reversal confirmation is present, the generator emits a BUY_CALL ENTRY CandidateIntent.

### Blocked hypotheses

If the market is inside the neutral zone, lacks required anchor evidence, has invalid numeric input, or lacks oscillator confirmation, the generator still emits a visible NO_TRADE CandidateIntent with blockers.

The blocked intent is kept in the pool report so the reason is auditable.

## Safety model

The generator is read-only and pure.

Safety flags are asserted in tests and in generated payloads. The generator metadata records that it does not import strategy modules, execute strategy callables, rank candidates, score edge, or touch runtime.

## Out of scope

EDGE-74 does not add:

- runtime strategy wiring
- ranking
- scoring
- executable selection
- dashboard changes
- external execution integration
- paper journal writes

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_74_mean_reversion_candidate_generator.py
```

## Next PR

EDGE-75 — Zero Hero Expiry Strategy Rebuild.
