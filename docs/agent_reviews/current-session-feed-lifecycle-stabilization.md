# Current-Session Feed Lifecycle Stabilization

mode: REVIEW
candidate_id: PR-522-CURRENT-SESSION-FEED-LIFECYCLE-STABILIZATION
decision: stabilize_current_session_feed_lifecycle_evidence_scoping
reason: Prevent stale historical feed churn from dominating current-session RCA, and block subscription rebalance mutation when websocket/feed runtime truth is genuinely unhealthy.
timestamp: 2026-06-08T00:00:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/current-session-feed-lifecycle-stabilization.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (minimal websocket/feed lifecycle safety fix + offline regression tests + docs)
title: Current-Session Feed Lifecycle Stabilization
scope: block rebalance mutation on dead/recovering/degraded current-session feed truth, keep stale historical feed churn visible but non-dominant, and render candidate-supply-zero attribution in command-center markdown
requested_paths:
  - core/kite_depth_ws.py
  - core/agents/feed_stability_agent.py
  - core/agents/command_center.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_feed_stability_agent.py
  - tests/test_agent_command_center.py
  - docs/agent_reviews/current-session-feed-lifecycle-stabilization.md
allowed_paths:
  - core/kite_depth_ws.py
  - core/agents/feed_stability_agent.py
  - core/agents/command_center.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_feed_stability_agent.py
  - tests/test_agent_command_center.py
  - docs/agent_reviews/*
forbidden_paths:
  - strategies/*
  - dashboard/*
  - core/orchestrator.py
  - core/candidate_scoring.py
  - core/expectancy/*
  - core/review_queue.py
  - core/broker*
  - core/order*
  - execution_engine/*
  - runtime/*
  - logs/*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py tests/test_feed_stability_agent.py tests/test_live_rca_agent.py tests/test_agent_command_center.py tests/test_candidate_supply_agent.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py
acceptance_proof:
  - FEED_REBALANCE_SKIPPED is emitted for ineligible mutation with explicit reason
  - FEED_REBALANCE_APPLIED is not emitted when ws is disconnected/recovering/degraded
  - Healthy connected websocket still allows safe rebalance when current-session feed truth is healthy
  - Feed stability RCA reports current-session mutation-on-dead-WS and ignores stale historical churn as the primary blocker
  - Command center prefers current-session feed truth over historical tail evidence when they contradict
  - Candidate-supply-zero attribution renders in markdown and stays visible without replacing feed truth diagnostics
```

## Scope Guard

- This PR is a feed lifecycle safety and RCA-scoping regression guard.
- It must not change strategy, ranking, Phase 2, broker/order, or dashboard behavior.
- It must fail closed on genuine websocket/feed runtime truth degradation.

## High-Risk Path Review

- `core/kite_depth_ws.py` is high risk because it owns subscription rebalance and feed runtime truth emission.
- The patch is intentionally narrow: it blocks rebalance mutation only when published feed/runtime truth is unhealthy.
- Legitimate stale-option recovery remains available when the current-session feed is healthy.

## Closed-Environment / Off-Market Rule

- All validation is offline and deterministic.
- No live Kite session is required.
- No broker calls are allowed.
- No real websocket connection is opened in tests.

## Live Evidence Summary

- Fresh current-session gate truth shows `N2_FEED_FRESH` healthy with websocket connected.
- The actual blocker is downstream at candidate supply / strategy select when no candidate can be constructed.
- Historical `FEED_REBALANCE_APPLIED` / `WS1006` lines remain useful diagnostics, but they must not dominate current-session RCA when current feed truth is healthy.

## Grill Me Review

- The main risk is over-blocking a legitimate stale-option refresh path.
- The test suite must prove the guard blocks only on genuine current-session feed truth degradation, not on stale in-memory freshness alone.
- Historical churn must remain visible in diagnostics without becoming the next-pr recommendation when current-session feed health is good.

## Hermes Review

- The safest boundary is the mutation guard and agent RCA evidence scoping.
- Published feed runtime truth should outrank tail logs when they disagree.
- Candidate supply attribution should remain explicit and separate from feed lifecycle failures.

## GSD Review

- Changes are narrowly scoped to websocket/feed guard logic, agent RCA summaries, and offline regression tests.
- No unrelated runtime, strategy, ranking, or broker execution changes are included.

## QA / Safety Review

- `read_only=true` where applicable.
- `is_order_action=false`.
- `broker_api_called=false`.
- `append=false` for evidence artifacts.
- Safety-positive skipped mutation must remain visible as a non-blocking diagnostic.

## Acceptance Proof

- ws-disconnected mutation attempts emit `FEED_REBALANCE_SKIPPED` with `guard_reason=ws_disconnected`.
- recovery-blocked / degraded current-session feed truth blocks mutation and emits `FEED_REBALANCE_SKIPPED`.
- healthy connected websocket still emits `FEED_REBALANCE_APPLIED` for safe rebalance.
- `feed_stability_agent` identifies current-session mutation-on-dead-WS and counts skipped rebalance as safety-positive evidence.
- `command_center` renders candidate-supply-zero attribution in markdown and preserves current-session feed truth precedence.

## Validation Commands

- `PYTHONPATH=. pytest -q tests/test_kite_depth_ws_stability.py tests/test_feed_stability_agent.py tests/test_live_rca_agent.py tests/test_agent_command_center.py tests/test_candidate_supply_agent.py -vv`
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py`

## Expected Changed Files

- `core/kite_depth_ws.py`
- `core/agents/feed_stability_agent.py`
- `core/agents/command_center.py`
- `tests/test_kite_depth_ws_stability.py`
- `tests/test_feed_stability_agent.py`
- `tests/test_agent_command_center.py`
- `docs/agent_reviews/current-session-feed-lifecycle-stabilization.md`

## Forbidden Scope Not Touched

- `strategies/*`
- `dashboard/*`
- `core/orchestrator.py`
- `core/candidate_scoring.py`
- `core/expectancy/*`
- `core/review_queue.py`
- `core/broker*`
- `core/order*`
- `runtime/*`
- `logs/*`

## Risk Assessment

- Medium risk because the patch touches websocket mutation gating.
- The main failure mode would be over-blocking a recoverable stale-option refresh path; the tests must prove this does not happen.

## Rollback Plan

- Revert the mutation guard and the agent RCA scope changes if the guard proves too aggressive.
- Keep the tests and evidence doc as the baseline for future review.

## Runtime Proof Required After Merge

- Run a fresh current-session session and confirm `FEED_REBALANCE_SKIPPED` occurs only for ineligible mutation.
- Confirm a healthy websocket still permits safe rebalance.
- Confirm current-session feed health wins over stale historical churn in command-center RCA.

## What This PR Does Not Prove

- It does not prove trading edge or profitability.
- It does not prove live market performance.
- It does not change any ranking or execution logic.

## Why This Does Not Prove Trading Edge

- The PR only corrects feed lifecycle safety and evidence scoping.
- It does not improve candidate quality, execution quality, or market edge.

## Future Work Explicitly Out of Scope

- Any runtime websocket architecture rewrite.
- Any change to candidate generation or execution truth.
- Any feed-truth schema change beyond existing evidence fields.

## Human Approval

This PR is safe to review as a focused websocket/feed lifecycle stabilization and RCA-scoping guard.
It does not change trading decisions, order behavior, or dashboard behavior.
