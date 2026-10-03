# Hermes Addendum — Issue 10 canonical writer serialization

**source_agent:** hermes
**action:** MAP_WORKFLOW, DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**title:** Serialize Issue 10 candidate-decision writes across observer processes
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Repository evidence

- `run_observation` is called from three repository entry paths: `scripts/run_kite_read_only_observation_v1.py`, `scripts/morning_readonly_observer.py`, and `core/read_only_live_pipeline.py`.
- `main.py` holds the governed `InstanceLock` for its normal PAPER/LIVE runtime, but these read-only launch paths do not all run through that lock. Separate processes can therefore converge on the same writer function and potentially the same session output path.
- `core/reject_shadow.py` is a second repository writer for `logs/desks/<desk>/candidate_decisions.jsonl`; it can converge with the observer writer when roots are configured to the same path.
- Both in-repository candidate-decision writers now route through `core/locked_jsonl.py::append_jsonl_batch`, the single lock owner.
- The Issue 10 reader's descriptor checks protect snapshot reads from in-place mutation; they do not serialize concurrent writers.

## Contract and decision

1. Serialize every in-repository candidate-decision append batch with an exclusive advisory lock on the canonical JSONL file descriptor. Both known writers share this implementation.
2. Preserve the existing row shape, ordering within a batch, newline termination, routing, and strict reader behavior. Do not mirror rows or introduce a second writer.
3. Hold the lock through the complete batch write and flush. If a write fails, truncate back to the pre-batch byte offset while still holding the lock, then propagate the failure.
4. Verify with two separate writer processes using the canonical writer helper; all records must parse, both complete batches must be present, and batch rows must remain contiguous.
5. Desk routing preserves an explicitly configured unknown desk ID in its own path; only absent/empty `DESK_ID` uses the repository's explicit `DEFAULT` configuration. A row under `DEFAULT` must not be consumed for an unknown configured desk.
6. This proves serialization only among the two cooperating in-repository callers using this helper. External writers that bypass it and captured/live parity remain UNKNOWN.

## Safety boundary

No decision-generation or execution authority changes. No broker/order calls, paper/live authority, feed, strategy, risk, directory, or token-universe changes. `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false` for evidence contracts. The append is limited to the existing candidate telemetry streams.
