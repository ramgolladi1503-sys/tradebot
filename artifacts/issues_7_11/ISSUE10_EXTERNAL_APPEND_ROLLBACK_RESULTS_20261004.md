# Issue 10 external append rollback attack — revised no-truncate contract — 2026-10-04

**source_agent:** gsd
**action:** GENERATE_TESTS, GENERATE_PATCH, VERIFY, UPDATE_DOCS
**repository HEAD:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**worktree:** `ram/issues-7-11-graph-repair`

## Independent finding and revised repair

The first defensive rollback used `fstat()` followed by `ftruncate()`. A fresh reviewer identified a time-of-check/time-of-use race: a bypass writer could append after the size check and before truncation, and the truncate could delete its record. The reviewer rejected the prior protection claim.

Following the revised Hermes contract, `core/locked_jsonl.py::append_jsonl_batch` now performs no in-place truncate or post-failure size check. On write failure it logs that rollback was skipped and re-raises the original exception. The cooperating-writer `flock` still serializes users of this helper.

A failed write can leave this call's partial bytes. A bypass writer can append behind that prefix and the combined bytes may no longer represent a valid foreign JSONL row. The actual advisory consumer is tested to report `parse_error` and admit zero rows from that malformed line. This prevents silent acceptance but cannot salvage the foreign row or make bypass writers atomic.

## Verification

- `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_kite_read_only_observation_runtime.py tests/test_reject_shadow_eval.py tests/core/test_runtime_snapshot_producer.py tests/analytics/test_issues_7_11_eod_row_parity.py` — **53 passed, 1 warning in 10.25s**.
- Failure-path tests verify the original exception is propagated; a foreign append survives; a no-external-writer partial tail is reported as `PARTIAL`; the advisory parser reports `parse_error` and yields zero rows for concatenated malformed bytes; and `ftruncate` is never called.
- `PATH=/tmp/tradebot-test-python-bin:$PATH python3 scripts/verify_issues_7_11_issue10_rollback_mutation.py` — **destructive external-append rollback mutant killed** in a temporary copy. Final source SHA-256: `2c7812f9e51b704ea90ac00672dc0cd694c714f81f7fb1511e1055e749e1d142`; test SHA-256: `daf1ed330feca4dfcb80740874fba1c2f4bf1d9bc403eb06f375e63a689127a2`.
- `python3 -m py_compile` and `git diff --check` passed.
- Independent read-only review found no remaining data-loss blocker in the revised append failure handler and confirmed the consumer-level malformed-line assertion. Reviewer limit: foreign-row salvage/atomicity is not proven.

## Scope and limits

No candidate schema, routing, ranking, execution, strategy, feed, risk, broker, order, authority, configuration, or migration behavior changed. The change only prevents destructive rollback by this helper. External writers can still interleave, and a partial record may make a concurrent foreign row unusable. Captured/live parity and external-writer inventory remain UNKNOWN. Overall Issues 7–11 campaign acceptance remains OPEN.
