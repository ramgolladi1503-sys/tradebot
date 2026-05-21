# EDGE-28 — Main Post-DB Boundary Proof

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-28-main-post-db-boundary-proof
- decision: ADD_MAIN_POST_DB_STARTUP_BOUNDARY_PROOF
- reason: The latest debug forensics run proved DB readiness completed but did not prove orchestrator construction entry. Code inspection showed multiple real startup steps between DB readiness and orchestrator construction, so this PR adds direct lifecycle proof around those steps.
- timestamp: 2026-05-21T20:45:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-28-main-post-db-boundary-proof.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: pending
- Branch: edge28-main-post-db-boundary-proof
- Scope: add direct evidence-only boundaries in main.py between DB readiness and orchestrator construction.
- Allowed files:
  - main.py
  - core/debug_forensics/flow_contracts.py
  - tests/test_debug_forensics_startup.py
  - docs/agent_reviews/EDGE-28-main-post-db-boundary-proof.md
- Forbidden files:
  - strategies/
  - dashboard/
  - core/orchestrator.py
  - core/orchestrator_parts/cycle.py
  - core/execution_engine_fast.py
  - core/execution_engine.py
  - core/kite_depth_ws.py
  - config/
- Forbidden behaviors:
  - No strategy changes.
  - No dashboard changes.
  - No feed changes.
  - No configuration changes.
  - No orchestrator behavior changes.
  - No readiness decision behavior changes.
  - No architecture framework or import-hook probe.

## Scope Guard

Verdict: PASS

Checked:

- The patch adds direct lifecycle markers only.
- Existing startup checks still run in the same order.
- Existing returns on startup security and readiness abort paths are preserved.
- Existing exception behavior is preserved for session guard and orchestrator construction.
- No generic probe framework is introduced.
- Debug forensics contract is updated only to include the direct post-DB proof markers.

Blocking issues: none.

## Grill Me Review

Verdict: PASS_WITH_LIMITATION

Hard challenge:

1. The previous report stopped at DB_READY_COMPLETED.
   - Reality: main.py has several real steps before orchestrator construction.
   - Fix: add direct proof around those steps.
2. This PR must not claim to fix the startup issue.
   - It only identifies which post-DB step blocks or returns.
3. A generic import-hook probe would be overengineering.
   - This PR uses explicit boring markers in main.py instead.

Remaining limitation:

- A fresh runtime run after merge is required to identify the exact post-DB boundary.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Boundary proof is placed directly where the startup work occurs.
2. The flow contract remains deterministic.
3. The report still fails closed on missing expected proof.
4. The patch avoids new abstractions.
5. The evidence remains read-only and diagnostic.

## GSD Review

Verdict: PASS

Execution plan:

1. Add a small local lifecycle recorder in main.py.
2. Add markers after DB readiness and before startup security.
3. Add markers around startup security, env check, trade log readiness, session guard, readiness resolution, poll interval resolution, and orchestrator construction call.
4. Update the startup flow contract.
5. Update focused forensics tests to prove the new first-missing boundaries.
6. Add mandatory agent-review evidence.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_debug_forensics_startup.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected behavior:

1. Forensics reports POST_DB_STARTUP_STARTED as the first missing event after DB_READY_COMPLETED if post-DB proof is absent.
2. Forensics reports STARTUP_SECURITY_CALLING after POST_DB_STARTUP_STARTED if security call proof is absent.
3. Forensics reports ORCHESTRATOR_INIT_CALLING after post-DB checks complete if construction call proof is absent.
4. Existing fast-engine and legacy-cycle boundary tests still pass.
5. Existing unsafe evidence checks remain intact.

## Acceptance Proof

Acceptance criteria:

1. Agent Review Evidence Gate passes.
2. Code Excellence Gates pass.
3. Unit tests pass.
4. The next post-merge runtime report identifies the exact post-DB startup boundary instead of stopping vaguely between DB readiness and orchestrator construction.

## Runtime Proof Required After Merge

After merge, run:

```bash
git checkout main
git pull --ff-only origin main
python scripts/debug_forensics.py --profile startup
```

Expected output should now reach or stop at one of these useful boundaries:

```text
POST_DB_STARTUP_STARTED
STARTUP_SECURITY_CALLING
STARTUP_SECURITY_COMPLETED
STARTUP_TRADE_LOG_READY_COMPLETED
SESSION_GUARD_COMPLETED
READINESS_GATE_RESOLUTION_COMPLETED
ORCHESTRATOR_INIT_CALLING
ORCHESTRATOR_INIT_ENTERED
```

## What This PR Does Not Prove

1. It does not prove startup security is correct.
2. It does not prove readiness logic is correct.
3. It does not fix any startup blocker.
4. It does not change strategy behavior.
5. It does not change feed behavior.
6. It does not change dashboard behavior.
7. It does not prove profitability.
8. It does not replace the final architecture documentation PR.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21
