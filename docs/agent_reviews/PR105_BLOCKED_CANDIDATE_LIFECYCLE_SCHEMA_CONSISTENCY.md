# PR105 — Blocked Candidate Lifecycle Schema Consistency

## Agent Work Contract

### Problem

Post-PR104 live validation fixed final emit truth, but exposed a new schema/lifecycle inconsistency:

- `advisory_emit_schema_error`
- `failure_reason: readiness=BLOCKED requires hard_blockers`

This means blocked/final-aborted rows can still reach advisory serialization with `readiness=BLOCKED` and empty `hard_blockers`.

### Scope

This PR fixes blocked candidate lifecycle schema consistency only.

In scope:

- blocked readiness hard-blocker repair
- final block permission/final-action consistency
- tests proving blocked rows cannot serialize with empty hard blockers
- agent evidence file

Out of scope:

- broker calls
- live order placement
- strategy changes
- regime gate relaxation
- dashboard/UI
- feed subscription changes

## Grill Me Review

PASS.

The system must not produce blocked rows with no hard blockers. That is a broken contract. Hiding the schema error would be fake progress; the correct fix is to repair lifecycle metadata before advisory serialization.

## Hermes Review

PASS.

Safety boundaries checked:

- no broker adapter changes
- no order API calls
- no execution routing changes
- no live/paper boundary changes
- no strategy scoring changes
- no gate relaxation

## GSD Review

PASS.

Implementation plan:

1. Add blocked lifecycle schema normalization helper.
2. Ensure blocked readiness/final-action rows always have hard blockers.
3. Force `final_action=BLOCK` rows to remain `permission=BLOCK`.
4. Apply normalization before final advisory serialization.
5. Add focused regression tests plus prior PR102–PR104 tests.

## Scope Guard

PASS.

This is schema/lifecycle consistency only. It does not make any candidate executable.

## Approval + Evidence

Approval pending targeted tests.


## QA / Safety Review

N/A

## High-Risk Path Review

N/A

## Acceptance Proof

N/A

## Runtime Proof Required After Merge

N/A

## What This PR Does Not Prove

N/A

## Human Approval

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
