# GSD Plan — Issue 10 append failure without destructive rollback

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Never truncate shared JSONL after an append failure
**Hermes contract:** `docs/agent_reviews/issues_7_11_hermes_issue10_external_append_rollback.md`

## Files

- `core/locked_jsonl.py`: remove failure-path `ftruncate`; preserve all bytes and log when a batch append fails. Cooperating writers remain serialized by flock.
- `tests/test_kite_read_only_observation_runtime.py`: prove external bytes survive and no truncate is attempted; failed own partial bytes remain and the advisory source reports an incomplete tail; actual advisory parsing rejects concatenated malformed bytes; retain original exception behavior and cooperating-writer coverage.
- `scripts/verify_issues_7_11_issue10_rollback_mutation.py`: inject a destructive-truncate mutant into a temporary copy and require the designated race regression to kill it.
- `docs/agent_reviews/issues_7_11_hermes_issue10_external_append_rollback.md`: architecture/invariant contract and exact rollback-race attack.
- Issue 10 results, campaign verdict, graph, ledgers, and worktree manifest: record exact bounded evidence.

## Acceptance

1. A forced partial write followed by a non-cooperating append and write failure retains both byte sequences; the original failure propagates, and the advisory consumer records a parse error without admitting a row from the malformed combination.
2. A failure with no external writer still does not truncate; the leftover partial tail is visible as `PARTIAL` to the canonical advisory reader and is not accepted as a candidate row.
3. The test injects an external append after an old-style size snapshot and before an old-style truncate; a temporary destructive-truncate mutant is killed.
4. Existing cooperating two-process serialization and focused Issue 10 regressions pass.
5. `git diff --check`, campaign graph/manifest integrity, and independent read-only review pass.

## Boundaries

No new configuration or schema. No writer routing, candidate generation, strategy, feed, risk, broker/order, or authority changes. A failed append may leave an incomplete tail, which the existing bounded advisory reader must report as `PARTIAL`; no cleanup is attempted in this failure handler. Bypass-writer atomicity and captured/live parity remain UNKNOWN.
