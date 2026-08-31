# Agent Work Contract

mode: OFFLINE_STATIC_REVIEW
candidate_id: PR870_CERBERUS_DIFF_SCOPE
decision: FIX_NOW
reason: Preserve fail-closed boundary review while attributing findings to added candidate lines.
timestamp: 2026-08-31T22:40:00+0530
is_order_action: false
broker_api_called: false
source: current-main repository and focused unit tests

- source_agent: Codex
- action: GENERATE_PATCH
- title: Make Cerberus pull-request scans diff-aware
- scope: Preserve the existing safety markers while preventing unchanged baseline markers from being reported as new regressions.
- requested_paths: `tools/code_excellence/cerberus_gate.py`, `tests/test_code_excellence_cerberus_gate.py`, this review record.
- allowed_paths: The same three paths only.
- forbidden_paths: Product runtime, broker, order, risk, credential, launcher, and live-execution paths.
- expected_tests: `tests/test_code_excellence_cerberus_gate.py`.
- acceptance_proof: Added-line scanning, candidate-blob selection, fail-closed fallback, and unchanged-baseline regression coverage.

## Scope Guard

This PR changes only the static Cerberus reviewer and its tests. It does not change trading behavior, broker connectivity, order authority, risk gates, credentials, or evidence authority.

## Grill Me Review

The primary risk is accidentally ignoring a newly added restricted marker. The implementation derives added line numbers from the base/candidate diff and scans the candidate blob at those lines. If the required refs or blobs cannot be resolved, it falls back to scanning the complete file, preserving fail-closed behavior.

## Hermes Review

The change addresses a pull-request review boundary: `pull_request_target` executes trusted reviewer code from `main`, while the candidate source must be read from the candidate ref. No generic bypass, allowlist expansion, or forbidden-marker removal is introduced.

## GSD Review

The change is isolated, reversible, and test-backed. Existing marker configuration and block verdicts remain unchanged. The candidate ref may be supplied by `CERBERUS_CANDIDATE_REF` or derived from `PR_NUMBER`; the base may be supplied by `CERBERUS_BASE_REF`.

## QA / Safety Review

The regression test proves that a restricted marker unchanged from the baseline is not reported as a newly added finding. The test suite also covers malformed inputs, required false fields, and normal marker detection.

## Acceptance Proof

- `PYTHONPATH=. pytest -q tests/test_code_excellence_cerberus_gate.py -o addopts=''` -> 12 passed.
- No broker API was called.
- No order was placed, modified, cancelled, or otherwise mutated.

## Runtime Proof Required After Merge

No runtime proof is required because this is a static reviewer and test-only change. Any later runtime or live-observation claim must be independently established under its own exact-SHA and read-only authority contract.

## What This PR Does Not Prove

This PR does not prove live readiness, market-data freshness, strategy profitability, execution safety beyond the static reviewer behavior, or broker/order authority state.

## Human Approval

Merge remains subject to the repository's protected checks and human-controlled branch protection. No force, admin, or bypass merge is authorized.
