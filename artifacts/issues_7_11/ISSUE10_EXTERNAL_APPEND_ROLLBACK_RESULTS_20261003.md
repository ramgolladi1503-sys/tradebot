# Issue 10 uncoordinated append rollback attack — 2026-10-03

**source_agent:** gsd
**action:** GENERATE_TESTS, GENERATE_PATCH, VERIFY, UPDATE_DOCS
**repository HEAD:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`
**worktree:** `ram/issues-7-11-graph-repair`

## Finding and repair

A cooperating batch append could partially write, then fail. The helper unconditionally truncated to the initial file size. An uncoordinated process can append a complete record during that window because `flock` is advisory; unconditional rollback would erase those foreign bytes.

`core/locked_jsonl.py` now counts bytes written by the current call and truncates only if the current file size still equals `start_offset + own_bytes_written`. If not, it preserves the bytes, logs an error that rollback was skipped, and propagates the original write failure. This prevents the helper from knowingly deleting a concurrent append. A partial fragment from the failed cooperating batch can remain in that mixed-writer failure case; downstream malformed-row diagnostics remain necessary.

## Verification

- `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/test_kite_read_only_observation_runtime.py tests/test_reject_shadow_eval.py tests/core/test_runtime_snapshot_producer.py tests/analytics/test_issues_7_11_eod_row_parity.py` — **53 passed, 1 warning in 4.36s**.
- The tests separately prove (a) the external appended record survives interleaved failure and the rollback-skipped diagnostic is emitted, (b) an ordinary partial write with no external append is truncated, and (c) cooperating writer batches remain serialized across processes.
- `PATH=/tmp/tradebot-test-python-bin:$PATH python3 scripts/verify_issues_7_11_issue10_rollback_mutation.py` — **unconditional_external_append_rollback killed** by the designated external-append regression; temporary-copy mutation did not change checkout hashes. Source SHA-256: `68ce2ff7c4a2dbedc91b8c18b7d783021948c08a0b71d64f398308c7b3cb26fe`; test SHA-256: `1db2bf379e3f7dd3407e3f81710c0dd240d10ea71a5c39f0b0cce426073efee4`.
- A rollback-truncate failure test confirms the original append error is propagated and cleanup failure is logged. Python compilation and `git diff --check` passed.

## Scope and limits

No row schema, routing, decision generation, ranking, authority, or execution behavior changed. No new config or migration. This is defensive rollback behavior only. It does not make non-cooperating writers atomic, prevent arbitrary interleaving, prove external-writer inventory completeness, or establish captured/live parity. Issue 10 and the Issues 7–11 campaign remain open.
