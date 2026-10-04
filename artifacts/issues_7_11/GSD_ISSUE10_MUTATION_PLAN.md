# GSD Plan — Issue 10 advisory reader mutation verification

**source_agent:** gsd
**action:** GENERATE_TESTS, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Prove advisory JSONL reader rejects mixed generations and invalid delimiters
**scope:** Isolated mutation verification of the existing Issue 10 reader; no production code edits.

## Files

- `scripts/verify_issues_7_11_issue10_mutations.py`: copy the existing producer and focused test module into a temporary package, sabotage one guard per run, and require the matching behavior test to fail.
- `tests/core/test_runtime_snapshot_producer.py`: existing in-place rewrite and LF-only delimiter behavior tests are the mutation oracles; no test weakening or new production fixture.
- `artifacts/issues_7_11/ISSUE10_MUTATION_RESULTS_20261003.md`: record exact result, source/test hashes, and the offline-only limitation.

## Mutations

1. Remove the pre/post descriptor metadata comparison. The in-place rewrite test must fail because the reader returns rows from an uncertain snapshot.
2. Replace LF-only splitting with `str.splitlines()`. The U+2028 JSON string test must fail because a legal string value is split as multiple records.

## Execution and acceptance

- Run both targeted tests against the checkout before mutation.
- Run each mutant in a separate temporary copy with bytecode caching disabled and a bounded timeout.
- Each test must fail for its intended assertion; import/collection errors and timeouts are invalid mutation results.
- Confirm the checked-out production and test file hashes are unchanged after both experiments.

## Boundaries

This verifies these two Issue 10 reader guards only. It does not prove multi-process writer atomicity, captured/live EOD parity, unknown-desk policy, or campaign-wide mutation closure. No runtime, broker, order, risk, feed, strategy, config, or token-universe behavior changes.
