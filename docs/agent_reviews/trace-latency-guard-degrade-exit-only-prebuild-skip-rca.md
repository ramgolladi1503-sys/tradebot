# Trace Latency Guard Degrade Exit-Only Prebuild Skip RCA

mode: REVIEW
candidate_id: PR-TRACE-LATENCY-GUARD-DEGRADE-EXIT-ONLY-PREBUILD-SKIP-RCA
decision: add_read_only_latency_guard_evidence
reason: Live evidence showed `LATENCY_GUARD_DEGRADE_EXIT_ONLY_PREBUILD_SKIP` blocking strategy generation while feed freshness and indicator readiness were healthy. This PR adds read-only evidence to expose the exact latency metric, threshold, and guard source behind the prebuild skip.
timestamp: 2026-06-03T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/trace-latency-guard-degrade-exit-only-prebuild-skip-rca.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (evidence-only runtime trace + deterministic tests)
title: Trace latency guard degrade exit-only prebuild skip RCA
scope: add read-only evidence identifying the exact latency source that triggers LATENCY_GUARD_DEGRADE_EXIT_ONLY_PREBUILD_SKIP
requested_paths:
  - core/orchestrator.py
  - core/runtime_candidate_flow_trace.py
  - core/runtime_strategy_no_qualified_reasons.py
  - tests/test_orchestrator_latency_accounting.py
  - tests/test_candidate_flow_trace_evidence.py
  - tests/test_strategy_no_qualified_reasons_evidence.py
  - docs/agent_reviews/trace-latency-guard-degrade-exit-only-prebuild-skip-rca.md
allowed_paths:
  - core/orchestrator.py
  - core/runtime_candidate_flow_trace.py
  - core/runtime_strategy_no_qualified_reasons.py
  - tests/test_orchestrator_latency_accounting.py
  - tests/test_candidate_flow_trace_evidence.py
  - tests/test_strategy_no_qualified_reasons_evidence.py
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
  - latency guard evidence unit tests
  - candidate-flow / notrade evidence tests
  - full pytest suite
  - agent review evidence validator
  - unified CE gates
acceptance_proof:
  - the artifact surfaces latency_guard_triggered, latency_guard_mode, latency_guard_action, latency_guard_source, latency_guard_reason, metric/value/threshold, and recovery flags
  - candidate_flow_trace_latest.json and strategy_no_qualified_reasons_latest.json both carry the same latency guard reason
  - healthy latency does not prebuild-skip
  - degraded latency does prebuild-skip in evidence, while unknown state fails closed with explicit evidence
  - flags: read_only=true, append=false, is_order_action=false, broker_api_called=false, live_order_allowed=false
```

## Purpose

PR #463 live evidence verified that indicator readiness is healthy and the first remaining blocker is a latency guard prebuild skip. This PR adds evidence-only wiring so the next live run can answer which latency metric, threshold, and guard source trigger the skip.

## Files Changed

- `/Users/madhuram/tradebot/core/orchestrator.py`
  - Adds evidence-only latency guard context derivation and passes it into the latest trace writers.
- `/Users/madhuram/tradebot/core/runtime_candidate_flow_trace.py`
  - Adds structured latency guard fields to the candidate-flow trace payload.
- `/Users/madhuram/tradebot/core/runtime_strategy_no_qualified_reasons.py`
  - Adds structured latency guard fields to the no-qualified evidence payload.
- `/Users/madhuram/tradebot/tests/test_orchestrator_latency_accounting.py`
  - Adds deterministic tests for healthy, degraded, and unknown latency-guard evidence.
- `/Users/madhuram/tradebot/tests/test_candidate_flow_trace_evidence.py`
  - Verifies latency guard fields are carried into candidate-flow evidence.
- `/Users/madhuram/tradebot/tests/test_strategy_no_qualified_reasons_evidence.py`
  - Verifies latency guard fields are carried into strategy no-qualified evidence.
- `/Users/madhuram/tradebot/docs/agent_reviews/trace-latency-guard-degrade-exit-only-prebuild-skip-rca.md`
  - Records scope, safety review, and runtime-proof expectations.

## High-Risk Path Review

High-risk file changed: `/Users/madhuram/tradebot/core/orchestrator.py`.

Review outcome:
- The change is evidence-only and does not alter broker/order execution, candidate creation, ranking, or Phase2 behavior.
- It reads the existing latency guard state and writes structured evidence fields.
- Failures in evidence writing remain non-fatal.

Residual risk:
- If the latency guard state is missing or stale, the evidence intentionally fails closed and reports `latency_guard_state_unknown`.

## Scope Guard

### In Scope

- Identify the exact latency guard metric/source causing `LATENCY_GUARD_DEGRADE_EXIT_ONLY_PREBUILD_SKIP`.
- Expose evidence fields:
  - `latency_guard_triggered`
  - `latency_guard_mode`
  - `latency_guard_action`
  - `latency_guard_source`
  - `latency_guard_reason`
  - `latency_guard_metric`
  - `latency_guard_value`
  - `latency_guard_threshold`
  - `latency_guard_age_sec`
  - `latency_guard_last_ok_at`
  - `latency_guard_last_bad_at`
  - `latency_guard_recovery_required`

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

- The evidence does not collapse distinct latency sources into a generic label when the monitor exposes the breached metric.
- Unknown or missing guard state is reported as `latency_guard_state_unknown` and fails closed in evidence.
- Writing the artifact does not alter candidate generation or any runtime decision path.

### Verdict

PASS — evidence-only wiring with explicit fail-closed behavior.

## Hermes Review

### Contract / Architecture Check

- [x] Evidence schema is explicit and versioned.
- [x] Writer provenance is included.
- [x] Safety fields are present.
- [x] The trace and no-qualified evidence carry the same latency guard reason.
- [x] Failure path is observable and fail-closed.

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Tests prove healthy vs degraded vs unknown behavior.
- [x] The exact latency metric/value/threshold/source is surfaced.
- [x] Candidate-flow and strategy evidence both include the latency guard context.
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
- `latency_guard_triggered`
- `latency_guard_mode`
- `latency_guard_action`
- `latency_guard_source`
- `latency_guard_reason`
- `latency_guard_metric`
- `latency_guard_value`
- `latency_guard_threshold`
- `latency_guard_age_sec`
- `latency_guard_last_ok_at`
- `latency_guard_last_bad_at`
- `latency_guard_recovery_required`

### Commands Run

```bash
PYTHONPATH=. python -m pytest -q tests/test_orchestrator_latency_accounting.py tests/test_candidate_flow_trace_evidence.py tests/test_strategy_no_qualified_reasons_evidence.py
PYTHONPATH=. python -m pytest -q tests -k "latency_guard or candidate_flow or strategy_no_qualified or notrade_reason_truth"
PYTHONPATH=. python -m pytest -q tests
python scripts/validate_agent_review_evidence.py
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file <generated-file>
```

## Runtime Proof Required After Merge

Required next live validation:
- run observation-only live session during market hours
- inspect:
  - `logs/candidate_flow_trace_latest.json`
  - `logs/strategy_no_qualified_reasons_latest.json`
  - `logs/notrade_reason_truth_latest.json`
  - `logs/feed_runtime_latest.json`
- confirm:
  - the latency guard fields show the exact metric and threshold
  - `LATENCY_GUARD_DEGRADE_EXIT_ONLY_PREBUILD_SKIP` is explained explicitly
  - healthy latency remains non-blocking
  - unknown latency state fails closed in evidence

## What This PR Does Not Prove

- It does not prove the latency thresholds need to be changed.
- It does not prove the feed or indicator logic is wrong.
- It does not prove any strategy generates candidates.
- It does not make candidates executable.

## Human Approval

This PR must remain draft until a human reviews the evidence-only latency guard tracing and the next live validation output.
