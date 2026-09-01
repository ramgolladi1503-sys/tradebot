# PR #881 — daily instrument authority reuse

## Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Reuse unchanged reviewed same-day instrument authority on restart
- scope: daily instrument authority producer and regression test only
- requested_paths: `core/daily_instrument_authority.py`, focused test
- allowed_paths: those files plus this review evidence
- forbidden_paths: credentials, broker write/order paths, live execution, governance gates
- expected_tests: daily authority validation and same-day reuse regression
- acceptance_proof: exact SHA CI and focused tests

## Scope Guard

This change does not fetch Kite data, alter credentials, or enable execution.
It preserves fail-closed date, release-SHA, raw-master-hash, and authority checks.

mode: read_only_advisory
candidate_id: daily-instrument-authority
decision: EXPECTED only for exact same-day unchanged reviewed authority
reason: avoid repeated restart blocking without accepting changed data
timestamp: authority acquisition timestamp
is_order_action: false
broker_api_called: false
source: exact-SHA deterministic authority producer

## Grill Me Review

The patch does not authorize a changed master or an unreviewed first artifact.

## Hermes Review

The same-day artifact remains bound to session date, release SHA, and raw SHA.

## GSD Review

This is one focused readiness fix; no governance or helper PR is included.

## QA / Safety Review

Regression coverage proves exact-match reuse passes. Existing mismatch tests
remain fail-closed. No broker or order method is called.

## Acceptance Proof

Ten daily-authority tests execute, including the restart reuse regression.

## Runtime Proof Required After Merge

Tomorrow’s fresh master and live token coverage remain morning-only checks.

## What This PR Does Not Prove

It does not prove live connectivity, fresh instrument availability, or trading
execution readiness.

## Human Approval

Merge remains subject to all repository protection and CI gates. No auto-merge.
