# EDGE-73 — VWAP Strategy Rebuild

## Purpose

EDGE-73 adds a pure VWAP CandidateIntent generator.

This is the second strategy-family rebuild after the CandidateIntent contract, pool validator, passive strategy-output adapter, and breakout generator were merged.

The implementation is intentionally narrow: it builds VWAP trend hypotheses from a market-state snapshot and emits a read-only CandidateIntent validated through the CandidateIntent pool.

## Added

- `core/vwap_candidate_generator.py`
- `VwapCandidateGenerationReport`
- `build_vwap_candidate_intents(...)`

## Inputs

The generator reads a market-state mapping with fields such as:

- symbol / instrument / tradingsymbol / underlying
- ltp / last_traded / last
- vwap / session_vwap / anchored_vwap
- vwap_slope / slope / vwap_trend
- regime / market_regime / regime_state

## Candidate behavior

### Upside VWAP trend

If LTP is sufficiently above VWAP and slope confirmation is present, the generator emits a BUY_CALL ENTRY CandidateIntent.

### Downside VWAP trend

If LTP is sufficiently below VWAP and slope confirmation is present, the generator emits a BUY_PUT ENTRY CandidateIntent.

### Blocked hypotheses

If the market is inside the VWAP neutral zone, lacks required VWAP evidence, has invalid numeric input, or lacks slope confirmation, the generator still emits a visible NO_TRADE CandidateIntent with blockers.

The blocked intent is kept in the pool report so the reason is auditable.

## Safety model

The generator is read-only and pure.

Safety flags are asserted in tests and in generated payloads. The generator metadata records that it does not import strategy modules, execute strategy callables, rank candidates, score edge, or touch runtime.

## Out of scope

EDGE-73 does not add:

- runtime strategy wiring
- ranking
- scoring
- executable selection
- dashboard changes
- external execution integration
- paper journal writes

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_73_vwap_candidate_generator.py
```

## Next PR

EDGE-74 — Mean Reversion Strategy Rebuild.
