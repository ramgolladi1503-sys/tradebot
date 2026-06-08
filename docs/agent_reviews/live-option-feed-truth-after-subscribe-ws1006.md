# PR #523 — Live Option Feed Truth After Subscribe and WS1006 Recovery

mode: REVIEW
candidate_id: PR-523-LIVE-OPTION-FEED-TRUTH-AFTER-SUBSCRIBE-WS1006
decision: fix_live_option_feed_truth_after_subscribe
reason: Distinguish subscription request from verified live option ticks, and keep WS1006 recovery truth current-session scoped so stale feed churn cannot dominate RCA.
timestamp: 2026-06-08T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/live-option-feed-truth-after-subscribe-ws1006.md

## Agent Work Contract
- **source_agent:** GSD
- **action:** Generate scoped patch, tests, docs, and validation for live option feed truth after subscribe and WS1006 recovery
- **title:** Live Option Feed Truth After Subscribe and WS1006 Recovery
- **scope:** Separate subscription request from verified live option ticks, classify current-session verification failures precisely, and keep stale historical feed churn from overriding current-session RCA without changing runtime trading behavior
- **requested_paths:** `core/kite_depth_ws.py`, `core/agents/feed_stability_agent.py`, `core/agents/live_rca_agent.py`, `core/agents/command_center.py`, `core/agents/readers.py`, `scripts/run_tradebot_agent_command_center.py`, `tests/test_kite_depth_ws_stability.py`, `tests/test_feed_stability_agent.py`, `tests/test_live_rca_agent.py`, `tests/test_agent_command_center.py`, `docs/agent_reviews/live-option-feed-truth-after-subscribe-ws1006.md`
- **allowed_paths:** Same as requested paths
- **forbidden_paths:** `core/orchestrator.py`, `core/candidate_scoring.py`, `core/expectancy/*`, `core/review_queue.py`, `strategies/*`, `dashboard/*`, broker/order/execution files, Phase2/ranking math files, websocket runtime architecture rewrites
- **expected_tests:** `PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py tests/test_feed_stability_agent.py tests/test_live_rca_agent.py tests/test_agent_command_center.py -vv`
- **acceptance_proof:** Current-session option subscription and live option tick verification are distinct; skipped-only rebalance evidence is safety-positive and not a blocker; no-live-option-feed and WS1006 recovery are classified precisely; command center no longer blames stale feed churn when current-session truth is healthy

## Scope Guard
- Do not change strategy generation, scoring, ranking, Phase2, broker, order, or dashboard behavior.
- Do not weaken stale-feed safety or feed freshness gates.
- Do not hide failures; label them correctly.
- Do not let stale historical feed churn dominate current-session evidence.
- Keep subscription-request evidence separate from verified live option ticks.

## Grill Me Review
- If subscribe/resubscribe is logged but tick verification never happens, the RCA must say so explicitly.
- If WS1006 recovery becomes process-restart-required, the blocker must be current-session precise, not stale tail churn.
- If skipped-only rebalance is treated as a blocker, the feed guard is too aggressive.

## Hermes Review
- Keep `core/kite_depth_ws.py` as the truth source for option-feed verification state and recovery-blocked evidence.
- Keep `feed_stability_agent.py` parsing-only over logs and runtime snapshots.
- Keep `live_rca_agent.py` current-session scoped, with stale historical tail evidence visible but non-dominant.
- Keep `command_center.py` mapping the first current-session blocker to the right action class.

## GSD Review
- Add option-feed verification begin/waiting/ok/failed evidence events and overlay state.
- Add current-session metrics for subscribe count, verify counts, recovery-blocked counts, and stale SLO counts.
- Classify no-live-option-feed-after-subscribe and WS1006 process-restart-required explicitly.
- Preserve skipped-only rebalance as safety-positive evidence.
- Add tests for fresh current-session feed health beating stale feed churn.

## QA / Safety Review
- Verify every report remains read_only and non-ordering.
- Verify skipped-only rebalance does not become a blocker.
- Verify option verification failure is surfaced before stale FEED_REBALANCE_APPLIED blame.
- Verify current-session feed health can coexist with stale historical churn in diagnostics.
- Verify no strategy, ranking, Phase2, broker, order, dashboard, or websocket runtime behavior changed.

## High-Risk Path Review
- `core/kite_depth_ws.py` was changed only to separate subscription request from verified live option ticks and to keep recovery-blocked evidence explicit.
- The feed runtime mutation guard still fails closed on disconnected or degraded websocket state.
- No broker, order, execution, strategy, ranking, or dashboard paths were changed.
- The runtime behavior remains conservative: subscription intent alone never implies verified live option feed truth.

## Live Evidence Summary
- `FEED_ON_CONNECT_SUBSCRIBE` and `FEED_RESUBSCRIBE` now lead into explicit option-feed verification rather than implying success.
- `FEED_OPTION_VERIFY_BEGIN`, `FEED_OPTION_VERIFY_WAITING_TICKS`, `FEED_OPTION_VERIFY_OK`, and `FEED_OPTION_VERIFY_FAILED` make live option truth observable.
- `NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE`, `OPTION_FEED_VERIFY_TIMEOUT`, `WS1006_PROCESS_RESTART_REQUIRED`, and `RECOVERY_BLOCKED` are classified separately from generic churn.
- Skipped-only rebalance evidence remains visible but does not force `FEED_REBALANCE_APPLIED` blame.
- Command center reports current-session blockers instead of stale tail feed churn when current-session feed truth is healthy.

## What Changed
- Added option-feed verification state and event logging in `core/kite_depth_ws.py`.
- Added feed stability metrics for current-session subscribe/verify/recovery evidence.
- Updated live RCA classification to prefer current-session live option truth and WS1006 recovery blockers.
- Updated command center mapping and metrics to avoid stale feed churn blame when current-session truth is healthy.
- Added deterministic tests for websocket, feed stability, live RCA, and command center evidence.

## What Was Not Changed
- Strategy generation.
- Ranking / scoring / Phase2 logic.
- Feed lifecycle runtime behavior beyond evidence reporting.
- Broker / order / execution behavior.
- Dashboard / UI behavior.

## Safety Summary
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- No runtime mutation outside evidence classification and RCA text.

## Tests Run
- `PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py tests/test_feed_stability_agent.py tests/test_live_rca_agent.py tests/test_agent_command_center.py -vv`
- `PYTHONPATH=. python scripts/run_tradebot_agent_command_center.py --runtime-dir .runtime --logs-dir logs --out-dir .runtime/agent_reports --agents all --format both`
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py`

## Acceptance Proof
- Current-session option verification is no longer conflated with subscription intent.
- Live option tick verification is explicit and auditable.
- Skipped-only rebalance remains safety-positive and non-blocking.
- WS1006 recovery-required evidence is no longer misreported as stale feed churn.
- Command center now prefers current-session truth over stale historical tail evidence.

## Runtime Proof Required After Merge
- Re-run `PYTHONPATH=. python scripts/run_tradebot_agent_command_center.py --runtime-dir .runtime --logs-dir logs --out-dir .runtime/agent_reports --agents all --format both`.
- Re-run `python scripts/validate_agent_review_evidence.py --base-ref origin/main`.
- Re-run the repo CE gate on the changed paths file.

## What This PR Does Not Prove
- It does not prove the market feed is always healthy.
- It does not prove market edge or profitability.
- It does not change runtime trading behavior.
- It does not eliminate historical feed churn from diagnostics.

## Human Approval
- Approved only for scoped evidence-classification changes that keep stale tail churn diagnostic-only when current-session feed truth is healthy.
- Do not let a stale `FEED_REBALANCE_APPLIED` line trigger a false feed lifecycle stabilization call when the current session has fresh feed truth.

## Rollback Plan
- Revert `core/kite_depth_ws.py`, `core/agents/feed_stability_agent.py`, `core/agents/live_rca_agent.py`, and `core/agents/command_center.py` together if attribution proves misleading in live evidence.
- Keep the doc and tests as the rollback verification baseline only if the code revert is required.
- Re-run the focused tests and command-center evidence generation after any rollback.
