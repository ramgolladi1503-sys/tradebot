# Fix Stale Indicator Blocker Before Strategy Generation

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (narrow runtime correctness fix + tests)
title: Fix stale indicator blocker before strategy generation
scope: prevent false INDICATORS_MISSING when current-cycle indicator readiness is already true
requested_paths:
  - core/decision_dag.py
  - core/runtime_notrade_reason_truth.py
  - core/runtime_candidate_flow_trace.py
  - tests/test_notrade_reason_truth_evidence.py
  - tests/test_candidate_flow_trace_evidence.py
  - tests/test_orchestrator_strategy_gate_once.py
allowed_paths:
  - core/decision_dag.py
  - core/runtime_notrade_reason_truth.py
  - core/runtime_candidate_flow_trace.py
  - tests/test_notrade_reason_truth_evidence.py
  - tests/test_candidate_flow_trace_evidence.py
  - tests/test_orchestrator_strategy_gate_once.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - strategies/*
  - config/*
  - dashboard/*
expected_tests:
  - pytest focused readiness/notrade/candidate-flow suites
  - pytest candidate/trade-builder suite
  - full pytest suite
acceptance_proof:
  - current ready indicators no longer surface as stale INDICATORS_MISSING
  - strategy gate reaches post-warmup stage when indicator values are present and fresh
  - evidence artifacts stay read-only and non-action
```

### Purpose

Fix a false upstream blocker classification proven by live evidence from PR #458: current-cycle indicator readiness was green, but the pre-strategy decision path still surfaced `INDICATORS_MISSING`, preventing strategy generation before `trade_builder` ran.

## Files Changed

- `/Users/madhuram/tradebot/core/decision_dag.py`
  - Make the warmup/indicator node trust explicit current per-indicator readiness when it exists, instead of re-blocking on a coarse overloaded `indicators_ok` flag.
- `/Users/madhuram/tradebot/core/runtime_notrade_reason_truth.py`
  - Reconcile stale `INDICATORS_MISSING` blocker evidence against current readiness so the no-trade root-cause label stays truthful.
- `/Users/madhuram/tradebot/core/runtime_candidate_flow_trace.py`
  - Reconcile stale `INDICATORS_MISSING` in the trace blocker summary when current readiness says all symbols are ready.
- `/Users/madhuram/tradebot/tests/test_notrade_reason_truth_evidence.py`
  - Add deterministic proof that stale indicator blockers do not win when readiness is currently true.
- `/Users/madhuram/tradebot/tests/test_candidate_flow_trace_evidence.py`
  - Add deterministic proof that trace evidence drops stale `INDICATORS_MISSING`.
- `/Users/madhuram/tradebot/tests/test_orchestrator_strategy_gate_once.py`
  - Add deterministic proof that strategy gating does not stop at warmup with `INDICATORS_MISSING` when live-ready indicator values are present.

## High-Risk Path Review

High-risk file changed: `/Users/madhuram/tradebot/core/decision_dag.py`.

Review outcome:
- Change is narrowly scoped to the pre-strategy warmup/indicator classification path.
- No broker/order/execution/risk/strategy modules were modified.
- The fix does not weaken the real indicator gate. It only prevents a non-indicator coarse flag from being mislabeled as `INDICATORS_MISSING` when current indicator evidence is explicitly ready.

Residual risk:
- Any decision-path change can alter upstream blocker labels. This change is covered by targeted regressions plus the full test suite, but it still needs live revalidation after merge.

## Scope Guard

### In Scope

- Fix false `INDICATORS_MISSING` classification when current-cycle indicator readiness is already true.
- Keep no-trade and candidate-flow evidence consistent with current readiness.

### Out of Scope

- Broker/order code
- Live safety
- Strategy formulas
- Ranking/scoring
- Phase2 behavior
- Thresholds
- Dashboard/UI

### Boundary Verification

- [x] No broker calls added
- [x] No order actions added
- [x] No strategy formulas changed
- [x] No Phase2 logic changed
- [x] No thresholds changed

## Grill Me Review

### Challenge

- Is this really a stale blocker bug, or is current readiness proving one thing while the runtime gate is correctly proving another?
- Are we accidentally weakening the indicator gate by trusting a secondary artifact over live snapshot facts?

### Findings

- `cycle_blockers` was not persisting across cycles. The bad signal was produced fresh each cycle.
- The actual mismatch was:
  - current readiness evidence recomputed from live indicator values said ready
  - `decision_dag` still treated coarse `snapshot.indicators_ok=False` as `INDICATORS_MISSING`
- That coarse field can be false for non-indicator reasons, so the blocker label was wrong.

### Verdict

PASS — the fix is justified and narrower than changing strategy or broker behavior.

## Hermes Review

### Contract / Architecture Check

- [x] Fix is explicit and reversible
- [x] No hidden fallback added
- [x] Evidence remains observable
- [x] Backward-compat fallback retained when explicit readiness is unavailable

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Runtime fix is surgical
- [x] Evidence writers updated for consistency
- [x] Regression tests prove behavior, not just object shape
- [x] Full suite passes locally

### Verdict

PASS

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched
- No live-order behavior changed
- No gate threshold weakened
- No fake candidates created
- No candidate gate bypass added

Evidence/runtime safety flags preserved:
- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`

## Acceptance Proof

### Root Cause

Current-cycle indicator readiness could be explicitly ready while `decision_dag` still emitted `INDICATORS_MISSING` because it trusted coarse `snapshot.indicators_ok=False` even after explicit indicator-readiness evidence had already proven the current values were present and fresh.

### Exact Fix

- In `/Users/madhuram/tradebot/core/decision_dag.py`, the warmup node now treats explicit current indicator-readiness evidence as authoritative when present. The coarse `snapshot.indicators_ok` fallback is only used when explicit readiness is unavailable.
- In the no-trade truth builder, stale raw `INDICATORS_MISSING` blocker counts are reconciled against current readiness before deriving the no-trade root-cause label.
- In the flow-trace builder, stale `INDICATORS_MISSING` is dropped from the trace blocker summary when all current symbols are ready.

### Commands Run

```bash
PYTHONPATH=. python -m pytest -q tests -k "indicator_readiness or notrade_reason_truth or candidate_flow_trace"
PYTHONPATH=. python -m pytest -q tests/test_orchestrator_strategy_gate_once.py
PYTHONPATH=. python -m pytest -q tests -k "candidate_flow or phase2 or trade_builder or strategy_generation"
PYTHONPATH=. python -m pytest -q tests
python scripts/validate_agent_review_evidence.py
PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file <generated-file>
```

## Runtime Proof Required After Merge

Required next live validation:
- run observation-only live loop during market hours
- inspect:
  - `logs/candidate_flow_trace_latest.json`
  - `logs/notrade_reason_truth_latest.json`
  - `.runtime/live_indicator_readiness_latest.json`
- confirm:
  - the trace blocker summary no longer contains stale `INDICATORS_MISSING` when readiness is green
  - `first_zero_stage` moves from false indicator blocking to the true upstream stage

## What This PR Does Not Prove

- Does not prove strategy generation will emit non-zero candidates
- Does not prove Phase2 ranking quality
- Does not change cross-asset, feed, regime, or strategy thresholds
- Does not authorize any live trading action

## Human Approval

Required before merge:
- confirm the blocker reclassification is correct
- confirm the fix does not hide real indicator failures
- confirm post-merge live validation is reviewed by a human

## Evidence (CE-10 Contract Fields)

- mode: LIVE_AUDIT
- candidate_id: stale_indicator_blocker_before_strategy_generation
- decision: FALSE_INDICATORS_MISSING_RECLASSIFIED
- reason: Current-cycle indicator readiness is authoritative when explicit ready evidence exists
- timestamp: 2026-06-02
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/fix-stale-indicator-blocker-before-strategy-generation.md
