# EDGE-69 CandidateIntent Contract Agent Review

mode: REVIEW
candidate_id: edge_69_candidate_intent_contract
decision: review_ready
reason: focused_contract_tests_docs
timestamp: 2026-05-25T19:15:00Z
is_order_action: false
broker_api_called: false
source: edge69_candidate_intent_review

## Agent Work Contract

Add a small CandidateIntent contract and tests.

## Scope Guard

In scope: contract, validator, tests, docs, TODO refresh.

Out of scope: pool builder, strategy conversion, ranking, scoring, UI, runtime wiring, paper journal.

## High-Risk Path Review

This PR adds one new file under `core/`.

Controls: new module only, read-only payloads, no mutation of existing behavior, tests for rejected unsafe payloads.

## Grill Me Review

Verdict: pass.

The contract rejects unsafe shapes and keeps blocked evidence visible without making it pool-eligible.

## Hermes Review

Verdict: pass.

Evidence includes deterministic IDs, sorted JSON payloads, accepted and rejected report shapes, blockers, warnings, and duplicate rejection.

## GSD Review

Verdict: pass.

This is the smallest useful step before EDGE-70 and EDGE-71.

## QA / Safety Review

Tests cover valid payloads, missing fields, unsafe flags, forbidden fields, invalid direction, duplicate IDs, blocked evidence, and empty input.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_69_candidate_intent_contract.py
```

## Runtime Proof Required After Merge

No runtime proof required because this is contract, test, and docs only.

## What This PR Does Not Prove

It does not prove strategy quality, ranking quality, paper truth, replay truth, live readiness, or dashboard correctness.

## Human Approval

Human approval required before merge.