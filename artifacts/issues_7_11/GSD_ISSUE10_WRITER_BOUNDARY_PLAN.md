# GSD Plan — Issue 10 concurrent writer serialization

**source_agent:** gsd
**action:** PLAN_PR, UPDATE_DOCS
**title:** Serialize canonical candidate-decision append batches
**scope:** Execute only `docs/agent_reviews/issues_7_11_hermes_issue10_writer_boundary.md`.

## Files

- `core/locked_jsonl.py`: provide the one shared file-descriptor lock, complete batch append, and rollback implementation.
- `core/kite_read_only_observation_runtime.py` and `core/reject_shadow.py`: route the observer and per-desk candidate-decision writers through the shared helper.
- `tests/test_kite_read_only_observation_runtime.py`: launch two processes through the canonical helper and verify complete, contiguous batches.
- `tests/core/test_runtime_snapshot_producer.py`: verify an unregistered configured desk reads only its own path and does not fall through to `DEFAULT`.
- `scripts/verify_issues_7_11_issue10_writer_mutation.py`: remove the exclusive lock in a temporary copy and require the designated multiprocess regression to fail.
- `artifacts/issues_7_11/ISSUE10_WRITER_MUTATION_RESULTS_20261003.md`: preserve exact test, mutation, hash, and scope evidence.
- `docs/agent_reviews/issues_7_11_hermes_issue10_writer_boundary.md`: authorize the exact narrow serialization contract.
- `artifacts/issues_7_11/defect_graph.json` and `.md`: record the shared call graph, patch, and bounded proof.
- `artifacts/issues_7_11/INDEPENDENT_VERIFICATION.md`: record verification limits without claiming a fresh independent review.
- `artifacts/issues_7_11/FINAL_VERDICT.json`: keep Issue 10 captured/live parity and campaign acceptance open.

## Plan and acceptance

1. Route both existing candidate decision writers through `core.locked_jsonl.append_jsonl_batch`; do not change row conversion, path selection, ranking, or decision generation.
2. Acquire `fcntl.flock(LOCK_EX)` on the destination file descriptor for the entire serialized batch and flush before release.
3. On write failure, truncate only this cooperating writer's partial batch to its starting offset while lock is held, then re-raise.
4. Start two independent processes against one temporary destination; verify all 64 records parse and each 32-row batch remains contiguous.
5. Run the new focused test, lock-removal mutant, unknown-desk regression, and observer/reject-shadow/advisory producer regression. Validate graph JSON/endpoints and `git diff --check`.
6. Keep external writers that bypass the helper and captured/live parity UNKNOWN.

## Authority

`read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`. This helper appends existing candidate telemetry only; it does not append evidence, create candidates, or affect execution. No broker/order, paper/live, feed, strategy, risk, config, or token-universe authority changes.
