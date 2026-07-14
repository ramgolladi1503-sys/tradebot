# EDGE-70 — Candidate Pool and Validator, adapted to CandidateIntent

## Purpose

EDGE-70 adds a deterministic pool validator on top of the EDGE-69 `CandidateIntent` contract.

The pool layer does not generate strategies. It does not rank, score, route, execute, write paper truth, or touch runtime.

Its job is simple:

1. consume candidate intents,
2. validate them through the canonical EDGE-69 contract,
3. split them into eligible, blocked, and rejected buckets,
4. expose pool readiness without hiding blocked or rejected evidence.

## Added

- `core/candidate_intent_pool.py`
  - `CandidateIntentPoolEntry`
  - `CandidateIntentPoolReport`
  - `build_candidate_intent_pool(...)`

## Pool buckets

### Eligible

A candidate intent becomes eligible only when the EDGE-69 contract accepts it and the intent itself has no blockers.

### Blocked

A candidate intent is blocked when it is structurally valid but carries explicit blockers such as weak signal or miss-ing confirmation.

Blocked intents stay visible for diagnosis but do not make the pool ready.

### Rejected

A candidate intent is rejected when the EDGE-69 validator rejects its structure, unsafe flags, duplicate identity, malformed input, or forbidden action-shaped fields.

Rejected intents are retained in the report so failures are auditable.

## Safety contract

Every pool report and pool entry serializes:

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

## Out of scope

EDGE-70 does not add:

- strategy conversion
- strategy rebuilds
- strategy selection
- ranking
- scoring
- NoTradeOracle
- review queue/UI work
- paper journal writes
- runtime wiring

## Test command

```bash
PYTHONPATH=. python -m pytest tests/test_edge_70_candidate_intent_pool_validator.py
```

## Next PR

EDGE-71 — Convert Existing Strategies to Candidate Generators.
