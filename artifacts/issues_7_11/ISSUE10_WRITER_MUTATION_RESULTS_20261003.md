# Issue 10 shared writer mutation results

**source_agent:** gsd
**action:** VERIFY, UPDATE_DOCS
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**branch:** `ram/issues-7-11-graph-repair`

## Contract and writer coverage

The observer session-ledger writer and `core.reject_shadow` desk-ledger writer both call `core.locked_jsonl.append_jsonl_batch`. The helper takes an exclusive `flock` on the destination file, appends serialized rows under the lock, and rolls back bytes from a failed batch before unlocking.

## Tests

- `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_kite_read_only_observation_runtime.py::test_candidate_decision_batches_are_serialized_across_processes` → **1 passed**. Two child processes wait on a shared start marker, force 1 KB writes with a short delay between syscalls, and write 32 large records each. All 64 records parse, both index sets are complete, and each writer's batch remains contiguous.
- `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_kite_read_only_observation_runtime.py tests/test_reject_shadow_eval.py tests/core/test_runtime_snapshot_producer.py tests/analytics/test_issues_7_11_eod_row_parity.py` → **42 passed, 1 warning**.
- Current shared-writer tree broad suite → **8672 passed, 9 skipped, 29 deselected, 1474 warnings in 949.64s; exit code 0**. Exact command and exclusions remain in `FINAL_VERDICT.json`.

## Mutation

`python3 scripts/verify_issues_7_11_issue10_writer_mutation.py` removed the exclusive lock from a temporary copy of `core/locked_jsonl.py` and ran the concurrent-process regression. The mutant was killed by the intended test. The runner rejects timeout/collection errors and verified the checkout SHA-256 values were unchanged:

- `core/locked_jsonl.py`: `609cc270757f743c695fe9e8e6f030685c24c6bfe0b6c9227103b9513a456ec2`
- `tests/test_kite_read_only_observation_runtime.py`: `e5781456fadafd9ba20d71cf0e6cf60e74c778b9f8b3280a01144c2985c20ab5`

## Limits

This verifies only cooperating in-repository writers using the shared helper. External writers that bypass it, captured/live parity, and full campaign acceptance remain unverified/open. No candidate logic, feed/risk gate, order/broker behavior, or execution authority changed.
