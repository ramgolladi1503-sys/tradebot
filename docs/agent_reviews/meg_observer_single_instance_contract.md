# MEG Read-Only Observer Single-Instance Contract

## Hermes Work Contract

- `source_agent: hermes`
- `action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS`
- `title: Prevent overlapping MEG read-only sessions from contending on shared runtime storage`
- `scope: Enforce one active Market Event Graph read-only observation run per host and user across git worktrees by default, with an explicit shared lock-root override. Acquire the lock only after static/launch preflight passes and only for an actual capture; leave preflight commands unaffected. Keep the guard independent from the LIVE/PAPER Kite execution lock.`
- `requested_paths: config/config.py; core/instance_lock.py; scripts/run_market_event_graph_live_session_v1.py; tests/test_instance_lock.py; tests/test_run_market_event_graph_live_session_v1.py; docs/agent_reviews/meg_observer_single_instance_contract.md`
- `allowed_paths: exactly the requested paths`
- `forbidden_paths: broker/order/execution/risk/strategy code; credential/environment files; main.py and live launcher behavior; broker calls; runtime artifacts; unrelated files`
- `expected_tests: same-process and cross-process lock exclusion; stale metadata cleared while lock-file inode remains stable; lock path is identical across two checkout roots; second observation is rejected before creating capture output; lock path is recorded in the presession manifest; static and launch preflight-only paths do not acquire the lock.`
- `acceptance_proof: at most one MEG capture per OS user can hold the default local lock across checkouts; a contending capture returns a stable fail-closed blocker and does not create a session directory; lock release allows a subsequent capture; configured lock-root overrides work; LIVE/PAPER lock path and behavior are unchanged; all tests remain read-only with no broker or order calls.`

## Design and Boundaries

The LIVE/PAPER `kite_session.lock` protects execution-bearing application processes. A MEG capture is intentionally SIM/read-only and uses `skip_lock=True`, so it does not contend with that lock. A repository-local fallback allowed two worktrees to capture concurrently. Use a separate per-user lock root at `~/.tradebot/locks` by default, overridable with `MEG_OBSERVATION_LOCKS_ROOT` or the existing explicit `LOCKS_ROOT` setting. The lock path is written into the presession manifest for later attribution.

The lock file must remain present while unlocked. Unlinking a lock path after unlock can race with another process opening and acquiring the old inode, allowing a third process to create and lock a new inode at the same path. Extend `InstanceLock` with an opt-in persistent-path mode that clears holder metadata while still holding the lock and then unlocks without unlinking. Existing LIVE/PAPER callers retain their current default behavior.

Acquire only after launch-plan readiness succeeds and before creating per-run output. Keep the lock for the full child process duration and release in `finally`. Lock failure is a fail-closed observation-startup result, not a claim about broker or strategy readiness.

## Agent Work Contract

Hermes specifies the lock contract and safety boundary; GSD implements only the listed paths and verifies exclusion/release behavior.

## Scope Guard

The new singleton applies only to actual MEG read-only capture sessions. Static and launch preflight, ordinary LIVE/PAPER process locking, execution mode, broker calls, and order behavior remain unchanged.

## Grill Me Review

- Do not share the execution lock: observers are SIM/read-only and may coexist with the execution process.
- Do not unlink the persistent lock path after release; inode replacement can permit two lock owners.
- A blocked second launch must create no capture directory and must not be presented as a successful observation.

## Hermes Review

Use a distinct `MEG_OBSERVATION_LOCKS_ROOT/meg_read_only_observation.lock` with OS advisory locking, clear holder metadata before unlock, and retain the inode. The default root must not depend on the current checkout. Hold the lock across the observer child process and release it in a `finally` path.

## GSD Review

GSD added the shared observer lock-root configuration, kept the generic `InstanceLock` default behavior, acquired the observer lock after preflight and before capture creation, recorded its path in the presession manifest, and added tests for cross-checkout path identity, contention, lock lifecycle, and lock-free preflight.

## QA / Safety Review

**High-Risk Path Review:** The session orchestrator is a runtime entrypoint, but this change only adds mutual exclusion for read-only SIM captures. It does not touch broker adapters, order/risk logic, credentials, live config, or execution locks. Lock errors fail closed with an explicit blocker and safety flags.

## Acceptance Proof

The focused lock and session-runner tests pass: 11 tests prove a contender is blocked across two simulated checkout roots and a child process, persistent lock metadata is cleared on release, reacquisition succeeds, legacy default unlink behavior remains intact, the manifest and blocked startup payloads record the lock path, and preflight-only does not create/acquire the observer lock. `py_compile` and `git diff --check` pass. Ruff is unavailable in this environment.

## Runtime Proof Required After Merge

On the next read-only session launch, record the exact commit, lock path, holder PID, and startup verdict. Attempting a second capture while the first is active must return the documented blocked verdict before creating a capture directory.

## What This PR Does Not Prove

It does not prove that unrelated observer programs, different OS users, or machines coordinate, or that prior overlapping sessions caused a specific database lock failure. Operators using multiple accounts must configure a shared `MEG_OBSERVATION_LOCKS_ROOT` accessible to those processes. The default prevents duplicate MEG wrappers launched by the same user across local worktrees.

## Configuration and Migration

- New key: `MEG_OBSERVATION_LOCKS_ROOT`, defaulting to `~/.tradebot/locks`.
- Set `MEG_OBSERVATION_LOCKS_ROOT` to a common local filesystem directory when sessions run under multiple accounts; an explicit `LOCKS_ROOT` remains a fallback override.
- Existing runs need no migration. The persistent lock file remains after release with empty holder metadata; advisory lock ownership, not file presence, determines whether a session is active.
- Static and launch preflight remain lock-free. The new path applies only to actual read-only MEG capture sessions.

## Human Approval

Human review is required before merge or runtime rollout. The observer lock does not grant live, paper, broker-write, or order authority.
