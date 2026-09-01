# PR #880 — CAS short-horizon advisory integration review evidence

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Wire the preserved CAS short-horizon hypothesis as a read-only advisory
- scope: canonical strategy registry, causal advisory object, queue idempotency, supersession evidence
- requested_paths: `core/cas_morning_reversal_advisory.py`, read-only registry/pipeline/queue, focused tests, CAS research evidence
- allowed_paths: the files changed by this PR
- forbidden_paths: broker write/order/position/funds paths, credentials, execution authority, strategy thresholds, historical research results
- expected_tests: focused evaluator, queue contract, safety and causality checks
- acceptance_proof: exact SHA-bound PR, CI gates, focused tests, no broker order calls

## Scope Guard

This is advisory-only. `BROKER_WRITE_AUTHORITY=false`, `ORDER_AUTHORITY=false`,
`PAPER_AUTHORIZED=false`, and `LIVE_EXECUTION_AUTHORIZED=false`. No broker
connectivity or order-capable method is invoked.

mode: advisory_only
candidate_id: session_id:symbol
decision: UP|DOWN|NO_SIGNAL
reason: causal 09:15-10:00 return with fresh 15:14 reference
timestamp: decision_timestamp
is_order_action: false
broker_api_called: false
source: exact-SHA read-only advisory evaluator

## Grill Me Review

The implementation does not establish an edge, prospective support, execution
viability, or live verification. The 20-session ledger remains the authority;
aggregate performance is not exposed before admission of 20 sessions.

## Hermes Review

The old `CAS_SW_RUNTIME_V2_1514` runtime is retained as historical provenance
and removed from the active canonical strategy identity. The new evaluator uses
only the frozen 09:15–10:00 return and a first fresh 15:14 observation.

## GSD Review

One focused integration PR follows the separately merged preservation PR #879.
No helper PR or scientific-result rewrite is included.

## QA / Safety Review

Focused tests cover positive, negative, exact-zero, pre-cutoff, and >2000 ms
late observations. Queue identity is session + strategy + symbol + decision
timestamp. The queue remains advisory-only.

## Acceptance Proof

`python -m pytest -q tests/test_cas_morning_reversal_advisory.py
tests/test_advisory_queue_contract.py` passed 4 tests locally.

## Runtime Proof Required After Merge

Only a fresh, exact-SHA, read-only observation session can prove runtime
invocation and emission. This PR does not claim that proof.

## What This PR Does Not Prove

It does not prove live readiness, prospective support, structural edge,
execution viability, P&L, or any order activity.

## Human Approval

Merge and any runtime activation remain subject to human review and all
repository CI/frozen-live-flow gates. No auto-merge is requested.
