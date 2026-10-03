# Hermes Addendum — Issue 10 rollback under an uncoordinated append

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
**title:** Preserve external candidate telemetry when a cooperating append fails
**scope:** `core/locked_jsonl.py` rollback only; no new writer or routing behavior.

## Finding

The shared JSONL helper holds an advisory lock and, after a write failure, unconditionally truncates the file to the pre-batch size. Advisory locks coordinate only cooperating writers. If a bypass writer appends after the helper's partial write and before its failure, unconditional truncation can delete the bypass writer's complete row. This is a destructive failure mode inside the helper, independent of whether external writers are authorized or supported.

## Contract

1. Preserve serialized append behavior for cooperating writers.
2. Never truncate the shared append file from the failure handler. A separate uncoordinated writer can append after any size check and before `ftruncate`; advisory locks cannot make the check-and-truncate sequence atomic against bypass writers.
3. On write failure, emit a diagnostic identifying that rollback was intentionally skipped and propagate the original write failure. Any bytes already appended by this call remain in the file.
4. Existing downstream readers must reject or surface malformed/incomplete JSONL records; they must not count a partial line as a valid decision.
5. Do not claim bypass writers are serialized or that a failed batch is atomic. A bypass writer may append behind this call's unterminated prefix, leaving concatenated malformed JSONL bytes. The traced advisory consumer must record a parse error and admit no candidate from that malformed line. Avoiding silent foreign-record deletion takes precedence over in-place cleanup. A separately designed canonical rewrite/repair process would need its own Hermes contract and must not run inside this append failure path.

## Acceptance proof

- Inject a short partial write, append an external complete JSONL record through a separate descriptor that ignores flock, then fail the original batch.
- Preserve the independent re-review reproduction of an append after the old size snapshot but before its truncate; verify the replacement implementation has no post-failure size-check/truncate path.
- Verify the helper propagates the write error, preserves all bytes, and logs that cleanup was skipped.
- Verify the actual advisory consumer records a parse error and admits zero rows from concatenated malformed bytes.
- Verify downstream JSONL parsing reports the retained partial record instead of accepting it as a valid decision.
- Preserve existing cooperating two-process serialization test and Issue 10 mutation harness.
- Run focused tests and static checks; captured/live parity remains UNKNOWN.

## Safety

Telemetry-only append behavior. No broker/order calls, feed/strategy/risk changes, candidate generation, path routing, or authority changes. Evidence stays read-only. No new configuration or migration.
