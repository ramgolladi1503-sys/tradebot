# Codex Handoff: Feed Reconnect Resource Soak Recovery

## Worktree
- `/Users/madhuram/.codex/worktrees/tradebot/feed-reconnect-resource-soak-recovery`

## Branch
- `codex/feed-reconnect-resource-soak-recovery`

## Base Commit
- `4235c012874757707a14322e3d5457fe0cb1896a`

## Commit Anchors
- 1000-cycle checkpoint:
  - `30b13a55489ed744a257d2c58d18448eddbbd02b`
- Evidence and cleanup commit:
  - `d5bf8195275fd2d0aa94369abbd196f994dd8835`
- Current branch tip:
  - Resolve with `git rev-parse HEAD` at handoff time.

## Offline Evidence Status
- `PROVEN`

## Offline Verdict
- `RECONNECT_RESOURCE_PASS`

## Complete Branch Commit Lineage
- `43122bdd3c004fe483e8e5024992cd250b302d28`
  - parent: `4235c012874757707a14322e3d5457fe0cb1896a`
  - subject: `fix: resolve SQLite FD leaks during feed reconnect loops`
  - files changed:
    - `core/feed/runtime_store.py`
    - `core/kite_depth_ws.py`
    - `core/storage/snapshots.py`
    - `core/tick_store.py`
    - `core/trade_store.py`
    - `scripts/run_feed_reconnect_resource_soak.py`
  - purpose: establish the prerequisite storage/FD lifecycle baseline so reconnect churn no longer leaks SQLite descriptors
  - originating lane: inherited prerequisite lane
  - classification: prerequisite
- `d52a5bfc7ef72e16b6f04ad1d6921e3c44e44e69`
  - parent: `43122bdd3c004fe483e8e5024992cd250b302d28`
  - subject: `test: add resource soak tests, harness warmup, and documentation`
  - files changed:
    - `docs/agent_handoffs/feed-reconnect-resource-soak-antigravity.md`
    - `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
    - `scripts/run_feed_reconnect_resource_soak.py`
    - `tests/test_feed_reconnect_resource_soak.py`
  - purpose: add the soak harness, baseline/warmup measurement, test coverage, and initial evidence docs
  - originating lane: inherited reconnect-soak lane before Codex takeover
  - classification: reconnect-soak-specific
- `bff9ea2b904578afb9f842a93618976e7a88e857`
  - parent: `d52a5bfc7ef72e16b6f04ad1d6921e3c44e44e69`
  - subject: `fix: resolve harness memory leak and verdict engine crashes`
  - files changed:
    - `scripts/run_feed_reconnect_resource_soak.py`
    - `tests/test_feed_reconnect_resource_soak.py`
  - purpose: fix harness-only memory retention and verdict crash behavior
  - originating lane: inherited reconnect-soak lane before Codex takeover
  - classification: reconnect-soak-specific
- `060e8f1be3c0b2e0f23fa1ba02b3e07c433b7af6`
  - parent: `bff9ea2b904578afb9f842a93618976e7a88e857`
  - subject: `fix: resolve memory leak, verdict engine crashes, and SQLite closed connection errors; update evidence`
  - files changed:
    - `core/trade_store.py`
    - `docs/agent_handoffs/feed-reconnect-resource-soak-antigravity.md`
    - `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
  - purpose: continue repairing inherited storage/SQLite lifecycle problems and refresh supporting evidence docs
  - originating lane: inherited mixed prerequisite plus reconnect-soak lane
  - classification: prerequisite
- `1ea92556a57ef83464c1b30c31ffdb50694749a7`
  - parent: `060e8f1be3c0b2e0f23fa1ba02b3e07c433b7af6`
  - subject: `Add bounded diagnostic information for retired reachable tickers`
  - files changed:
    - `core/trade_store.py`
    - `scripts/run_feed_reconnect_resource_soak.py`
  - purpose: add bounded diagnostics for retained websocket generation evidence while still on the inherited branch stack
  - originating lane: inherited reconnect-soak lane before Codex takeover
  - classification: reconnect-soak-specific with prerequisite ancestry
- `e8de8aeb2564ac647a2d5b1c3af1c0f1f997f80c`
  - parent: `1ea92556a57ef83464c1b30c31ffdb50694749a7`
  - subject: `fix: enforce strict reconnection verification boundaries and restore trade store`
  - files changed:
    - `core/kite_depth_ws.py`
    - `core/trade_store.py`
    - `docs/agent_handoffs/feed-reconnect-resource-soak-antigravity.md`
    - `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
    - `scripts/run_feed_reconnect_resource_soak.py`
    - `tests/test_feed_reconnect_resource_soak.py`
    - `tests/test_kite_depth_ws_stability.py`
  - purpose: restore strict acceptance boundaries, restore `trade_store`, and harden reconnect verification
  - originating lane: inherited reconnect-soak lane immediately before Codex checkpoint
  - classification: reconnect-soak-specific with prerequisite ancestry
- `30b13a55489ed744a257d2c58d18448eddbbd02b`
  - parent: `e8de8aeb2564ac647a2d5b1c3af1c0f1f997f80c`
  - subject: `fix: repair reconnect resource soak evidence contract`
  - files changed:
    - `core/kite_depth_ws.py`
    - `scripts/run_feed_reconnect_resource_soak.py`
    - `tests/test_feed_reconnect_resource_soak.py`
    - `tests/test_kite_depth_ws_stability.py`
  - purpose: Codex checkpoint that repaired the soak evidence contract and produced the accepted 1000-cycle proof
  - originating lane: Codex-authored reconnect-soak scope
  - classification: reconnect-soak-specific
- `d5bf8195275fd2d0aa94369abbd196f994dd8835`
  - parent: `30b13a55489ed744a257d2c58d18448eddbbd02b`
  - subject: `test: persist reconnect negative cleanup proof`
  - files changed:
    - `docs/agent_handoffs/feed-reconnect-resource-soak-codex.md`
    - `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
    - `scripts/run_feed_reconnect_resource_soak.py`
    - `tests/test_feed_reconnect_resource_soak.py`
  - purpose: Codex evidence follow-up that persisted explicit post-cleanup negative-control snapshots
  - originating lane: Codex-authored reconnect-soak scope
  - classification: reconnect-soak-specific

## Complete Branch Diff Against Main
- `core/feed/runtime_store.py`
- `core/kite_depth_ws.py`
- `core/storage/snapshots.py`
- `core/tick_store.py`
- `core/trade_store.py`
- `docs/agent_handoffs/feed-reconnect-resource-soak-antigravity.md`
- `docs/agent_handoffs/feed-reconnect-resource-soak-codex.md`
- `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
- `scripts/run_feed_reconnect_resource_soak.py`
- `tests/test_feed_reconnect_resource_soak.py`
- `tests/test_kite_depth_ws_stability.py`

## Codex Reconnect-Soak Implementation Scope
- `core/kite_depth_ws.py`
- `scripts/run_feed_reconnect_resource_soak.py`
- `tests/test_feed_reconnect_resource_soak.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
- `docs/agent_handoffs/feed-reconnect-resource-soak-codex.md`

## Inherited Prerequisite Scope
- `core/feed/runtime_store.py`
- `core/storage/snapshots.py`
- `core/tick_store.py`
- `core/trade_store.py`
- `docs/agent_handoffs/feed-reconnect-resource-soak-antigravity.md`

## Why The Branch Diff Against Main Includes The Inherited Files
- `core/feed/runtime_store.py`
  - inherited prerequisite storage/FD lifecycle fix from `43122bdd`
- `core/storage/snapshots.py`
  - inherited prerequisite storage/FD lifecycle fix from `43122bdd`
- `core/tick_store.py`
  - inherited prerequisite storage/FD lifecycle fix from `43122bdd`
- `core/trade_store.py`
  - inherited prerequisite storage repair and later restoration path across `43122bdd`, `060e8f1b`, `1ea92556`, and `e8de8aeb`
- `docs/agent_handoffs/feed-reconnect-resource-soak-antigravity.md`
  - inherited documentation lineage from the pre-Codex reconnect-soak lane beginning in `d52a5bfc`

## Production Changes And Rationale
- `core/kite_depth_ws.py`
  - real lifecycle fix in `_resubscribe_full()`
  - zero-count option maps no longer keep recovery uncleared after exact replay
- `scripts/run_feed_reconnect_resource_soak.py`
  - later Codex change is reporting-only after the 1000-cycle checkpoint
  - negative profiles now persist `post_cleanup_final`
  - positive reconnect semantics were not changed after the checkpoint

## Profiles Implemented
- `control`
- `reconnect_guarded`
- `reconnect_unbounded_resource_stress`
- `owner_failure`
- `negative_fd_leak`
- `sqlite_same_path_multi_descriptor_negative`

## Short-Suite Result
- Command:
  - `/Users/madhuram/tradebot/.venv/bin/python -m pytest -vv tests/test_feed_reconnect_resource_soak.py tests/test_kite_depth_ws_stability.py tests/test_feed_recovery_coordinator.py tests/test_kite_depth_restart.py -k "not test_reconnect_stress_1000_has_bounded_resources and not test_control_1000_has_no_cycle_correlated_fd_growth" --tb=long`
- Result:
  - `145 passed, 2 deselected in 370.38s`

## 100-Cycle Result
- Accepted prior evidence only. Not rerun in this handoff.
- Result:
  - `RECONNECT_RESOURCE_100_CYCLE_PASS`
  - `disconnect_count=100`
  - `verified_successful_reconnect_count=100`
  - `generation_transition_count=100`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `retired_websocket_generations_reachable=0`

## 1000-Cycle Result
- This 1000-cycle proof applies to checkpoint `30b13a55489ed744a257d2c58d18448eddbbd02b`.
- The later change affects negative-control cleanup reporting only.
- Result:
  - `RECONNECT_RESOURCE_1000_CYCLE_PASS`
  - `cycles_requested=1000`
  - `verified_successful_reconnect_count=1000`
  - `generation_transition_count=1000`
  - `websocket_generations_created=1001`
  - `generation_creation_failures=0`
  - `terminal_failure_count=0`
  - `hard_failures=0`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `retired_websocket_generations_reachable=0`
  - `reconnect_lock_held=false`
  - `completed_cycle_same_generation_reuse=0`

## Corrected Generation Counter Explanation
- `same_generation_reused_count` is a legacy and misnamed polling-observation counter.
- It counts wait-loop observations where the old generation is still visible before transition.
- It is not a completed-cycle reuse count.
- It is not an acceptance invariant.
- The observed value `1557` does not mean 1,557 reconnect cycles reused an old websocket.
- The accepted generation evidence is:
  - `cycles_requested=1000`
  - `verified_successful_reconnect_count=1000`
  - `generation_transition_count=1000`
  - `websocket_generations_created=1001`
  - `generation_creation_failures=0`
  - `terminal_failure_count=0`
  - `hard_failures=0`
- Terminology debt remains for future cleanup, but the harness was not changed and the soak was not rerun for renaming only.

## Corrected RSS Explanation
- `rss_slope_bytes_per_sample` is endpoint delta across sampled observations.
- It is not an ordinary least-squares regression slope.
- RSS was observed, but RSS slope was not used as an independent PASS/FAIL certification gate.
- The certified offline invariants are:
  - descriptor bounds
  - SQLite bounds
  - thread and watchdog cleanup
  - exact generation transitions
  - subscription reconciliation
  - owner release
  - negative-control detection and cleanup

## Guarded-Policy Result
- `RECONNECT_GUARDED_POLICY_PASS`
- `disconnect_count=3`
- `verified_successful_reconnect_count=2`
- `first_mismatch=guarded_policy_blocked_at_cycle_2: recovery blocked by original safety limits`

## Owner-Failure Result
- `RECONNECT_OWNER_FAILURE_RECOVERY_PASS`
- `disconnect_count=100`
- `owner_failures_injected_count=19`
- `owner_failures_observed_count=19`
- `owner_recoveries_completed_count=19`
- `reconnect_lock_held=false`

## Negative-Control Cleanup Result
- Result:
  - `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS`
  - `first_mismatch=fd_leak_detected_final`
  - `fd_count 7 -> 27 -> 7`
  - `sqlite_fd_count 0 -> 0 -> 0`

## SQLite Same-Path Result
- Result:
  - `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS`
  - `first_mismatch=fd_leak_detected_final`
  - `fd_count 7 -> 47 -> 7`
  - `sqlite_fd_count 0 -> 40 -> 0`

## Integration Dependency
The branch was tested as a composite tree whose ancestry includes prerequisite storage/FD lifecycle commits.

The 1000-cycle result applies to that exact checkpoint tree.

The reconnect-soak commits must not be copied onto a different storage baseline and represented as carrying the same 1000-cycle evidence without revalidation.

OPTION A — STACKED INTEGRATION
- Merge the prerequisite storage/FD lifecycle commits first.
- Then retarget or rebase the reconnect-soak branch onto that merged baseline.

OPTION B — COMPOSITE REVIEW
- Open a stacked or dependent PR that explicitly includes and identifies the prerequisite commits.
- Review the prerequisite storage changes separately from the reconnect-soak changes.

Recommended option:
- OPTION A is safest because the accepted 1000-cycle proof belongs to checkpoint `30b13a55` and its full tested ancestry. Merging the prerequisite storage baseline first preserves the exact dependency order and avoids representing a copied six-file subset as carrying unchanged scale proof.

## Storage Result
- Accepted prior evidence only. Not rerun in this handoff.
- Result:
  - `66 passed in 2.60s`

## Remaining Limitations
- Offline synthetic soak only.
- No live or paper broker session proof.
- Positive final snapshots are post-stop snapshots.
- `pre_shutdown_snapshot` and `post_shutdown_snapshot` were not part of the 1000-cycle checkpoint JSON and remain `UNMEASURED`.

## No PR
- No PR opened.

## No Merge
- No merge performed.
