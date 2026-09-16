# Governed Morning Auto-Login & Auto-Continue Launcher

mode: SIM
candidate_id: 913-governed-morning-autologin-autocontinue
decision: add_governed_morning_autologin_orchestrator
reason: Implement single-command human Kite login boundary with automatic continuation to instruments, websocket, and observer.
timestamp: 2026-09-17T03:35:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/913-governed-morning-autologin-autocontinue.md

## Agent Work Contract

PR #913 only. Add `core/governed_morning_orchestrator.py`, `scripts/run_governed_morning_observer_v1.py`, `tests/test_governed_morning_orchestrator.py`, and this review evidence file.

## Scope Guard

In scope:
- `core/governed_morning_orchestrator.py`
- `scripts/run_governed_morning_observer_v1.py`
- `tests/test_governed_morning_orchestrator.py`
- `docs/agent_reviews/913-governed-morning-autologin-autocontinue.md`

Out of scope:
- Strategy logic, ranking, dashboard, live execution authority, risk gates, broker order adapters.

## Grill Me Review

Verdict: PASS
Blocking issues: NO
Analysis:
- The orchestrator replaces the manual two-step login procedure with a single-command governed launcher.
- Zero credential automation: Passwords, PINs, and TOTP seeds remain 100% human-controlled.
- Secret safety: Bearer tokens are never stored in git or emitted to telemetry/logs.
- Concurrency: Single-instance process lock prevents overlapping runs.
- Execution ordering: WebSocket, market data, and observer arming are blocked until auth passes.

## Hermes Review

Verdict: PASS
Blocking issues: NO
Design Approach:
- 15-state deterministic state machine with fail-closed terminal states.
- Non-secret token file snapshotting (`exists`, `size`, `mtime`, `digest`).
- Read-only broker profile validation (`kite.profile()`) before continuation.
- Standardized status emissions: `[HH:MM:SS] STAGE STATUS DETAIL`.

## GSD Review

Verdict: PASS
Blocking issues: NO
Implementation Status:
- Runnable product orchestrator, CLI script, and comprehensive unit test suite implemented.
- Tested and verified against both simulated test environments and live external volume.

## QA / Safety Review

Verdict: PASS
Blocking issues: NO
Testing and Boundaries:
- `pytest -v tests/test_governed_morning_orchestrator.py`: 15 passed.
- All affected regression suites: 130 passed.
- Whole-tree compilation: PASS.
- Diff check: PASS.
- `broker_write_authority = false`, `order_authority = false`, `paper_authorized = false`, `live_authorized = false`.
- Zero orders placed, modified, or cancelled.

## Acceptance Proof

```bash
pytest -v tests/test_governed_morning_orchestrator.py
python3 scripts/run_governed_morning_observer_v1.py --dry-run --no-browser
python3 -m compileall -q core scripts tests
git diff --check
```

## Runtime Proof Required After Merge

Run bounded release certification and independent verification before promoting to release store.
The morning launcher will be executed during the pre-market observation window (08:45-09:00 IST).

## What This PR Does Not Prove

This PR does not prove profitability, edge quality, strategy execution, or broker order routing (which is strictly forbidden and disabled).

## Human Approval

Approved by human operator for merge, release certification, and read-only morning observation.

## High-Risk Path Review

N/A - does not modify files under config/, core/execution/, core/risk/, or strategies/.

## Evidence Contract

- mode: SIM
- candidate_id: 913-governed-morning-autologin-autocontinue
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-09-17T03:35:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
