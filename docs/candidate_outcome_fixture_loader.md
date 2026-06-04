# Candidate Outcome Fixture Loader

## Purpose

This module loads deterministic offline fixtures for the existing `CandidateOutcomeTruth` contract.
It converts committed JSON files into `CandidateOutcomeInput` and `PriceObservation` objects and
evaluates them with the existing pure contract.

## Scope

- Closed/off-market environment only.
- Offline deterministic fixture loading only.
- No runtime wiring.
- No broker, Kite, websocket, or external service access.

## Fixture schema

Each fixture is a JSON object with:

- `schema_version`
- `fixture_id`
- `description`
- `candidate`
- `observations`
- `expected`
- `metadata`

The loader fails closed on malformed or unsupported shapes.

## Example fixture

```json
{
  "schema_version": 1,
  "fixture_id": "target_hit",
  "description": "BUY candidate reaches target before stop.",
  "candidate": {
    "candidate_id": "cand-target-1",
    "trade_id": "trade-target-1",
    "strategy_family": "breakout",
    "symbol": "NIFTY",
    "signal_epoch": 100.0,
    "entry_price": 100.0,
    "stop_loss_price": 95.0,
    "target_price": 110.0,
    "timeout_epoch": 200.0,
    "side": "BUY",
    "reportable_executable": true,
    "execution_allowed": true
  },
  "observations": [
    { "observed_epoch": 101.0, "ltp": 103.0 },
    { "observed_epoch": 102.0, "ltp": 110.0 }
  ],
  "expected": {
    "outcome_status": "TARGET_HIT",
    "gross_r": 2.0,
    "cost_adjusted_r": 1.75
  },
  "metadata": {
    "closed_environment": true,
    "source": "synthetic"
  }
}
```

## Loader functions

- `load_candidate_outcome_fixture(path)` loads one fixture from disk.
- `evaluate_candidate_outcome_fixture(path)` loads and evaluates one fixture.
- `load_candidate_outcome_fixtures(directory)` loads all `*.json` fixtures in deterministic sorted order.

## What this PR does not do

- It does not write reports.
- It does not wire into runtime.
- It does not aggregate outcomes.
- It does not change execution logic.
- It does not prove trading edge.

## Why this does not prove edge

These fixtures are deterministic offline inputs. They validate parsing and contract behavior only.
They do not establish live market profitability, robustness to live data, or execution edge.

## Future consumer PRs

Future PRs can consume these fixtures to build offline outcome reports, regression suites,
or other deterministic validation tooling without changing runtime behavior.
