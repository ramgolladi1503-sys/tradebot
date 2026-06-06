# Execution Truth Normalization Before Candidate Classification

mode: REVIEW
candidate_id: PR-EXECUTION-TRUTH-NORMALIZATION-BEFORE-CANDIDATE-CLASSIFICATION
decision: add_read_only_execution_truth_normalization
reason: Normalize candidate execution truth before classification and reporting so stale/feed/WS/latency blockers cannot leak an executable-looking row into top-candidate, review-queue, or final-emit evidence.
timestamp: 2026-06-06T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/execution-truth-normalization-before-candidate-classification.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (runtime truth normalization + deterministic regression tests + review doc)
title: Execution Truth Normalization Before Candidate Classification
scope: prevent executable-looking candidates from being classified or reported as executable when runtime execution truth contains stale/feed/WS/latency blockers
requested_paths:
  - core/runtime_execution_truth.py
  - core/orchestrator.py
  - core/review_queue.py
  - tests/test_runtime_execution_truth_evidence.py
  - tests/test_review_queue_decision_engine.py
  - docs/agent_reviews/execution-truth-normalization-before-candidate-classification.md
allowed_paths:
  - core/runtime_execution_truth.py
  - core/orchestrator.py
  - core/review_queue.py
  - tests/test_runtime_execution_truth_evidence.py
  - tests/test_review_queue_decision_engine.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/feed_truth_contract.py
  - core/kite_depth_ws.py
  - core/broker*
  - core/order*
  - strategies/*
  - dashboard/*
  - runtime/live*
  - logs/*
  - core/runtime_candidate_flow_trace.py
  - core/runtime_notrade_reason_truth.py
  - core/runtime_strategy_no_qualified_reasons.py
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_runtime_execution_truth_evidence.py -vv
  - PYTHONPATH=. pytest -q tests/test_review_queue_decision_engine.py -vv
  - PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr493_changed_paths.txt
acceptance_proof:
  - blocked execution truth overrides executable-looking fields
  - blocked candidates are never reportable executable or top executable
  - final emit cannot produce EXECUTE when execution truth is blocked
  - healthy candidates still remain executable
```

## Scope Guard

- This PR is off-market and read-only.
- It must not alter strategy logic, ranking math, Phase 2 behavior, broker calls, order behavior, or dashboard/UI behavior.
- It must fail closed when execution truth is blocked.

## Grill Me Review

- Runtime truth must win over executable-looking legacy fields.
- Candidate blockers must be preserved and deduplicated, not hidden.
- Normalization must not make advisory or queue-only candidates silently executable.

## Hermes Review

- The normalization belongs at the execution-truth boundary, before reporting and final emit.
- Reusing the same truth overlay for orchestrator and review-queue paths keeps behavior coherent.
- Blocking fields should override display fields, never the other way around.

## GSD Review

- Changes are limited to runtime truth normalization plus narrow consumer checks in orchestrator/review queue.
- No candidate generation or live feed code is changed.

## QA / Safety Review

- `read_only=true`, `append=false`, `is_order_action=false`, and `broker_api_called=false` remain enforced in evidence paths.
- Execution blockers such as `STALE`, `LTP_STALE`, `WS_DISCONNECTED`, `GLOBAL_FEED_UNHEALTHY`, and latency blockers must keep rows blocked.
- Healthy execution truth remains executable when no blockers are present.

## High-Risk Path Review

- `core/orchestrator.py` and `core/review_queue.py` are high-risk candidate/reporting paths, so the fix is intentionally narrow and truth-only.
- The patch does not change ranking math, strategy formulas, or Phase 2 selection.
- The patch only ensures normalized execution truth is respected before executable reporting and final emit.

## Acceptance Proof

- A candidate with executable-looking fields and blocked runtime truth is normalized to `BLOCK` with `reportable_executable=false`.
- `TB_TOP_EXECUTABLE_CANDIDATE` cannot be emitted for blocked execution truth.
- `TB_TOP_BLOCKED_CANDIDATE` preserves blocker evidence.
- Final emit cannot stay `EXECUTE` when execution truth is blocked.
- Healthy executable candidates still remain executable.

## Runtime Proof Required After Merge

- Re-run the candidate truth evidence suite and confirm blocked payloads never report executable.
- Confirm the review queue final emit path now fails closed on execution-truth blockers.

## What This PR Does Not Prove

- It does not prove trading edge, profitability, or strategy quality.
- It does not change live feed behavior or websocket recovery.
- It does not authorize any live order or broker activity.

## Human Approval

This is safe to review as a narrow execution-truth normalization patch.
