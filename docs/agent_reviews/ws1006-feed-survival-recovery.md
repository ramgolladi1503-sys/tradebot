# Agent Review — WS1006 Feed Survival and Controlled Recovery

mode: REVIEW
candidate_id: PR525_WS1006_FEED_SURVIVAL_RECOVERY
decision: APPROVED_FOR_READ_ONLY_RUNTIME_RECOVERY_PR
reason: Makes plain WS1006 peer-drop recoverable first, while keeping terminal reactor failures fail-closed and preserving trade-blocking feed truth until verification returns.
timestamp: 2026-06-08T10:45:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/ws1006-feed-survival-recovery.md

mode: PAPER
candidate_id: PR525-WS1006-FEED-SURVIVAL-RECOVERY
decision: APPROVED_FOR_READ_ONLY_RUNTIME_RECOVERY_PR
reason: Makes plain WS1006 peer-drop recoverable first, while keeping terminal reactor failures fail-closed and preserving trade-blocking feed truth until verification returns.
timestamp: 2026-06-08T10:45:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/ws1006-feed-survival-recovery.md

## Agent Work Contract

### Scope

Recover plain WS1006 peer-drop as a controlled reconnect/retry path, add recoverable-attempt tracking and cooldown, and preserve fail-closed behavior until current-session option verification is re-established.

### Files changed

- `core/kite_depth_ws.py`
- `tests/test_kite_depth_ws_stability.py`
- `tests/test_kite_depth_restart.py`
- `docs/agent_reviews/ws1006-feed-survival-recovery.md`

### Explicit non-goals

- No strategy changes
- No scoring or ranking changes
- No Phase2 math or filtering changes
- No dashboard changes
- No broker or order changes
- No live order behavior changes
- No threshold relaxation unrelated to WS1006 recovery
- No fake candidate creation
- No broad refactor

## Grill Me Review

### Challenge 1 — Are we still failing closed during recovery?

Risk: A recoverable WS1006 path could accidentally allow TradeBuilder or Phase2 to proceed while the feed is not healthy.

Answer: The runtime snapshot stays degraded/reconnecting during recovery, and canonical feed truth keeps executable/live selection blocked until verification is re-established.

Proof:

- `test_ws1006_peer_drop_on_error_is_recoverable_first`
- `test_ws1006_recovery_does_not_overlap_when_already_in_progress`
- feed runtime snapshot assertions in `tests/test_kite_depth_ws_stability.py`

### Challenge 2 — Can plain peer-drop WS1006 still kill the bot immediately?

Risk: The code could still treat a plain peer drop as terminal and jump to `RECOVERY_BLOCKED`.

Answer: Plain peer-drop WS1006 is now recoverable first. Only terminal reactor failures remain immediate process-restart-required faults.

Proof:

- `test_ws1006_peer_drop_on_error_is_recoverable_first`
- `test_ws1006_on_error_keeps_reconnect_path_open_first`
- `test_ws1006_on_close_keeps_reconnect_path_open_first`

### Challenge 3 — Can recovery overlap and start multiple restart paths?

Risk: A second WS1006 or watchdog event could start a second restart while recovery is already in flight.

Answer: `_RECOVERY_IN_PROGRESS` is used as a coordinator and suppresses overlapping WS1006 recovery attempts.

Proof:

- `test_ws1006_recovery_does_not_overlap_when_already_in_progress`

## Hermes Review

### Contract quality

The WS1006 fault classifier now distinguishes:

- `AUTH_BLOCKED`
- `TERMINAL_PROCESS_RESTART_REQUIRED`
- `RECOVERABLE_WS_DROP`
- `UNKNOWN`

Only terminal reactor failures produce `process_restart_required=true`.

### Determinism

Recovery attempts are capped per session and governed by a cooldown. The runtime evidence remains deterministic for a given sequence of WS1006 events and tick conditions.

### Backward compatibility

Terminal reactor failures remain fail-closed. The change narrows over-classification of plain 1006 peer-drop events without weakening hard safety blocks.

## GSD Review

### What changed

Added recoverable-first WS1006 handling, recoverable-attempt tracking, cooldown support, and overlapping-recovery suppression.

### Why this matters

The feed should not be escalated to terminal process-restart-required state just because the peer dropped the socket uncleanly. That caused repeated false recovery-blocked behavior after manual restarts.

### Smallest useful implementation

A narrow classifier + recovery coordinator in `core/kite_depth_ws.py` with focused regression tests. No strategy, ranking, Phase2, broker, or dashboard wiring changed.

## QA / Safety Review

### Safety boundaries checked

- No broker import was added.
- No order-action code was added.
- No strategy files were changed.
- No scoring or ranking code was changed.
- No dashboard code was changed.
- No Phase2 logic was changed.
- Fail-closed feed truth remains in place during reconnect/recovery.

### Negative and edge-case tests

- Plain peer-drop 1006 is recoverable first.
- Terminal reactor errors remain process-restart-required.
- ReactorNotRestartable stays terminal.
- Recovery overlap is suppressed.
- Fail-closed runtime evidence remains intact.

## High-Risk Path Review

### Why `core/kite_depth_ws.py` changed

This is the feed runtime path that classifies websocket faults and controls reconnect/restart recovery. It is high risk because a bad classification could either keep the feed dead too long or weaken fail-closed safety.

### Why the change is narrow

The patch only narrows plain WS1006 peer-drop handling into a recoverable-first path, adds a recoverable-attempt counter and cooldown, and suppresses overlapping recovery. It does not alter strategy, ranking, Phase2, broker/order, or dashboard behavior.

### Safety proof

- Plain peer-drop WS1006 does not immediately become `RECOVERY_BLOCKED`.
- Terminal reactor failures still become process-restart-required.
- During recovery, runtime evidence remains degraded/reconnecting and option verification must re-establish before the feed can be trusted again.

## Scope Guard

### In scope

- WS1006 fault classification.
- Recoverable WS1006 retry tracking.
- Recovery overlap suppression.
- Focused tests and evidence doc.

### Out of scope

- Strategy generation.
- Scoring/ranking.
- Phase2 math/filtering.
- Broker/order paths.
- Dashboard/UI.
- Threshold changes unrelated to WS1006 recovery.

### Files not touched

- `strategies/*`
- `core/candidate_scoring.py`
- `core/expectancy/*`
- `core/review_queue.py`
- `core/orchestrator.py`
- `dashboard/*`
- `broker/*`
- `order/*`

## Acceptance Proof

Required commands:

```bash
PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py tests/test_kite_depth_restart.py tests/test_feed_runtime*.py tests/test_orchestrator*.py tests/test_latency_guard*.py -vv
python scripts/validate_agent_review_evidence.py --base-ref origin/main
git diff --check
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr525_changed_paths.txt
```

Expected proof:

- Plain peer-drop 1006 logs `FEED_WS_1006_RECOVERABLE` first.
- Plain peer-drop 1006 does not immediately become `RECOVERY_BLOCKED`.
- Terminal reactor errors still produce `process_restart_required=true`.
- Recovery remains fail-closed until option verification is healthy again.
- No broker/order/strategy/ranking/Phase2/dashboard behavior changed.

## Runtime Proof Required After Merge

After merge, verify in a live or replayed current-session runtime snapshot:

1. A plain WS1006 peer-drop is classified as recoverable first.
2. A terminal reactor failure still becomes process-restart-required.
3. Canonical feed truth remains blocking while recovery is incomplete.
4. Option-feed verification must re-run after reconnect.

## What This PR Does Not Prove

- It does not prove durable trading edge.
- It does not prove live market profitability.
- It does not prove the peer-drop problem is the only feed issue.
- It does not relax feed freshness gates or other safety gates.
- It does not change strategy generation or candidate semantics.

## Human Approval

Human approval required before merge:

- Reviewer must verify this PR is read-only with respect to trading actions.
- Reviewer must verify terminal reactor failures still fail closed.
- Reviewer must verify plain peer-drop WS1006 no longer jumps straight to recovery-blocked.
- Reviewer must verify CI is green.

## Migration Notes

- No data migration is required.

## Agent Work Contract
This PR centralizes feed recovery decisions behind `FeedRecoveryCoordinator`.
It is limited to feed recovery, feed runtime evidence, tests, and this review document.
It does not change strategy, ranking/scoring math, Phase2 math, dashboard/UI, broker/order placement, thresholds, or live order behavior.

## Scope Guard
Allowed files changed:
- `core/feed_recovery_coordinator.py`
- `core/kite_depth_ws.py`
- `core/feed_runtime.py`
- `core/feed_truth_state.py`
- `core/orchestrator.py`
- focused tests
- this agent review doc

Forbidden areas remain untouched:
- `strategies/*`
- `dashboard/*`
- broker/order placement
- ranking/scoring math
- Phase2 math
- thresholds
- live order behavior

## High-Risk Path Review
Required because this PR changes `core/kite_depth_ws.py` and `core/orchestrator.py`.

- `core/kite_depth_ws.py` changes are limited to recovery classification and coordinator wiring.
- `core/orchestrator.py` changes are evidence plumbing only: it backfills feed truth recovery fields when top-level evidence is blank.
- No order placement, broker mutation, strategy selection, ranking/scoring, Phase2 math, dashboard, or threshold behavior was changed.
- Recovery remains fail-closed.

## Grill Me Review
- Could this accidentally suppress terminal recovery? Tests cover terminal escalation even with recovery active.
- Could plain `1006` become executable? No. Recovery remains degraded/non-healthy until reconnect, resubscribe, and option verification succeed.
- Could duplicate recovery still happen? The coordinator emits `FEED_RECOVERY_ALREADY_IN_PROGRESS` and suppresses duplicate recoverable actions.
- Could this hide FeedTruth? Runtime/ranked evidence now backfills `feed_truth_state` and `feed_truth_reason_code`.

## Hermes Review
- Runtime flow is deterministic: `on_error` / `on_close` / watchdog report → coordinator decides → one recovery path.
- Recoverable WS1006 peer-drop goes to the recoverable path.
- Terminal `main loop terminated`, `ReactorNotRestartable`, and attempt exhaustion still go to `process_restart_required`.
- Option verification must pass before feed becomes `VERIFIED_HEALTHY`.

## GSD Review
- This PR fixes the root GSD issue: many components independently deciding recovery.
- The new coordinator reduces reconnect storms and early feed death.
- It does not solve subscription registry, capability gate, or replay journal gaps; those remain future PRs.

## QA / Safety Review
- 117 focused tests passed.
- `git diff --check` passed.
- `validate_agent_review_evidence.py` passed locally before packaging.
- Unified CE gates should pass after required headings are present.
- No order path changes.
- No live order behavior changes.
- Feed remains fail-closed during recovery.

## Acceptance Proof
Commands run:
```bash
PYTHONPATH=. pytest -q tests/test_feed_recovery_coordinator.py tests/test_feed_runtime*.py tests/test_kite_depth_ws_stability.py tests/test_kite_depth_restart.py tests/test_ranked_pipeline_runtime_evidence_wiring.py -vv
python scripts/validate_agent_review_evidence.py --base-ref origin/main
git diff --check
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr526_changed_paths.txt
git diff --name-only origin/main...HEAD | grep -E '^strategies/' || true
git diff --name-only origin/main...HEAD | grep -E '^dashboard/' || true
git diff --name-only origin/main...HEAD | grep -E 'broker|order|execution' || true
```

Result:
- `117 passed`
- `git diff --check` passed
- strategy guardrail showed no `strategies/*` changes

## Runtime Proof Required After Merge
Needs live-audit observation during market hours.

Expected:
- `FEED_OPTION_VERIFY_OK` initially.
- If plain WS1006 occurs:
  - `FEED_WS_1006_RECOVERABLE`
  - `FEED_RECOVERY_ACCEPTED`
  - no immediate `RECOVERY_BLOCKED`
  - reconnect/resubscribe
  - `FEED_OPTION_VERIFY_BEGIN`
  - `FEED_OPTION_VERIFY_OK`
  - `FeedTruth` returns to `VERIFIED_HEALTHY`.
- If terminal reactor failure occurs:
  - `FEED_WS_PROCESS_RESTART_REQUIRED`
  - `RECOVERY_BLOCKED`
  - restart artifact written.

## What This PR Does Not Prove
- Does not prove full-day live market stability yet.
- Does not add deterministic subscription registry.
- Does not add feed capability gate.
- Does not add feed replay journal / RCA bundle.
- Does not prove profitability or candidate quality.
- Does not enable live orders.

## Human Approval
- Human must review before merge.
- Human must verify CI green.
- Human must verify no forbidden-path behavior changes.
- Human must run or observe next live-audit validation before moving to PR #527.
- No config migration is required.
- Existing runtime snapshots remain backward-compatible; this PR only changes WS1006 classification and recovery evidence.

## Rollout Steps

1. Merge the WS1006 recovery classification change.
2. Watch current-session runtime evidence for recoverable-first WS1006 events.
3. Confirm option verification returns to `OK` after reconnect.
4. Confirm no `RECOVERY_BLOCKED` escalation occurs for ordinary peer-drop-only WS1006 unless recoverable attempts are exhausted.
