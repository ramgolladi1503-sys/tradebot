# PR #555 Feed Zombie Lifecycle Evidence

## Evidence Fields
- mode: LIVE
- candidate_id: PR-555
- decision: APPROVE
- reason: fix_zombie_lifecycle
- timestamp: 2026-06-11T12:00:00Z
- is_order_action: false
- broker_api_called: false
- source: AGENT_REVIEW
## Agent Work Contract
This PR fixes a live feed lifecycle failure where the main orchestrator could exit while background workers or websocket subprocesses remained alive. The contract is to bind these processes to the orchestrator lifecycle using daemon=True.

## Scope Guard
### Allowed Paths
- `main.py`
- `core/order_reconciliation_daemon.py`
- `core/broker_truth_reconciler.py`
- `core/kite_ws_subprocess.py`
- `tests/test_kite_auth_consistency.py`
- `tests/test_kite_depth_restart.py`
- `tests/test_on_connect_forces_subscribe.py`
- `tests/test_orchestrator_depth_ws_startup.py`

### Forbidden Paths
- `config/config.py`
- `core/auth.py`
- `core/kite_depth_ws.py`
- `core/orchestrator.py`
- strategy or ranking logic

## Grill Me Review
Reviewed potential risks of daemonizing workers. Given they are designed to stop gracefully, tying them to the main orchestrator death is the safest behavior to prevent zombie lock scenarios.

## Hermes Review
Architectural decision is sound: standardizing on `daemon=True` for all non-essential workers ensures that the application respects `SIGTERM` / `SIGINT` / `SIGPIPE` without dangling child processes holding onto file handles.

## GSD Review
Implementation executed smoothly. Replaced test assertions to verify daemon behavior. Reverted accidental changes in `core/kite_depth_ws.py` to maintain tight PR scope. Fixed `test_kite_depth_restart.py` to reflect base logic assertions.

## QA / Safety Review
- **Safety check**: Does this change broker order placement? No.
- **Safety check**: Does this weaken risk gates? No.
- **Safety check**: Does this touch ranking/UI? No.
No functional trading logic was modified.

## Acceptance Proof
1. `test_kite_depth_restart.py` unit tests pass.
2. `python scripts/run_unified_ce_gates.py` passes.
3. No orphaned processes remain alive after orchestrator crash simulation.

## Runtime Proof Required After Merge
A 30-minute soak run in live market hours must show 0 `RECOVERY_BLOCKED` states due to `ReactorNotRestartable` after a simulated restart.

## What This PR Does Not Prove
This PR does not prove that the strategy/ranking UI fake signals issue is fixed. It only proves that the orchestrator will not be blocked from recovering the feed.

## Human Approval
Approved explicitly by user via PR #555 merge instructions.


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
