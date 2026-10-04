# GSD Plan — Issue 9 targeted source-mutation verification

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, UPDATE_DOCS
**title:** Prove completed-bar cutoff and immutable deduplication guards
**scope:** Execute only `docs/agent_reviews/issues_7_11_hermes_issue9_mutation_contract.md`.

## Files

- `scripts/verify_issues_7_11_issue9_mutations.py`: temporary-copy mutation runner for the two specified source guards.
- `core/market_session_store.py`: read-only source input; no checkout edits.
- `tests/core/test_market_session_store.py`: read-only behavior-test input; no checkout edits.
- `artifacts/issues_7_11/ISSUE9_MUTATION_RESULTS_20261003.md`: exact baseline, mutation, hash, and scope results.

## Execution

1. Run both behavior tests unmodified and require them to pass.
2. Remove the completion cutoff in a temporary copy and require the incomplete-bar test to fail by assertion.
3. Remove the row-hash conflict guard in a temporary copy and require the immutable-bar mutation test to fail by assertion.
4. Reject timeouts, import/collection failures, and unrelated test failures as invalid mutation outcomes.
5. Confirm the source/test SHA-256 values in the checkout are unchanged after the run.

## Acceptance

Both mutants are killed, the unmodified baseline is green, the checkout remains byte-identical for the two protected files, and no production behavior or authority is changed.
