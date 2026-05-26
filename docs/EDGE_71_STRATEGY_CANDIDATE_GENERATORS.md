# EDGE-71 — Convert Existing Strategies to Candidate Generators

## Purpose

EDGE-71 introduces a passive adapter that converts already-produced strategy result dictionaries into the EDGE-69 `CandidateIntent` contract and then validates them through the EDGE-70 pool validator.

This PR does not rewrite strategy logic. It does not import or execute strategy modules. It does not wire strategy runtime into the new pool.

## Added

- `core/strategy_candidate_generator.py`
  - `StrategyCandidateGeneratorReport`
  - `convert_strategy_outputs_to_candidate_intents(...)`

## What the adapter does

The adapter accepts metadata dictionaries from existing strategy-like outputs and extracts:

- strategy identity
- instrument/symbol
- direction/bias
- regime
- strategy family
- trigger
- invalidation
- required evidence keys
- evidence references
- blockers/warnings

It then creates `CandidateIntent` objects and sends them through the CandidateIntent pool validator.

## Safety model

The adapter is read-only and passive.

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

## Rejection behavior

The adapter rejects source payloads that cannot safely become CandidateIntent values, including:

- missing strategy id
- missing instrument
- missing direction
- unsafe action-shaped fields

Rejected source payloads are retained as evidence with blockers and source keys.

## Blocked behavior

If a strategy output carries blockers/reject reasons, the adapter creates a NO_TRADE CandidateIntent. The pool keeps it visible in the blocked bucket and does not mark the pool ready from that candidate alone.

## Out of scope

EDGE-71 does not add:

- strategy rewrites
- actual runtime strategy invocation
- ranking
- scoring
- executable trade selection
- dashboard changes
- broker calls
- paper journal writes

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_71_strategy_candidate_generators.py
```

## Next PR

EDGE-72 — Breakout Strategy Rebuild.
