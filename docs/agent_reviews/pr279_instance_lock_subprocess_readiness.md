# PR 279 Agent Review Evidence — Instance Lock Subprocess Readiness Test

mode: TEST
candidate_id: PR279_INSTANCE_LOCK_SUBPROCESS_READINESS
candidate_status: documentation_evidence
rank: 0
rank_reason: process_gate_evidence_only
liquidity_score: 0
risk_score: 0
execution_score: 0
data_quality_penalty: 0
decision: STABILIZE_INSTANCE_LOCK_READINESS_TEST
reason: The full local pytest suite had one remaining failure because the instance-lock test called communicate on a deliberately sleeping child process when readiness was not observed fast enough.
timestamp: 2026-05-26T09:20:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: docs/agent_reviews/pr279_instance_lock_subprocess_readiness.md

## Agent Work Contract

- PR scope: stabilize `tests/test_instance_lock.py` subprocess readiness handling.
- Changed files: `tests/test_instance_lock.py` and this evidence document.
- No production lock behavior is changed.
- No broker, execution, strategy, WebSocket, dashboard, or runtime behavior is touched.

## Scope Guard

- In scope: make the test wait for the child readiness line and terminate the child safely on failure or teardown.
- Out of scope: changing `core/instance_lock.py`, changing runtime lock paths, changing live startup behavior, or weakening single-instance protection.
- Files changed list: `tests/test_instance_lock.py`, `docs/agent_reviews/pr279_instance_lock_subprocess_readiness.md`.
- Files not touched list: `core/instance_lock.py`, broker adapters, execution router, live runner scripts, dashboard paths.

## Grill Me Review

- Question: Why not change production lock code?
- Answer: The production lock already acquires a POSIX lock, writes holder payload, and releases on teardown. The observed failure came from the test trying to `communicate` with a child that intentionally sleeps.
- Question: Could this hide a lock failure?
- Answer: No. The test still requires the child to print `ACQUIRED`, then verifies a second `InstanceLock.acquire()` returns false and reports the child PID as holder.
- Question: What failure remains visible?
- Answer: If the child cannot acquire the lock or the second acquisition does not block, the test still fails with explicit stdout and stderr evidence.

## Hermes Review

- Scope status: pass.
- Boundary violations: none.
- Production behavior change: none.
- Verdict: test stabilization only.

## GSD Review

- purpose: remove subprocess timeout flake from the single-instance lock test.
- scope: use non-blocking readiness read, keep explicit second-acquire assertion, and terminate child process safely.
- files_changed: test fixture and agent review evidence.
- tests_or_reason_not_required: run `python -m pytest -q tests/test_instance_lock.py` and full `python -m pytest -q tests`.
- evidence: local full-suite run had 3398 passes and one failure in `test_instance_lock_blocks_second_instance` caused by `TimeoutExpired` while the child had already printed `ACQUIRED`.
- risks: uses POSIX `select`, matching the POSIX-only `fcntl` lock implementation being tested.
- next_pr: none for this fix.

## QA / Safety Review

- Safety boundary: no order action, no broker call, no live execution behavior.
- The test still verifies single-instance blocking.
- The patch does not weaken live startup lock behavior.
- The patch avoids leaving a child process alive after failure.

## Acceptance Proof

Planned validation commands:

```bash
python -m pytest -q tests/test_instance_lock.py
python -m pytest -q tests
```

Expected proof:

- Child process prints `ACQUIRED` within the readiness window.
- Parent process fails to acquire the same lock while child holds it.
- Holder PID reported by the lock equals the child process PID.
- Full local pytest no longer fails on subprocess readiness timeout.

## Runtime Proof Required After Merge

- Pull latest `main` after merge.
- Re-run `python -m pytest -q tests/test_instance_lock.py` locally.
- Re-run clean full suite before live validation.
- Run live validation only after tests are green.

## What This PR Does Not Prove

- It does not prove live broker connectivity.
- It does not prove market feed health.
- It does not prove order execution behavior.
- It does not change production instance-lock semantics.

## Human Approval

- Human approval required before merge.
- Reviewer should verify the patch is limited to test subprocess readiness and evidence documentation.

## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
