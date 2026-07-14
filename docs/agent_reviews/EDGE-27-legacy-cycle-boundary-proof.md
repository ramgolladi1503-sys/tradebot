# EDGE-27 — Legacy Cycle Boundary Proof

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-27-legacy-cycle-boundary-proof
- decision: ADD_LEGACY_CYCLE_INTERNAL_BOUNDARY_PROOF
- reason: Debug forensics proved that the fast adapter entered its execute step but did not prove completion. The RUN_LEGACY_CYCLE action delegates to the legacy one-cycle method, so that delegated call needs its own proof markers before any behavior change is attempted.
- timestamp: 2026-05-21T20:20:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-27-legacy-cycle-boundary-proof.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: pending
- Branch: edge27-legacy-cycle-boundary-proof
- Scope: add evidence-only boundary proof around the delegated legacy one-cycle call inside FastExecutionEngine.execute.
- Allowed files:
  - core/execution_engine_fast.py
  - core/debug_forensics/flow_contracts.py
  - tests/test_debug_forensics_startup.py
  - docs/agent_reviews/EDGE-27-legacy-cycle-boundary-proof.md
- Forbidden files:
  - strategies/
  - dashboard/
  - core/orchestrator.py
  - core/orchestrator_parts/cycle.py
  - core/execution_engine.py
  - core/kite_depth_ws.py
  - config/
- Forbidden behaviors:
  - No strategy changes.
  - No dashboard changes.
  - No feed changes.
  - No configuration changes.
  - No legacy-cycle behavior changes.
  - No fast-adapter decision behavior changes.
  - No architecture rewrite.

## Scope Guard

Verdict: PASS

Checked:

- RUN_LEGACY_CYCLE still delegates to the same legacy one-cycle method.
- Return value is preserved.
- Exceptions are re-raised after failure evidence is recorded.
- NOOP and SKIP behavior is unchanged.
- Unsupported actions still raise ValueError.
- Debug forensics contract is updated only to include the new proof markers.

Blocking issues: none.

## Grill Me Review

Verdict: PASS_WITH_LIMITATION

Hard challenge:

1. The previous report stopped at the fast adapter execute marker.
   - Reality: the adapter then delegates to the legacy one-cycle method.
   - Fix: add proof around that delegated method call.
2. This PR must not claim to fix the runtime blocker.
   - It only reveals whether the delegated call starts, completes, or fails.
3. This PR must not swallow exceptions.
   - Failed proof is recorded and the original exception is raised.

Remaining limitation:

- A fresh runtime run after merge is required to identify the next boundary inside or after the delegated one-cycle call.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Boundary proof is placed where the delegated call occurs.
2. The fast adapter remains minimal.
3. No new abstraction or rewrite is introduced.
4. The debug forensics contract remains deterministic.
5. The proof names match the real responsibility: FAST_ENGINE_LEGACY_CYCLE.

## GSD Review

Verdict: PASS

Execution plan:

1. Add a local safe recorder in core/execution_engine_fast.py.
2. Add FAST_ENGINE_LEGACY_CYCLE_STARTED before the delegated one-cycle call.
3. Add FAST_ENGINE_LEGACY_CYCLE_COMPLETED after the delegated call returns.
4. Add FAST_ENGINE_LEGACY_CYCLE_FAILED if the delegated call raises, then re-raise.
5. Update the startup flow contract.
6. Add focused forensics tests for legacy-cycle first-missing boundaries.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_debug_forensics_startup.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected behavior:

1. Forensics reports FAST_ENGINE_LEGACY_CYCLE_STARTED as the first missing event after FAST_ENGINE_EXECUTE_STARTED.
2. Forensics reports FAST_ENGINE_LEGACY_CYCLE_COMPLETED as the first missing event after legacy-cycle start.
3. Existing fast-engine evaluate/execute boundary tests still pass.
4. Existing unsafe evidence checks remain intact.
5. Existing timestamp skew behavior remains intact.

## Acceptance Proof

Acceptance criteria:

1. Agent Review Evidence Gate passes.
2. Code Excellence Gates pass.
3. Unit tests pass.
4. The next post-merge runtime report identifies whether the delegated legacy one-cycle call started, completed, or failed.

## Runtime Proof Required After Merge

After merge, run:

```bash
git checkout main
git pull --ff-only origin main
python scripts/debug_forensics.py --profile startup
```

Expected output should now reach or stop at one of these useful boundaries:

```text
FAST_ENGINE_LEGACY_CYCLE_STARTED
FAST_ENGINE_LEGACY_CYCLE_COMPLETED
FAST_ENGINE_EXECUTE_COMPLETED
RUNTIME_STATUS_WRITE_COMPLETED
```

## What This PR Does Not Prove

1. It does not prove the delegated one-cycle implementation is correct.
2. It does not fix the delegated one-cycle implementation.
3. It does not change strategy behavior.
4. It does not change feed behavior.
5. It does not change dashboard behavior.
6. It does not prove profitability.
7. It does not replace the final architecture documentation PR.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21


## High-Risk Path Review

N/A
