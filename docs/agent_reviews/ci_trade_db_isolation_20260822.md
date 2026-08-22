# CI Runtime Isolation Repair Review

## Agent Work Contract

- source_agent: ChatGPT/GitHub connector
- action: repair a repository-wide pytest isolation defect exposed by multiple unrelated weekend reconstruction PRs
- requested_paths: `tests/conftest.py`, `tests/test_market_data_index_quote_cache.py`, this review document
- prohibited_paths: runtime implementation, broker/order/feed behavior, strategy/risk, credentials, workflow acceptance criteria
- artifact_cleanup_contract: test runtime remains isolated under each pytest `tmp_path`; no repository runtime artifacts are created
- tests_and_ci_contract: full required CI must pass before merge; this repair does not make candidate-specific failures PASS by assertion
- deployment_notes: test-only change; no production deployment/runtime behavior
- human_approval: exact branch protection and merge authority remain required

## Root Cause Evidence

Two unrelated current-main reconstruction candidates (#846 cleanup and #847 Outcomes) independently failed the same two tests in `tests/test_market_data_index_quote_cache.py`. Their changed paths do not touch market-data behavior. The existing autouse runtime fixture isolates `DB_ROOT` but does not rebind `TRADE_DB_PATH`, allowing process-level configured SQLite authority to escape the per-test runtime root.

A pre-existing Evidence Kernel integration branch independently contains the same narrow compatibility repair: bind both environment and `config.config.TRADE_DB_PATH` to the per-test runtime database and add a focused assertion proving the fixture.

## Scope Guard

This PR changes only test isolation. It does not modify `core/market_data.py`, auth, feed truth, live quote semantics, or production database paths.

## QA / Safety Review

```text
RUNTIME_IMPLEMENTATION_CHANGE=false
BROKER_WRITE_AUTHORITY=false
ORDER_AUTHORITY=false
PAPER_AUTHORIZED=false
LIVE_AUTHORIZED=false
CI_GATE_WEAKENING=false
```

## Acceptance Proof

Required before merge:

- the fixture test proves `TRADE_DB_PATH` is inside each test's `tmp_path/runtime/db`;
- the full `tests` and `ci` workflows pass on this exact head;
- normal governance/security checks pass;
- no production path is changed.

## What This PR Does Not Prove

It does not prove #846, #847, or any other candidate is merge-ready. After this baseline repair merges, stale candidates must be refreshed/reconstructed on the new main and run fresh CI.

## Final Verdict

```text
SCOPE=TEST_ISOLATION_ONLY
BASELINE_REPAIR=AWAITING_CI
MERGE_ALLOWED=ONLY_AFTER_REQUIRED_CHECKS_PASS
```
