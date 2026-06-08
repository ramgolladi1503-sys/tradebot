# PR #502 — Agent Command Center Session-Scoped RCA Evidence

mode: REVIEW
candidate_id: PR-502-AGENT-COMMAND-CENTER-SESSION-SCOPED-RCA
decision: fix_agent_command_center_rca_scoping
reason: Distinguish current-session feed evidence from stale historical tail evidence so feed lifecycle churn does not dominate the RCA when current gate evidence is healthy.
timestamp: 2026-06-08T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/command-center-session-scoped-rca.md

## Agent Work Contract
- **source_agent:** GSD
- **action:** Generate patch, tests, docs, and validation for a scoped RCA evidence fix
- **title:** Agent Command Center Session-Scoped RCA Evidence
- **scope:** Distinguish current-session evidence from stale historical feed churn in agent RCA outputs without changing runtime trading behavior
- **requested_paths:** `core/agents/readers.py`, `core/agents/feed_stability_agent.py`, `core/agents/live_rca_agent.py`, `core/agents/command_center.py`, `scripts/run_tradebot_agent_command_center.py`, `tests/test_agent_command_center.py`, `tests/test_feed_stability_agent.py`, `tests/test_live_rca_agent.py`, `docs/agent_reviews/command-center-session-scoped-rca.md`
- **allowed_paths:** Same as requested paths
- **forbidden_paths:** `core/orchestrator.py`, `core/candidate_scoring.py`, `core/expectancy/*`, `core/review_queue.py`, `strategies/*`, `dashboard/*`, broker/order/execution files, websocket runtime behavior files unless explicitly proven current-session churn
- **expected_tests:** `PYTHONPATH=. pytest -q tests/test_agent_command_center.py tests/test_feed_stability_agent.py tests/test_live_rca_agent.py -vv`
- **acceptance_proof:** Current feed health beats stale feed churn; current-session blockers remain visible; safety summary stays read-only and non-ordering

## Scope Guard
- Do not change broker, order, execution, strategy, ranking, Phase2, or dashboard behavior.
- Do not weaken stale-feed safety gates.
- Do not suppress evidence; classify it correctly.
- Do not let historical tail feed churn dominate the RCA when current-session feed evidence is healthy.

## Grill Me Review
- If the current session is fresh but the command center still recommends feed lifecycle stabilization, that is a bug.
- If historical depth watchdog churn can still outrank a fresh current-session feed health signal, the scoping fix is incomplete.
- If the command center hides stale evidence instead of labeling it historical, the report is misleading.

## Hermes Review
- Preserve the evidence pipeline.
- Add session-scoping helpers in the agent readers/agents layer.
- Use current-session feed freshness as the guardrail for whether historical feed churn is explanatory or merely diagnostic.
- Keep stale evidence visible in diagnostics, but prevent it from choosing the next PR recommendation when contradicted by current-session health.

## GSD Review
- Implement the smallest patch that distinguishes current-session vs historical-tail RCA evidence.
- Add deterministic tests that prove current-session feed health beats stale churn, current-session churn still blocks, and strategy-select no-candidate evidence is surfaced when feed health is fresh.
- Update the command center output to report evidence scope and current-session blocker metadata.

## QA / Safety Review
- Verify `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `live_order_allowed=false`, and `append=false` in the agent reports.
- Verify the command center remains diagnostic-only and does not trigger broker/order/runtime side effects.
- Verify stale historical churn remains visible in evidence and markdown.

## Acceptance Proof
- `tests/test_agent_command_center.py`
  - Fresh feed health with stale depth watchdog churn must not return `FEED_STABILITY`.
  - Current-session feed churn must still return `FEED_STABILITY`.
  - Fresh feed with `N8_STRATEGY_SELECT / NO_STRATEGY_QUALIFIED` must return a candidate/strategy supply blocker, not feed stability.
- `tests/test_feed_stability_agent.py`
  - Historical tail churn is labeled historical when current-session feed freshness is healthy.
  - Current-session churn remains current and blocks.
- `tests/test_live_rca_agent.py`
  - Current-session strategy-select no-candidate evidence is surfaced.
  - Current-session churn remains a subscription-churn RCA.

## Runtime Proof Required After Merge
- Run `PYTHONPATH=. python scripts/run_tradebot_agent_command_center.py --runtime-dir .runtime --logs-dir logs --out-dir .runtime/agent_reports --agents all --format both` on current evidence.
- Re-run `python scripts/validate_agent_review_evidence.py --base-ref origin/main`.
- Re-run the repo CE gate on the changed paths file.

## What This PR Does Not Prove
- It does not prove the strategy layer is generating enough candidates.
- It does not prove market edge.
- It does not prove feed churn can never happen.
- It does not change runtime trading behavior.

## Human Approval
- Approved for scoped implementation only if the command center uses current-session-scoped evidence to avoid stale feed churn dominating the recommendation.
- If the current-session feed is healthy, the next PR recommendation must not be a false feed lifecycle stabilization call.
