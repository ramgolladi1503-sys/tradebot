# Trace Strategy No-Qualified Reasons

mode: REVIEW
candidate_id: PR-TRACE-STRATEGY-NO-QUALIFIED-REASONS
decision: add_read_only_strategy_no_qualified_evidence
reason: NO_STRATEGY_QUALIFIED currently has insufficient per-symbol setup-failure evidence after feed indicators and regime are ready.
timestamp: 2026-06-02T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/trace-strategy-no-qualified-reasons.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (evidence-only runtime trace + deterministic tests)
title: Trace strategy no-qualified reasons
scope: add read-only evidence explaining NO_STRATEGY_QUALIFIED when feed, indicators, and regime are ready but strategy generation produces zero raw candidates
requested_paths:
  - core/runtime_strategy_no_qualified_reasons.py
  - core/orchestrator.py
  - tests/test_strategy_no_qualified_reasons_evidence.py
  - docs/agent_reviews/trace-strategy-no-qualified-reasons.md
allowed_paths:
  - core/runtime_strategy_no_qualified_reasons.py
  - core/orchestrator.py
  - tests/test_strategy_no_qualified_reasons_evidence.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - core/feed*
  - strategies/*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - tests/test_strategy_no_qualified_reasons_evidence.py
  - candidate/phase2/notrade focused pytest group
  - full pytest suite
  - agent review evidence validator
  - unified CE gates
acceptance_proof:
  - read-only artifacts are emitted to logs, runtime, and runtime/logs latest paths
  - strategy no-qualified evidence is applicable only when feed/indicator/regime blockers are absent
  - per-symbol and per-strategy attempts record trade-builder execution and candidate-drop distinction
  - non-action contract remains append=false, is_order_action=false, broker_api_called=false, live_order_allowed=false, with read_only asserted by tests
```

## Purpose

PR #458 live evidence showed candidate flow reaching `first_zero_stage=strategy_generation_zero` with `NO_STRATEGY_QUALIFIED` after feed, indicator readiness, and regime readiness were healthy. This PR adds evidence only so the next live run can identify the exact failed setup category per symbol and strategy.

Follow-on PR #462 tightened the predicate evidence and this branch now aligns N8 indicator truth with the same current-cycle readiness source used by candidate-flow and notrade evidence. This review note remains the evidence contract for that read-only wiring.

## Files Changed

- `/Users/madhuram/tradebot/core/runtime_strategy_no_qualified_reasons.py`
  - Adds a pure schema-v1 builder, reason categorizer, attempt builders, and latest-json writer for strategy no-qualified evidence.
- `/Users/madhuram/tradebot/core/orchestrator.py`
  - Collects evidence-only strategy gate and trade-builder attempt rows, then writes the latest artifact in the existing finalizer.
- `/Users/madhuram/tradebot/tests/test_strategy_no_qualified_reasons_evidence.py`
  - Adds deterministic tests for applicability, safety flags, per-symbol/per-strategy detail, candidate-drop distinction, and writer paths.
- `/Users/madhuram/tradebot/docs/agent_reviews/trace-strategy-no-qualified-reasons.md`
  - Records scope, safety review, acceptance proof, and runtime validation expectations.

## High-Risk Path Review

High-risk file changed: `/Users/madhuram/tradebot/core/orchestrator.py`.

Review outcome:
- The orchestrator change only appends dictionaries to an evidence list and writes a read-only artifact.
- No broker/order execution code was modified.
- No strategy formulas, thresholds, Phase2 behavior, ranking/scoring, or strike-window behavior was modified.
- Evidence write failures are logged and non-fatal; they do not change trading decisions.

Residual risk:
- If existing strategy telemetry is sparse, the artifact uses `reason_category="unknown"` instead of inventing precision.
- The first live run may still require follow-up if the true failed condition is hidden inside strategy internals not exposed by current traces.

## Scope Guard

### In Scope

- Add read-only evidence artifacts:
  - `logs/strategy_no_qualified_reasons_latest.json`
  - `.runtime/strategy_no_qualified_reasons_latest.json`
  - `.runtime/logs/strategy_no_qualified_reasons_latest.json`
- Explain per-symbol and per-strategy no-qualified reasons when current-cycle blockers indicate `NO_STRATEGY_QUALIFIED`.
- Distinguish no setup from generated-then-dropped candidates.

### Out of Scope

- Broker/order code
- Live safety behavior
- Strategy formulas
- Threshold tuning
- Ranking/scoring
- Phase2 behavior
- Strike-window behavior
- Dashboard/UI

### Boundary Verification

- [x] No broker calls added
- [x] No order actions added
- [x] No gate bypass added
- [x] No candidates forced or faked
- [x] No strategy behavior changed
- [x] No thresholds changed

## Grill Me Review

### Challenge

- Could this evidence accidentally make NO_STRATEGY_QUALIFIED look actionable when feed, indicators, or regime are still blocked?
- Could the categorizer fake precision?
- Could writing the artifact affect candidate counts?

### Findings

- Applicability is false when feed, indicator, or regime blockers are present.
- Unknown or sparse evidence is classified as `unknown`, not coerced into a preferred bucket.
- Raw candidate and Phase2 counts are passed through unchanged; the module has no candidate creation path.

### Verdict

PASS — the change improves observability without changing execution behavior.

## Hermes Review

### Contract / Architecture Check

- [x] Evidence schema is explicit and versioned.
- [x] Writer provenance is included.
- [x] Safety fields are present.
- [x] Artifact mirrors existing latest-json evidence conventions.
- [x] Failure path is observable and fail-closed.

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Tests prove behavior, not only shape.
- [x] Evidence distinguishes no setup from generated-then-dropped candidates.
- [x] Writer writes all required latest paths.
- [x] No strategy or broker/order behavior changed.

### Verdict

PASS

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched.
- No live-order behavior changed.
- No feed, indicator, regime, or risk gate bypass added.
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

The artifact includes:
- schema/provenance fields
- safety flags
- `symbols_evaluated`
- `strategies_attempted`
- `strategy_generation_attempt_count`
- `no_setup_qualified_count`
- `candidate_generated_then_dropped_count`
- `reason_categories`
- `by_symbol`
- `by_strategy`
- `raw_candidate_count`
- `phase2_input_candidate_count`
- `strategy_no_qualified_applicable`
- `not_applicable_reason`

### Commands Run

```bash
PYTHONPATH=. python -m pytest -q tests/test_strategy_no_qualified_reasons_evidence.py
PYTHONPATH=. python -m pytest -q tests -k "strategy_no_qualified or candidate_flow or phase2 or trade_builder or notrade_reason_truth"
PYTHONPATH=. python -m pytest -q tests
python scripts/validate_agent_review_evidence.py
PYTHONPATH=. python scripts/run_unified_ce_gates.py
```

## Runtime Proof Required After Merge

Required next live validation:
- run observation-only live session during market hours
- inspect:
  - `logs/strategy_no_qualified_reasons_latest.json`
  - `.runtime/strategy_no_qualified_reasons_latest.json`
  - `.runtime/logs/strategy_no_qualified_reasons_latest.json`
  - `logs/candidate_flow_trace_latest.json`
- confirm:
  - `strategy_no_qualified_applicable=true` only when feed/indicators/regime are ready
  - `NO_STRATEGY_QUALIFIED` attempts are present per symbol
  - failed setup categories are explicit or `unknown`
  - no broker/order action strings appear in live logs

## What This PR Does Not Prove

- It does not prove any strategy should generate candidates.
- It does not tune or relax any strategy condition.
- It does not make candidates executable.
- It does not prove Phase2 ranking quality.

## Human Approval

This PR must remain draft until a human reviews the evidence-only orchestrator hook and live validation output.
