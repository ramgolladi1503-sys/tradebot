# Trace Executable Truth Normalization Under Stale Feed

mode: REVIEW
candidate_id: PR-TRACE-EXECUTABLE-TRUTH-NORMALIZATION-UNDER-STALE-FEED
decision: add_read_only_execution_truth_evidence
reason: Live audit evidence showed stale feed / recovery-blocked / latency-guard-degraded runtime states still producing executable-looking candidate evidence. This PR adds read-only normalization so top candidate and phase2 evidence remain fail-closed and truth-consistent under stale feed conditions.
timestamp: 2026-06-04T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/trace-executable-truth-normalization-under-stale-feed.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (evidence-only runtime normalization + deterministic tests)
title: Trace executable truth normalization under stale feed
scope: normalize candidate and phase2 evidence so stale feed, recovery-blocked, and latency-guard-degraded states cannot appear executable in logs
requested_paths:
  - core/orchestrator.py
  - core/runtime_execution_truth.py
  - core/runtime_phase2_rejection_evidence.py
  - tests/test_runtime_execution_truth_evidence.py
  - tests/test_candidate_flow_trace_evidence.py
  - tests/test_phase2_rejection_evidence_artifact.py
  - docs/agent_reviews/trace-executable-truth-normalization-under-stale-feed.md
allowed_paths:
  - core/orchestrator.py
  - core/runtime_execution_truth.py
  - core/runtime_phase2_rejection_evidence.py
  - tests/test_runtime_execution_truth_evidence.py
  - tests/test_candidate_flow_trace_evidence.py
  - tests/test_phase2_rejection_evidence_artifact.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - strategies/*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - execution truth evidence unit tests
  - candidate-flow / phase2 evidence tests
  - full pytest suite
  - agent review evidence validator
  - unified CE gates
acceptance_proof:
  - stale feed / ws disconnected / RECOVERY_BLOCKED / latency guard degraded states are normalized to non-executable evidence
  - top executable opportunities are suppressed when execution truth is blocked
  - phase2 rejection evidence carries concrete hard blocker details
  - flags: read_only=true, append=false, is_order_action=false, broker_api_called=false
```

## Purpose

Live audits after the WS1006 recovery work showed a mismatch between runtime truth and candidate evidence: stale feed or recovery-blocked states could still look executable in top-candidate logs. This PR adds evidence-only normalization so runtime logs stay fail-closed and reflect the true execution state.

## Files Changed

- `/Users/madhuram/tradebot/core/orchestrator.py`
  - Passes current execution truth context into candidate and top-opportunity evidence writers.
  - Normalizes reportable candidate evidence when feed or recovery state is blocked.
- `/Users/madhuram/tradebot/core/runtime_execution_truth.py`
  - New pure helper that derives execution truth and normalizes candidate payloads.
- `/Users/madhuram/tradebot/core/runtime_phase2_rejection_evidence.py`
  - Adds hard execution blocker categorization and detailed blocker reporting.
- `/Users/madhuram/tradebot/tests/test_runtime_execution_truth_evidence.py`
  - Verifies blocked, advisory, and feed-truth normalization behavior.
- `/Users/madhuram/tradebot/tests/test_candidate_flow_trace_evidence.py`
  - Verifies candidate-flow trace remains truth-consistent.
- `/Users/madhuram/tradebot/tests/test_phase2_rejection_evidence_artifact.py`
  - Verifies phase2 rejection evidence includes hard blocker details.
- `/Users/madhuram/tradebot/docs/agent_reviews/trace-executable-truth-normalization-under-stale-feed.md`
  - Records scope, safety review, and runtime-proof expectations.

## High-Risk Path Review

High-risk file changed: `/Users/madhuram/tradebot/core/orchestrator.py`.

Review outcome:
- The change is evidence-only and does not alter broker/order execution, candidate creation, ranking, or Phase2 behavior.
- It consumes existing runtime truth signals and emits normalized evidence fields.
- Failures in evidence writing remain non-fatal.

Residual risk:
- If runtime truth context is absent or stale, evidence fails closed and reports non-executable visibility rather than inventing executable state.

## Scope Guard

### In Scope

- Normalize candidate evidence under stale feed / recovery blocked / latency guard states.
- Expose execution truth fields:
  - `execution_truth_state`
  - `execution_truth_blocked`
  - `execution_truth_advisory`
  - `execution_truth_blockers`
  - `execution_truth_source`
  - `visibility_bucket`
  - `reportable_executable`
  - `execution_allowed`
  - `eligible_for_execution`
  - `permission`
  - `final_action`
  - `execution_status`
  - `readiness`
  - `candidate_status`
- Emit hard blocker details for phase2 rejection evidence.

### Out of Scope

- Broker/order code
- Strategy formulas and thresholds
- Ranking and Phase2 behavior
- Dashboard/UI work
- Live-order behavior

### Boundary Verification

- [x] No broker calls added
- [x] No order actions added
- [x] No gate bypass added
- [x] No candidate counts are faked
- [x] No strategy behavior changed
- [x] No threshold changes

## Grill Me Review

### Risks Addressed

- Stale feed and recovery-blocked states can no longer look executable in candidate evidence.
- Advisory latency-guard states are separated from executable truth.
- Unknown or missing guard state fails closed in evidence instead of inventing an executable path.

### Verdict

PASS — evidence-only normalization with explicit fail-closed behavior.

## Hermes Review

### Contract / Architecture Check

- [x] Evidence schema is explicit and versioned.
- [x] Writer provenance is included.
- [x] Safety fields are present.
- [x] Candidate-flow, top-opportunity, and phase2 rejection evidence are consistent.
- [x] Failure path is observable and fail-closed.

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Tests prove blocked vs advisory vs executable truth handling.
- [x] Candidate-flow and phase2 evidence remain consistent with runtime truth.
- [x] No runtime behavior outside evidence changed.

### Verdict

PASS

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched.
- No live-order behavior changed.
- No feed, indicator, regime, or strategy predicate gate bypass added.
- No strategy formula or threshold changed.
- No Phase2 or ranking behavior changed.

Evidence/runtime safety flags preserved:
- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`

## Acceptance Proof

### Evidence Contract

The artifacts include:
- schema/provenance fields
- safety flags
- execution truth blocker details
- non-executable normalization for stale feed / recovery blocked / latency guard advisory states
- phase2 hard blocker categorization

### Commands Run

```bash
PYTHONPATH=. python -m pytest -q tests/test_runtime_execution_truth_evidence.py tests/test_candidate_flow_trace_evidence.py tests/test_phase2_rejection_evidence_artifact.py tests/test_ranked_pipeline_runtime_evidence_wiring.py tests/test_runtime_truth_consistency_pr103.py tests/test_final_emit_truth_contract_pr104.py
PYTHONPATH=. python -m pytest -q tests
python scripts/validate_agent_review_evidence.py
git diff --check
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file <generated-file>
```

## Runtime Proof Required After Merge

Required next live validation:
- run observation-only live session during market hours
- confirm stale feed / recovery-blocked / latency-guard-degraded states no longer emit executable-looking top candidate evidence
- confirm phase2 rejection evidence surfaces hard blockers instead of silent executable normalization

## What This PR Does Not Prove

- This PR does not change strategy logic, ranking math, Phase2 selection, broker/order behavior, or UI.
- This PR does not prove any improvement in trading quality or profitability.
- This PR does not authorize live trading or any order action.

## Human Approval

This PR requires explicit human approval before merge because it touches high-risk orchestrator evidence wiring, even though it remains read-only and fail-closed.
