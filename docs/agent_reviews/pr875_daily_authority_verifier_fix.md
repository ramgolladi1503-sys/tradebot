# PR #875 — Daily authority verifier follow-up

## Agent Work Contract

mode: READ_ONLY_SOURCE_AUTHORITY_CHANGE
candidate_id: PR875_DAILY_AUTHORITY_VERIFIER_FIX
decision: REVIEW_REQUIRED_BEFORE_MERGE
reason: index rows have non-applicable zero lot and tick metadata
timestamp: 2026-09-01T06:25:00Z
is_order_action: false
broker_api_called: false
source: protected main after PR874

## Scope Guard

Only the independent verifier and its regression test change. Feed, strategy, CAS, order, execution, broker, credential, and risk paths are untouched.

## Grill Me Review

The exemption is limited to rows whose segment is `INDICES`; tradable contract rows still require positive lot and tick values. No authority acceptance rule is broadened.

## Hermes Review

Kite’s index metadata legitimately reports zero lot and tick values. Treating those fields as contract metadata caused a false fail on the acquired daily master.

## GSD Review

This is a narrow post-merge repair required before producing the 2026-09-01 authority artifact.

## QA / Safety Review

Focused tests pass locally, including the new index-metadata regression. No broker connection or order-capable method is involved.

## Acceptance Proof

Index rows with non-applicable zero lot/tick values pass; malformed rows and non-index rows with invalid lot/tick values fail closed.

## Runtime Proof Required After Merge

Re-run the producer against the already acquired raw master, verify the exact protected merge SHA, and require `authority_verdict=PASS` before any feed startup.

## What This PR Does Not Prove

This does not prove live feed health, subscription convergence, tick/depth advancement, full-day coverage, CAS eligibility, edge, or execution viability.

## Human Approval

This PR is part of the explicitly supplied daily instrument authority task and remains subject to protected CI and normal merge.
