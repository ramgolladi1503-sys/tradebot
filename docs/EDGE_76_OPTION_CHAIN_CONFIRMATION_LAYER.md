# EDGE-76 — Option Chain Confirmation Layer

## Purpose

EDGE-76 adds a pure option-chain confirmation layer after the CandidateIntent strategy rebuilds.

The layer answers one narrow question: does an eligible option candidate have clean option-chain quote and liquidity evidence? It does not rank candidates, score edge, choose capital, touch runtime, or call external execution adapters.

## Added

- `core/option_chain_confirmation.py`
- `OptionChainConfirmation`
- `OptionChainConfirmationReport`
- `confirm_option_chain_for_candidates(...)`
- `confirm_option_chain_for_candidate_pool(...)`

## Inputs

The confirmation layer accepts:

- CandidateIntent values or an already-built candidate pool
- An option-chain snapshot as a list of contract rows or a mapping containing rows
- Optional deterministic freshness and liquidity thresholds

Contract rows may include fields such as symbol, underlying, option type, strike, expiry, LTP, bid, ask, volume, open interest, timestamp, and quality/status markers.

## Confirmation behavior

A candidate is confirmed only when all of these are true:

1. The candidate is pool-eligible.
2. The candidate direction identifies call or put context.
3. A matching option-chain contract exists.
4. The snapshot is fresh when a current epoch is supplied.
5. The selected contract has valid LTP, bid, ask, volume, and open-interest values.
6. The spread is within the configured limits.
7. The selected contract has no fallback, recovered, estimated, stale, mismatch, missing-quote, or subscription-failure markers.

If any condition fails, the layer returns a blocked confirmation with explicit blockers.

## Safety model

EDGE-76 is read-only and deterministic.

The report preserves non-action guarantees and records that it does not import strategy modules, execute strategy callables, rank candidates, score edge, or touch runtime.

## Why this matters

The previous strategy rebuilds create better candidate hypotheses. EDGE-76 prevents those hypotheses from being treated as usable unless option-chain evidence is clean enough. This directly addresses the risk of candidates looking valid while being backed by patched, stale, wide-spread, or illiquid option data.

## Out of scope

EDGE-76 does not add:

- runtime wiring
- ranking
- scoring
- dashboard changes
- capital allocation
- paper journal writes
- external execution integration
- exit models

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_76_option_chain_confirmation.py
```

## Next PR

EDGE-77 — Strategy-Specific Exit Models.
