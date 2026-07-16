# Feed Reconnect Resource Soak Audit

mode: OFFLINE_SYNTHETIC
candidate_id: feed_reconnect_resource_soak_pr656
decision: RECONNECT_RESOURCE_PASS
reason: exact offline reconnect, resource, owner, subscription, and negative-cleanup invariants passed for the documented checkpoint
timestamp: 2026-07-16T08:34:08Z
is_order_action: false
broker_api_called: false
source: scripts/run_feed_reconnect_resource_soak.py

## Agent Work Contract
- `source_agent`: Codex
- `action`: UPDATE_DOCS
- `title`: normalize reconnect-soak integration lineage and evidence terminology
- `scope`: documentation-only normalization of accepted offline evidence
- `requested_paths`:
  - `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
  - `docs/agent_handoffs/feed-reconnect-resource-soak-codex.md`
- `allowed_paths`:
  - `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
  - `docs/agent_handoffs/feed-reconnect-resource-soak-codex.md`
- `forbidden_paths`:
  - production code
  - harness behavior
  - assertions
  - thresholds
  - strategy code
  - storage code
  - credentials
  - execution logic
  - market-data semantics
- `expected_tests`:
  - `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
  - `git diff --check`
  - `git status --short --untracked-files=all`
  - `git diff --name-status`
  - `git diff`
- `acceptance_proof`: corrected lineage, integration dependency, generation-counter terminology, and RSS terminology with clean lightweight validation

## Scope Guard
- Worktree: `/Users/madhuram/.codex/worktrees/tradebot/feed-reconnect-resource-soak-recovery`
- Branch: `codex/feed-reconnect-resource-soak-recovery`
- Base commit: `4235c012874757707a14322e3d5457fe0cb1896a`
- 1000-cycle checkpoint commit: `30b13a55489ed744a257d2c58d18448eddbbd02b`
- Previous evidence commit: `d5bf8195275fd2d0aa94369abbd196f994dd8835`
- This pass is documentation-only.
- No soak reruns were permitted.
- No production or harness code changes were permitted.

## Objective
Normalize the accepted reconnect-soak evidence so the documentation reflects full branch ancestry, inherited prerequisite scope, accurate generation-counter semantics, accurate RSS terminology, and the dependency-order constraints on reusing the 1000-cycle proof.

## Technical Evidence Status
- `PROVEN`

## Offline Verdict
- `RECONNECT_RESOURCE_PASS`

## Starting Baseline
- Accepted evidence already existed before this documentation pass:
  - 100-cycle reconnect proof
  - 1000-cycle reconnect proof
  - guarded-policy proof
  - owner-failure proof
  - negative-control detection and cleanup proof
  - storage regression proof
- The 1000-cycle proof belongs to checkpoint `30b13a55489ed744a257d2c58d18448eddbbd02b`.
- The later `d5bf8195275fd2d0aa94369abbd196f994dd8835` commit changed negative-control cleanup reporting only.

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
  - purpose: prerequisite storage/FD lifecycle repair
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
  - purpose: initial reconnect-soak harness, warmup baseline, and evidence docs
  - originating lane: inherited reconnect-soak lane before Codex takeover
  - classification: reconnect-soak-specific
- `bff9ea2b904578afb9f842a93618976e7a88e857`
  - parent: `d52a5bfc7ef72e16b6f04ad1d6921e3c44e44e69`
  - subject: `fix: resolve harness memory leak and verdict engine crashes`
  - files changed:
    - `scripts/run_feed_reconnect_resource_soak.py`
    - `tests/test_feed_reconnect_resource_soak.py`
  - purpose: harness-only stability repair
  - originating lane: inherited reconnect-soak lane before Codex takeover
  - classification: reconnect-soak-specific
- `060e8f1be3c0b2e0f23fa1ba02b3e07c433b7af6`
  - parent: `bff9ea2b904578afb9f842a93618976e7a88e857`
  - subject: `fix: resolve memory leak, verdict engine crashes, and SQLite closed connection errors; update evidence`
  - files changed:
    - `core/trade_store.py`
    - `docs/agent_handoffs/feed-reconnect-resource-soak-antigravity.md`
    - `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
  - purpose: continue inherited storage/SQLite lifecycle repair and evidence updates
  - originating lane: inherited mixed prerequisite plus reconnect-soak lane
  - classification: prerequisite
- `1ea92556a57ef83464c1b30c31ffdb50694749a7`
  - parent: `060e8f1be3c0b2e0f23fa1ba02b3e07c433b7af6`
  - subject: `Add bounded diagnostic information for retired reachable tickers`
  - files changed:
    - `core/trade_store.py`
    - `scripts/run_feed_reconnect_resource_soak.py`
  - purpose: diagnostic evidence for reachable retired generations
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
  - purpose: strict reconnect verification boundaries and restoration of inherited storage baseline
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
  - purpose: accepted Codex checkpoint for the 1000-cycle proof
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
  - purpose: accepted Codex evidence follow-up for explicit negative cleanup snapshots
  - originating lane: Codex-authored reconnect-soak scope
  - classification: reconnect-soak-specific

## Full Branch Diff Against Main
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

## Codex-Authored Reconnect-Soak Scope
- `core/kite_depth_ws.py`
- `scripts/run_feed_reconnect_resource_soak.py`
- `tests/test_feed_reconnect_resource_soak.py`
- `tests/test_kite_depth_ws_stability.py`
- `docs/agent_reviews/feed_reconnect_resource_soak_audit.md`
- `docs/agent_handoffs/feed-reconnect-resource-soak-codex.md`

## Inherited Prerequisite Commits
- `43122bdd3c004fe483e8e5024992cd250b302d28`
- `060e8f1be3c0b2e0f23fa1ba02b3e07c433b7af6`

## Inherited Prerequisite Scope
- `core/feed/runtime_store.py`
- `core/storage/snapshots.py`
- `core/tick_store.py`
- `core/trade_store.py`
- `docs/agent_handoffs/feed-reconnect-resource-soak-antigravity.md`

## Why The Branch Includes Inherited Files
- `core/feed/runtime_store.py`
  - prerequisite storage/FD lifecycle fix from `43122bdd`
- `core/storage/snapshots.py`
  - prerequisite storage/FD lifecycle fix from `43122bdd`
- `core/tick_store.py`
  - prerequisite storage/FD lifecycle fix from `43122bdd`
- `core/trade_store.py`
  - prerequisite storage repair and restoration path across multiple inherited commits
- `docs/agent_handoffs/feed-reconnect-resource-soak-antigravity.md`
  - inherited handoff lineage from the pre-Codex reconnect-soak lane

## Architecture Decision
- Preserve the accepted 1000-cycle evidence at the exact checkpoint tree where it was measured.
- Do not recast the branch as if only the Codex-authored files existed.
- Separate:
  - full branch diff against `main`
  - Codex-authored reconnect-soak scope
  - inherited prerequisite storage/FD lifecycle scope

## High-Risk Path Review
- High-risk path on the accepted checkpoint tree: `core/kite_depth_ws.py`
- Review outcome:
  - no broker or order path changes
  - no risk-gate weakening
  - no feed-freshness weakening
  - lifecycle fix is constrained to recovery clearing after exact replay
  - zero-count option maps no longer keep recovery stuck

## Guarded Policy Evidence
- Accepted result:
  - `RECONNECT_GUARDED_POLICY_PASS`
  - `disconnect_count=3`
  - `verified_successful_reconnect_count=2`
  - `generation_transition_count=2`
  - `hard_failures=0`
  - `first_mismatch=guarded_policy_blocked_at_cycle_2: recovery blocked by original safety limits`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`

## Unbounded 100-Cycle Evidence
- Accepted result only. Not rerun in this documentation pass.
- Result:
  - `RECONNECT_RESOURCE_100_CYCLE_PASS`
  - `disconnect_count=100`
  - `verified_successful_reconnect_count=100`
  - `generation_transition_count=100`
  - `hard_failures=0`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `retired_websocket_generations_reachable=0`

## Unbounded 1000-Cycle Evidence
- This 1000-cycle proof applies to checkpoint `30b13a55489ed744a257d2c58d18448eddbbd02b`.
- The later change affects negative-control cleanup reporting only.
- Accepted result:
  - `RECONNECT_RESOURCE_1000_CYCLE_PASS`
  - `cycles_requested=1000`
  - `verified_successful_reconnect_count=1000`
  - `generation_transition_count=1000`
  - `websocket_generations_created=1001`
  - `same_generation_reused_count=1557`
  - `generation_creation_failures=0`
  - `terminal_failure_count=0`
  - `hard_failures=0`
  - `fd_count 7 -> 9 -> 9`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `watchdog_thread_count 1 -> 1 -> 0`
  - `python_thread_count 2 -> 3 -> 1`
  - `retired_websocket_generations_reachable=0`
  - `reconnect_lock_held=false`
  - `completed_cycle_same_generation_reuse=0`

## Corrected Generation Counter Explanation
- `same_generation_reused_count` is a legacy and misnamed polling-observation counter.
- It counts wait-loop observations of the old generation before transition.
- It is not a completed-cycle reuse count and is not an acceptance invariant.
- The observed value `1557` does not mean 1,557 reconnect cycles reused an old websocket.
- The accepted generation evidence is:
  - `cycles_requested=1000`
  - `verified_successful_reconnect_count=1000`
  - `generation_transition_count=1000`
  - `websocket_generations_created=1001`
  - `generation_creation_failures=0`
  - `terminal_failure_count=0`
  - `hard_failures=0`

## Owner-Failure Evidence
- Accepted result:
  - `RECONNECT_OWNER_FAILURE_RECOVERY_PASS`
  - `disconnect_count=100`
  - `verified_successful_reconnect_count=100`
  - `generation_transition_count=100`
  - `owner_failures_injected_count=19`
  - `owner_failures_observed_count=19`
  - `owner_recoveries_completed_count=19`
  - `hard_failures=0`
  - `fd_count 7 -> 7 -> 7`
  - `sqlite_fd_count 0 -> 0 -> 0`
  - `reconnect_lock_held=false`

## Negative FD Detector And Cleanup Evidence
- Accepted result:
  - `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS`
  - `first_mismatch=fd_leak_detected_final`
  - `post_warmup_baseline.fd_count=7`
  - `final.fd_count=27`
  - `post_cleanup_final.fd_count=7`
  - `post_warmup_baseline.sqlite_fd_count=0`
  - `final.sqlite_fd_count=0`
  - `post_cleanup_final.sqlite_fd_count=0`

## SQLite Same-Path Descriptor And Cleanup Evidence
- Accepted result:
  - `RECONNECT_RESOURCE_NEGATIVE_CONTROL_PASS`
  - `first_mismatch=fd_leak_detected_final`
  - `post_warmup_baseline.fd_count=7`
  - `final.fd_count=47`
  - `post_cleanup_final.fd_count=7`
  - `post_warmup_baseline.sqlite_fd_count=0`
  - `final.sqlite_fd_count=40`
  - `post_cleanup_final.sqlite_fd_count=0`

## Subscription Reconciliation Evidence
- Accepted positive-profile invariants:
  - `subscription_tokens_match_exactly=true`
  - `missing_token_count=0`
  - `unexpected_token_count=0`
  - `duplicate_subscription_count=0`
- Final shutdown snapshots intentionally reflect stopped-ticker state rather than in-flight replay.

## Watchdog Lifecycle Evidence
- Accepted positive-profile invariants:
  - no watchdog leak
  - no thread leak that survives shutdown
  - 1000-cycle proof recorded `watchdog_thread_count 1 -> 1 -> 0`

## Recovery-Clear Contract Evidence
- Accepted production fix:
  - `_resubscribe_full()` clears recovery after exact replay only when positive-count option verification is actually required.
- This prevents a zero-count option map from blocking recovery indefinitely.

## Corrected RSS Explanation
- `rss_slope_bytes_per_sample` is endpoint change across sampled observations.
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
- OPTION A is safest because the accepted scale proof belongs to checkpoint `30b13a55` and its complete ancestry.

## Grill Me Review
- Do not describe this branch as if only the six Codex reconnect-soak files exist.
- Do not copy only those files onto `main` and claim the 1000-cycle proof transfers unchanged.

## Hermes Review
- The correct integration model is dependency-ordered composition, not proof transplant.

## GSD Review
- This pass made documentation-only corrections.
- No further implementation or testing was performed.

## QA / Safety Review
- No production code changed in this documentation pass.
- No soak runs were repeated.
- No pytest or resource profiles were run.

## Acceptance Proof
- Documentation now distinguishes:
  - full branch diff against `main`
  - Codex-authored reconnect-soak scope
  - inherited prerequisite scope
- Documentation now correctly explains the misnamed generation counter.
- Documentation now correctly explains the RSS metric limitation.
- Documentation now records the dependency-order constraint on the accepted 1000-cycle proof.

## Runtime Proof Required After Merge
- Live or paper websocket sessions under real Kite auth
- Real market-open option-universe transitions
- Real network churn under broker runtime

## What This PR Does Not Prove
- It does not prove live readiness.
- It does not prove paper readiness.
- It does not prove broker correctness.
- It does not prove unbounded real-runtime stability.

## Human Approval
- Human approval is still required for merge or rollout.
- No PR was opened in this documentation pass.
- No merge was performed in this documentation pass.

## Final Verdict
- The accepted offline reconnect-soak evidence remains `PROVEN`, and the integration lineage is now documented without concealing inherited prerequisite scope.
