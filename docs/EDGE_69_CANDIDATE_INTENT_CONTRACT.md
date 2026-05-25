# EDGE-69 — CandidateIntent Contract

## Purpose

EDGE-69 locks the smallest safe contract that future strategy generators must emit before any candidate pool validation, strategy conversion, rebuild, ranking, paper truth, or live-pilot work continues.

The problem being fixed is structural: existing code has candidate pools, normalized strategy metadata, scoring, ranking, and older movement candidates, but there was no single `CandidateIntent` contract for future strategy generators to target.

Without this contract, EDGE-71 and later strategy rebuilds would keep producing inconsistent shapes and the system would drift back into a filtered-output viewer instead of a real opportunity engine.

## Added

- `core/candidate_intent.py`
  - `CandidateIntent`
  - `CandidateIntentRejection`
  - `CandidateIntentValidationReport`
  - `create_candidate_intent(...)`
  - `validate_candidate_intent(...)`
  - `validate_candidate_intents(...)`

## Contract rules

A `CandidateIntent` is:

- read-only
- non-action
- metadata/evidence only
- not a broker order
- not a paper order
- not a ranked candidate
- not a scored candidate
- not an executable trade

Every serialized intent and report emits:

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

## Required fields

- `candidate_intent_id`
- `strategy_id`
- `instrument`
- `direction`
- `regime`
- `family`
- `intent_type`
- `trigger`
- `invalidation`
- `required_evidence_keys`

## Safety blockers

The validator rejects structurally unsafe payloads when they contain:

- missing required fields
- invalid direction
- invalid intent type
- unsafe action flags
- forbidden order/action fields
- duplicate candidate intent IDs
- malformed payload markers

Forbidden order/action fields include examples such as `quantity`, `qty`, `order_type`, `price`, `entry_price`, `limit_price`, `stop_loss`, `target_price`, `place_order`, `submit_order`, `modify_order`, and `cancel_order`.

## Important behavior

A blocked strategy intent can still be structurally valid.

Example: a strategy may emit an intent with `blockers=["weak_signal"]`. That is valid evidence, but it is not pool-eligible.

This matters because EDGE-70 can keep blocked/non-ready intents visible for diagnosis instead of hiding them, while still preventing them from becoming executable.

## Out of scope

EDGE-69 does not add:

- candidate pool validation
- strategy conversion
- strategy rebuilds
- ranking
- scoring
- NoTradeOracle
- review queue/UI work
- paper journal writes
- broker calls
- order intent
- runtime wiring

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_69_candidate_intent_contract.py
```

## Next PR

EDGE-70 — Candidate Pool and Validator, adapted to CandidateIntent.
