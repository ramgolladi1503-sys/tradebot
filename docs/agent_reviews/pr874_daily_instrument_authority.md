# PR #874 — Daily instrument authority review

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Govern daily instrument-master authority for live read-only runtime
- scope: DAILY_INSTRUMENT_AUTHORITY_V1 producer, independent validation, and read-only runtime consumption
- requested_paths: authority module, authority producer, read-only launchers, focused tests, this evidence
- allowed_paths: the paths changed by this PR
- forbidden_paths: orders, execution, broker writes, credentials, strategy, CAS, feed implementation
- expected_tests: focused authority, registry, and launcher tests; protected CI
- acceptance_proof: dated artifact requires exact date/source/raw hash and independent PASS before runtime launch

## Scope Guard

No strategy, CAS, feed implementation, broker adapter, order, execution, credential, or risk-gate behavior was changed. The launchers remain observation-only and fail closed when authority is absent or invalid.

## Grill Me Review

The producer does not accept an unknown material change automatically; `--reviewed-pass` is explicit. Artifact tampering, source/date mismatch, raw hash mismatch, missing verifier status, and missing token coverage block. A future change must add a governed prior-session diff policy before broadening automatic acceptance.

## Hermes Review

The static release pin was a release-scoped authority incorrectly used as daily authority. The new contract separates raw acquisition, independent validation, explicit material-change review, immutable dated artifact creation, and runtime consumption.

## GSD Review

Implemented in one bounded PR from exact base `cc172343002fc69c16421e38562995bf32afb381`. No unrelated files were touched.

## QA / Safety Review

Focused validation: `16 passed`. Tests cover malformed/empty/duplicate/missing-token/material-change rejection, reviewed artifact validation, tampering, and dated-artifact overwrite prevention. Runtime authority remains read-only; no order-capable methods are introduced or invoked.

## Acceptance Proof

Required runtime checks are exact session date, source SHA, raw master SHA, contract ID, authority verdict, independent verifier, semantic validation, and token coverage. Any failed check returns `MORNING_BLOCKED_INSTRUMENT_AUTHORITY`.

## Runtime Proof Required After Merge

After protected merge, generate `INSTRUMENT_MASTER_AUTHORITY_20260901.json` from the already acquired raw master, verify its hash and exact merge SHA, independently validate it, and only then reassess live read-only startup. Do not relogin.

## What This PR Does Not Prove

It does not prove live feed connectivity, subscription confirmation, tick/depth advancement, persistence, analytics health, full-day coverage, CAS eligibility, structural edge, or execution viability.

## Human Approval

This PR implements the explicitly supplied `TRADEBOT_DAILY_INSTRUMENT_AUTHORITY_V1_20260901.md` task specification. Protected CI and normal merge remain required before runtime use.

## Evidence Contract Fields

mode: READ_ONLY_SOURCE_AUTHORITY_CHANGE
candidate_id: PR874_DAILY_INSTRUMENT_AUTHORITY_V1
decision: REVIEW_REQUIRED_BEFORE_MERGE
reason: dated authority is required because the prior release pin was not daily-scoped
timestamp: 2026-09-01T05:40:00Z
is_order_action: false
broker_api_called: false
source: exact base cc172343002fc69c16421e38562995bf32afb381
