# PR Review: Feed Subprocess Isolation (MOD-1)

## Agent Work Contract
source_agent: GSD
action: GENERATE_PATCH
title: feat(feed): isolate KiteTicker websocket in subprocess
scope: core/kite_depth_ws.py, core/orchestrator.py, core/kite_ws_subprocess.py, tests/test_kite_depth_ws_stability.py
requested_paths: core/kite_depth_ws.py, core/orchestrator.py, core/kite_ws_subprocess.py, tests/test_kite_depth_ws_stability.py
allowed_paths: core/kite_depth_ws.py, core/orchestrator.py, core/kite_ws_subprocess.py, tests/test_kite_depth_ws_stability.py, docs/agent_reviews/feat-kite-ws-subprocess.md
forbidden_paths: main.py, config/*, credentials.py, .env, core/execution*, core/order*, core/broker*
expected_tests: test_kite_depth_ws_stability.py
acceptance_proof: Tests run successfully and os._exit(1) is proven to be restricted to child process via feature flags.

## Scope Guard
We only changed what was strictly necessary for the MOD-1 architectural shift. We did not touch `config.py` live mode settings, we did not touch broker code, and we did not enable live execution. The feature is behind a feature flag (`FEED_USE_SUBPROCESS`) which is `False` by default.

## Grill Me Review
**Q: Could the orchestrator crash if the feature flag is accidentally enabled?**
A: `os._exit(1)` has been explicitly constrained behind a `multiprocessing.current_process().name != "MainProcess"` check. This is an ironclad guarantee that the main process cannot be killed by this code path, even if `FEED_USE_SUBPROCESS` is flipped on.

## Hermes Review
The architecture shifts from in-process Twisted reactor stop/start cycles to a supervised `multiprocessing.Process` pool. This correctly mitigates `ReactorNotRestartable` because Twisted is never restarted; the entire process dies and is respawned. 

## GSD Review
- **What changed?** Created `core/kite_ws_subprocess.py`, updated `core/orchestrator.py` to optionally spawn it based on `FEED_USE_SUBPROCESS` flag, and updated `core/kite_depth_ws.py` to use `os._exit(1)` if in a child process. Modified tests for WS1006 recovery budget escalation.
- **Why does this move safety/stability forward?** Eliminates the fatal permanent crash on WebSocket drops when a twisted reactor is un-restartable.
- **What did not change?** Live orders, read-only feeds, logic in Phase 2, old in-process restart path (retained and defaulted to).
- **What tests prove it?** `test_kite_depth_ws_stability.py` all passing.

## QA / Safety Review
```text
mode=SIM
candidate_id=MOD-1
decision=ISOLATE_WEBSOCKET_IN_SUBPROCESS
reason=Reactor cannot restart in twisted
timestamp=2026-06-11
is_order_action=false
broker_api_called=false
source=GSD
read_only=true
allowed_for_live_execution=false
append=false
```

## High-Risk Path Review
`core/kite_depth_ws.py` and `core/orchestrator.py` are high risk. We mitigated risk by keeping the old in-process restart path intact as the default. The new subprocess path is isolated and feature-flagged. `os._exit` includes safety guard rails against MainProcess execution.

## Acceptance Proof
1. Tests pass.
2. In-process restart is the default.
3. Subprocess path uses `os._exit(1)` ONLY in a child process.
4. Old behavior remains structurally identical when flag is False.

## Runtime Proof Required After Merge
A supervised live soak in paper mode must be run with `FEED_USE_SUBPROCESS=True` for a full 6-hour Indian market session to prove 5-hour stability. 

## What This PR Does Not Prove
This PR does NOT prove 5-hour stability yet. It only implements the MOD-1 candidate architecture.

## Human Approval
Requires explicit human approval to merge.
