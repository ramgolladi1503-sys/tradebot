# EDGE-71 Strategy Candidate Generators Agent Review

mode: REVIEW
candidate_id: edge_71_strategy_candidate_generators
decision: review_ready
reason: passive_strategy_output_adapter_tests_docs
timestamp: 2026-05-26T03:45:00Z
is_order_action: false
broker_api_called: false
source: edge71_strategy_candidate_generator_review

## Agent Work Contract

Add a passive adapter that converts existing strategy-style output dictionaries into CandidateIntent values and validates them through the CandidateIntent pool.

## Scope Guard

In scope: adapter, focused tests, docs, TODO refresh.

Out of scope: strategy rewrites, runtime invocation, ranking, scoring, UI, broker work, paper journal.

## High-Risk Path Review

The high-risk path is accidentally executing strategy code or converting action-shaped fields into intent payloads.

Controls: adapter accepts dictionaries only, imports no strategy modules, invokes no callables, rejects unsafe source shapes, and serializes explicit non-action metadata.

## Grill Me Review

Verdict: pass.

The adapter does not pretend strategy quality is solved. It only normalizes already-produced metadata into the locked CandidateIntent contract.

## Hermes Review

Verdict: pass.

No runtime path, dashboard path, broker adapter, or strategy callable is touched.

## GSD Review

Verdict: pass.

This is the smallest safe bridge after EDGE-69 and EDGE-70 before rebuilding specific strategies.

## QA / Safety Review

Tests prove happy-path generation, blocked-source visibility, missing-field rejection, unsafe-shape rejection, empty-input fail-closed behavior, and non-action payload guarantees.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge_71_strategy_candidate_generators.py
```

## Runtime Proof Required After Merge

No runtime proof required because this is adapter-only and not wired into runtime.

## What This PR Does Not Prove

It does not prove strategy alpha, ranking, scoring, executable quality, paper truth, replay truth, live readiness, or dashboard correctness.

## Human Approval

Human approval required before merge.