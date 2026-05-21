# EDGE-26 — Fast Engine Cycle Boundary Proof

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-26-fast-engine-cycle-boundary-proof
- decision: ADD_FAST_ENGINE_CYCLE_INTERNAL_BOUNDARY_PROOF
- reason: The debug forensics report reached RUNTIME_STATUS_WRITE_ATTEMPTED but did not prove RUNTIME_STATUS_WRITE_COMPLETED. Code inspection showed that this span actually wraps fast-engine evaluate and execute, so the boundary must be split before diagnosing runtime status writing.
- timestamp: 2026-05-21T20:00:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-26-fast-engine-cycle-boundary-proof.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: pending
- Branch: edge26-fast-engine-cycle-boundary-proof
- Scope: add evidence-only internal boundary proof for fast-engine evaluate and execute inside the startup/live-monitoring cycle.
- Allowed files:
  - core/orchestrator_parts/cycle.py
  - core/debug_forensics/flow_contracts.py
  - tests/test_debug_forensics_startup.py
  - docs/agent_reviews/EDGE-26-fast-engine-cycle-boundary-proof.md
- Forbidden files:
  - strategies/
  - dashboard/
  - core/execution_engine.py
  - core/order_reconciliation_daemon.py
  - core/kite_depth_ws.py
  - config/
- Forbidden behaviors:
  - No strategy changes.
  - No dashboard changes.
  - No feed/WebSocket changes.
  - No broker/session behavior changes.
  - No fast-engine decision behavior changes.
  - No order placement or cancellation behavior changes.
  - No architecture rewrite.

## Scope Guard

Verdict: PASS

Checked:

- The fast cycle still calls `engine.evaluate()` then `engine.execute(decision)` in the same order.
- Return values are preserved.
- Exceptions are re-raised after evidence is recorded.
- The patch only adds proof events around existing calls.
- Debug forensics contract is updated to expect those proof events.
- Tests prove the new first-missing boundary resolution.

Blocking issues: none.

## Grill Me Review

Verdict: PASS_WITH_LIMITATION

Hard challenge:

1. The prior event name suggested a runtime status write problem.
   - Reality: the event span wrapped fast-engine evaluate and execute.
   - Fix: split the span into evaluate and execute proof events.
2. This PR must not claim to fix the blocker.
   - It only proves which sub-step is missing or failing.
3. This PR must not hide exceptions.
   - Failed evaluate/execute proof is recorded, then the original exception is raised.

Remaining limitation:

- A follow-up runtime run is required after merge to identify whether the system stops before evaluate, inside evaluate, inside execute, or after execute.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Boundary proof remains inside the cycle layer where the calls occur.
2. Debug forensics contract remains explicit and deterministic.
3. No new abstraction is introduced.
4. No broad refactor is introduced.
5. The proof events are named by actual subsystem responsibility: FAST_ENGINE_EVALUATE and FAST_ENGINE_EXECUTE.

## GSD Review

Verdict: PASS

Execution plan:

1. Add `FAST_ENGINE_EVALUATE_STARTED` and `FAST_ENGINE_EVALUATE_COMPLETED` around `engine.evaluate()`.
2. Add `FAST_ENGINE_EXECUTE_STARTED` and `FAST_ENGINE_EXECUTE_COMPLETED` around `engine.execute(decision)`.
3. Add failed events for evaluate and execute exceptions.
4. Keep `RUNTIME_STATUS_WRITE_ATTEMPTED` and `RUNTIME_STATUS_WRITE_COMPLETED` for backward-compatible outer cycle proof.
5. Update startup flow contract.
6. Add tests for first missing evaluate and execute boundaries.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_debug_forensics_startup.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected behavior:

1. Forensics reports `FAST_ENGINE_EVALUATE_STARTED` as the first missing event after `RUNTIME_STATUS_WRITE_ATTEMPTED`.
2. Forensics reports `FAST_ENGINE_EXECUTE_STARTED` as the first missing event after evaluate completion.
3. Existing malformed/mixed-run/unsafe evidence validation stays intact.
4. Minor timestamp skew remains a warning.

## Acceptance Proof

Acceptance criteria:

1. Agent Review Evidence Gate passes.
2. Code Excellence Gates pass.
3. Unit tests pass.
4. The next post-merge runtime forensics report gives a more precise fast-engine boundary than `RUNTIME_STATUS_WRITE_COMPLETED`.

## Runtime Proof Required After Merge

After merge, run:

```bash
git checkout main
git pull --ff-only origin main
python scripts/debug_forensics.py --profile startup
```

Expected output must include one of these useful boundaries:

```text
FAST_ENGINE_EVALUATE_STARTED
FAST_ENGINE_EVALUATE_COMPLETED
FAST_ENGINE_EXECUTE_STARTED
FAST_ENGINE_EXECUTE_COMPLETED
RUNTIME_STATUS_WRITE_COMPLETED
```

The report should no longer leave the whole fast-engine span hidden behind only `RUNTIME_STATUS_WRITE_ATTEMPTED`.

## What This PR Does Not Prove

1. It does not prove fast-engine evaluate is correct.
2. It does not prove fast-engine execute is correct.
3. It does not fix a runtime failure.
4. It does not change strategy behavior.
5. It does not change feed behavior.
6. It does not change dashboard behavior.
7. It does not prove profitability.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21
