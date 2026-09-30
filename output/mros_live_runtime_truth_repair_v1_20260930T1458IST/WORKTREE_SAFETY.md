# Worktree and Live-Session Safety

## Before implementation

Observed 2026-09-30 around 14:58 IST using read-only Git metadata, `ps`, and SHA-256 commands.

```text
ACTIVE_LIVE_WORKTREE=/Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1
ACTIVE_LIVE_SHA=e2e95aae201271db9cb7abe11b43d462bea3bd57
ACTIVE_SESSION=meg-live-2026-09-30-a08e95b09449-c0e5c366feed
LIVE_PROCESS_PIDS=77419,79000,79001,79080
LIVE_WORKTREE_DIRTY=false (git status --porcelain=v1 produced 0 lines)
REPAIR_WORKTREE=/Users/madhuram/.codex/worktrees/mros-live-runtime-truth-v1/tradebot
REPAIR_BASE_SHA=e2e95aae201271db9cb7abe11b43d462bea3bd57
REPAIR_BRANCH=fix/mros-live-runtime-truth-reliability-v1
```

Process identities observed:

- PID 77419: `scripts/run_governed_morning_observer_v1.py`.
- PID 79000, child of 77419: `scripts/tick_data_collector.py` from the active worktree.
- PID 79001, child of 77419: `scripts/run_market_event_graph_live_session_v1.py`.
- PID 79080, child of 79001: `scripts/run_kite_read_only_observation_v1.py`, output session ID matches the active session above.

The ReleaseStore history pointer was read only. `/Volumes/TradeBotData/release_store/current.json` points to event SHA-256 `5721c25f2ba5a1b8a9aaba7b0332c77288440135eac8eefe70af589df2c01c1e`; that history event names `e2e95aae201271db9cb7abe11b43d462bea3bd57` as `certified_live_sha`.

Selected active-session artifact hashes (read-only, before implementation):

```text
dbe15d4a26ad12164a812288db5b10566b2f37c07261b2ab0be0aa4eb6ba7bed  launch_plan.json
14e62a6309bfd1606466206f342885251c0a8e67cea8e1eaaa7d4f8c2181ec7a  presession_manifest.json
```

The canonical checkout `/Users/madhuram/tradebot` was already heavily dirty and at another SHA; it was not used for implementation. No process control, broker API, order action, or active-session write was issued by this task.

## After implementation and focused validation (initial final snapshot, 14:58 IST)

Read-only snapshot recorded 2026-09-30 after the focused suites:

- Active live worktree path remains `/Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1`.
- Live SHA and process identities were rechecked; see final manifest for exact observed values.
- Active live worktree status remained clean (0 porcelain entries).
- Selected static active-session artifacts were rehashed and matched the recorded baseline values.
- All code/test/evidence writes and offline pytest commands were confined to the repair worktree.
- This proves non-interference by Codex actions for the observed scope; it does not prove the live observer itself remained operational or that its session completed successfully.

Initial final read-only recheck (2026-09-30 14:58 IST, after implementation and 174 focused tests):

```text
ACTIVE_LIVE_WORKTREE=/Volumes/TradeBotData/worktrees/mros-dynamic-releasestore-binding-v1
ACTIVE_LIVE_SHA=e2e95aae201271db9cb7abe11b43d462bea3bd57
ACTIVE_LIVE_STATUS_PORCELAIN_LINES=0
ACTIVE_SESSION=meg-live-2026-09-30-a08e95b09449-c0e5c366feed
LIVE_PROCESS_PIDS=77419,79000,79001,79080
REPAIR_WORKTREE=/Users/madhuram/.codex/worktrees/mros-live-runtime-truth-v1/tradebot
REPAIR_HEAD=e2e95aae201271db9cb7abe11b43d462bea3bd57
REPAIR_BRANCH=fix/mros-live-runtime-truth-reliability-v1
```

Final read-only recheck at 2026-09-30 15:48 IST found a changed process set: PID 79000 (`tick_data_collector.py`) remained with PPID 1; PIDs 77419 (`run_governed_morning_observer_v1.py`), 79001 (`run_market_event_graph_live_session_v1.py`), and 79080 (`run_kite_read_only_observation_v1.py`) were absent. The cause and external owner of these process exits are UNKNOWN. Codex issued no signal, terminate, restart, or live-worktree write command. PID 79000 is left untouched. The active worktree remains at the baseline SHA with zero porcelain status lines. Selected static evidence hashes still match baseline:

```text
dbe15d4a26ad12164a812288db5b10566b2f37c07261b2ab0be0aa4eb6ba7bed  launch_plan.json
14e62a6309bfd1606466206f342885251c0a8e67cea8e1eaaa7d4f8c2181ec7a  presession_manifest.json
```

`git status --porcelain=v1` in the live worktree produced no lines. These observations support `ACTIVE_LIVE_WORKTREE_MODIFIED=false`, `ACTIVE_LIVE_PROCESS_SIGNALED=false`, and unchanged selected artifacts by Codex actions. The overall session-process state changed during the task and its cause is UNKNOWN; do not interpret the initial non-interference check as proof that all live processes remained unchanged or that the session completed successfully.


Latest read-only check at 2026-09-30 16:09 IST: live worktree SHA remains `e2e95aae201271db9cb7abe11b43d462bea3bd57`, `git status --porcelain=v1` is empty, and none of baseline session PIDs 77419, 79000, 79001, or 79080 is present. PID 1167 is an Antigravity scheduler/language-server process and is not a session PID. Cause and owner of session process exits remain UNKNOWN. No process was signaled or controlled by Codex.

Latest read-only check at 2026-09-30 16:56 IST: live worktree SHA remains `e2e95aae201271db9cb7abe11b43d462bea3bd57` and `git status --porcelain=v1` has 0 entries. The four baseline session PIDs remain absent; PID 1167 is the unrelated Antigravity scheduler/language-server. Cause and owner of the session process exits remain UNKNOWN. `launch_plan.json` and `presession_manifest.json` were not found under the active worktree, so their latest hashes are UNKNOWN; the prior recorded hash values are baseline-only and were not carried forward as current verification. No process-control or write action was issued against the active worktree/session.


## Pointer-safe test-data handling

The tracked worktree tick dataset remains the 132-byte Git LFS pointer with OID `30e6b7372cd521c80831a0da478e2402ce884c20bc00e47d7ea07122473ebda7` and declared size 7,604,505 bytes. The test now detects pointer content and uses the already-existing local canonical copy only as an optional read-only test input; when unavailable, it skips explicitly. No tracked dataset hydration or network/LFS fetch was performed for the final run. The earlier hydrated-file full-suite run remains historical evidence only. No canonical file was written, and no live process or broker was contacted.
