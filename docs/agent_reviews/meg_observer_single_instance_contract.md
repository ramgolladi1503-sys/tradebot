# MEG Read-Only Observer Single-Instance Contract

## Hermes Work Contract

- `source_agent: hermes`
- `action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS`
- `title: Prevent overlapping MEG read-only sessions from contending on shared runtime storage`
- `scope: Enforce one active Market Event Graph read-only observation run per shared LOCKS_ROOT. Acquire the lock only after static/launch preflight passes and only for an actual capture; leave preflight commands unaffected. Keep the guard independent from the LIVE/PAPER Kite execution lock.`
- `requested_paths: core/instance_lock.py; scripts/run_market_event_graph_live_session_v1.py; tests/test_instance_lock.py; tests/test_run_market_event_graph_live_session_v1.py; docs/agent_reviews/meg_observer_single_instance_contract.md`
- `allowed_paths: exactly the requested paths`
- `forbidden_paths: broker/order/execution/risk/strategy code; credential/environment files; main.py and live launcher behavior; broker calls; runtime artifacts; unrelated files`
- `expected_tests: same-process and cross-process lock exclusion; stale metadata cleared while lock-file inode remains stable; second observation is rejected before creating capture output; lock releases after child exits; static and launch preflight-only paths do not acquire the lock.`
- `acceptance_proof: at most one actual MEG capture can hold the shared lock; a contending capture returns a stable fail-closed blocker and does not create a session directory; lock release allows a subsequent capture; LIVE/PAPER lock path and behavior are unchanged; all tests remain read-only with no broker or order calls.`

## Design and Boundaries

The LIVE/PAPER `kite_session.lock` protects execution-bearing application processes. A MEG capture is intentionally SIM/read-only and uses `skip_lock=True`, so it does not contend with that lock and currently permits duplicate observer sessions. Add a separate lock under configured `LOCKS_ROOT` (falling back to the repository runtime lock directory), shared across worktrees using the same runtime root.

The lock file must remain present while unlocked. Unlinking a lock path after unlock can race with another process opening and acquiring the old inode, allowing a third process to create and lock a new inode at the same path. Extend `InstanceLock` with an opt-in persistent-path mode that clears holder metadata while still holding the lock and then unlocks without unlinking. Existing LIVE/PAPER callers retain their current default behavior.

Acquire only after launch-plan readiness succeeds and before creating per-run output. Keep the lock for the full child process duration and release in `finally`. Lock failure is a fail-closed observation-startup result, not a claim about broker or strategy readiness.
