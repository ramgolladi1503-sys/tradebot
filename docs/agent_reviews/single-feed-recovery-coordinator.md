# PR #526 — Single Feed Recovery Coordinator

mode: REVIEW
candidate_id: PR526_SINGLE_FEED_RECOVERY_COORDINATOR
decision: centralize_feed_recovery_decisions
reason: Centralize feed recovery decisions behind a single coordinator so recoverable WS1006 peer-drops stay fail-closed without being over-classified as terminal.
timestamp: 2026-06-08T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/single-feed-recovery-coordinator.md

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
