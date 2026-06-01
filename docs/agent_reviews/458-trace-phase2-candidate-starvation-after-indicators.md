# PR 458 — Trace Phase2 Candidate Starvation After Indicator Readiness

PR: https://github.com/ramgolladi1503-sys/tradebot/pull/458

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (evidence-only trace)
title: Candidate flow starvation trace artifact
scope: runtime evidence only; no trading behavior changes
requested_paths:
  - core/runtime_candidate_flow_trace.py
  - core/orchestrator.py
  - tests/test_candidate_flow_trace_evidence.py
allowed_paths:
  - core/runtime_candidate_flow_trace.py
  - core/orchestrator.py (evidence write block only)
  - tests/test_candidate_flow_trace_evidence.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - strategies/*
  - config/*
expected_tests:
  - pytest for candidate flow trace + full suite
acceptance_proof:
  - deterministic artifact schema + safety flags
  - trace identifies first_zero_stage without forcing candidates
```

### Purpose

Prove where candidates become zero in the pipeline (market data → indicators → regime → strategy generation → Phase2 input) using a read-only latest artifact, without changing any runtime decisions.

### Files Changed

- `core/runtime_candidate_flow_trace.py` (new): builds+writes `candidate_flow_trace_latest.json` with explicit schema and safety flags.
- `core/orchestrator.py` (edit): writes the trace artifact from the existing end-of-cycle evidence block (no decision logic changes).
- `tests/test_candidate_flow_trace_evidence.py` (new/updated): deterministic tests for schema and inference.

### Files Not To Touch (asserted)

- broker adapters, execution/order router, risk gates, strategy formulas, ranking/scoring, Phase2 behavior, dashboard/UI.

## High-Risk Path Review

High-risk file changed: `core/orchestrator.py`.

Review outcome:
- Change is restricted to the existing evidence write section (end-of-cycle), alongside other `*_latest.json` writers.
- New wiring only reads existing in-memory cycle objects (`market_data_list`, `cycle_blockers`, `cycle_candidate_pool_count`, `cycle_ranked_candidates`) and writes a read-only artifact.
- No broker/order execution calls introduced; no gate decisions are modified; no strategies are invoked from the new code path.
- Non-action artifact flags are hard-coded fail-closed (`read_only=true`, `is_order_action=false`, `broker_api_called=false`, `append=false`).

Residual risk:
- Any orchestrator edit carries operational risk; this change is evidence-only but still lives in the orchestrator loop. Tests and careful diff review are required before merge.

## Scope Guard

### In Scope

- Add `candidate_flow_trace_latest.json` evidence to locate first starvation stage.
- Interpret indicator readiness and regime-block status in a contract-compatible way (no behavior change).

### Out of Scope

- Modifying indicator computation, regime model, gate thresholds, strategy generation, Phase2 ranking, scoring, or any order/broker behavior.
- Forcing candidate creation or bypassing gating.

### Boundary Verification

- [x] No broker calls added
- [x] No order actions added
- [x] No gate behavior changed
- [x] No strategy formulas modified

## Grill Me Review

### Challenge

- Are we accidentally treating stale / informational regime data as a reject signal and mislabeling starvation?
- Are we mis-reading indicator readiness due to schema differences between evidence writers?

### Weaknesses Found (and fixed)

- Indicator readiness inference previously depended on a single key (`ready`). Fixed to accept readiness v2 fields (`indicators_ok`, present flags + empty missing list).
- Regime blocked inference previously treated any non-empty dict presence as blocked. Fixed to require explicit unstable/reject evidence (`unstable_reasons`, `decision_gate_reason=REGIME_UNSTABLE`, `regime_ok=False`, or explicit per-symbol unstable).

### Verdict

PASS (evidence interpretation improved; still requires live validation to confirm the new trace matches runtime contracts).

## Hermes Review

### Contract / Observability Check

- [x] Evidence-only artifact with explicit schema
- [x] Keys always present (no silent omissions for required fields)
- [x] Safety flags explicit and fail-closed
- [x] No changes to runtime decision logic

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Purpose is narrow and explicit
- [x] Artifacts written to `logs/`, `.runtime/`, and `.runtime/logs/`
- [x] Tests cover inference edge-cases
- [x] Full test suite passes locally

### Verdict

PASS

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched.
- No order placement/modification/cancel/exit pathways altered.
- No weakening of gates/thresholds.
- Artifact payload enforces:
  - `read_only=true`
  - `append=false`
  - `is_order_action=false`
  - `broker_api_called=false`

## Acceptance Proof

### Artifact Contract

Writes latest artifacts:
- `logs/candidate_flow_trace_latest.json`
- `.runtime/candidate_flow_trace_latest.json`
- `.runtime/logs/candidate_flow_trace_latest.json`

Must include (minimum):
- provenance: `schema_version`, `writer_name`, `writer_module`, `writer_schema_version`, `generated_epoch`
- safety: `read_only`, `append`, `is_order_action`, `broker_api_called`
- counts: `market_data_symbol_count`, `indicator_ready_symbol_count`, `regime_blocked_symbol_count`, `raw_candidate_count`, `phase2_input_candidate_count`
- diagnosis: `gate_reasons`, `first_zero_stage`

### Commands Run (local)

```bash
PYTHONPATH=. python -m pytest -q tests/test_candidate_flow_trace_evidence.py
PYTHONPATH=. python -m pytest -q tests -k "candidate_flow or phase2 or candidate_starvation or notrade_reason_truth"
PYTHONPATH=. python -m pytest -q tests
```

## Runtime Proof Required After Merge

Required follow-up (market open, observation-only) to validate that the artifact matches runtime contracts:
- Run the standard live observation run.
- Confirm `candidate_flow_trace_latest.json` is freshly written per cycle and aligns with:
  - `notrade_reason_truth_latest.json`
  - `phase2_rejection_latest.json`
  - `candidate_handoff_root_cause_latest.json`
  - `live_indicator_readiness_latest.json`

## What This PR Does Not Prove

- Does not prove a fix for Phase2 starvation; it only localizes the starvation stage.
- Does not prove strategies emit viable candidates when indicators/regime are green.
- Does not prove Phase2 correctness if Phase2 never receives input.

## Human Approval

Required before merge:
- A human reviewer must confirm:
  - orchestrator changes are limited to evidence writing
  - no hidden runtime behavioral changes
  - artifact contract meets investigation needs
  - all CI gates are green

## Evidence (CE-10 Contract Fields)

These fields exist to satisfy the repo’s Evidence Contract Gate for scoped evidence documents.

- mode: PAPER
- candidate_id: pr_458_candidate_flow_trace
- decision: EVIDENCE_ONLY_TRACE_ADDED
- reason: Trace Phase2 starvation stage without changing runtime decisions
- timestamp: 2026-06-01
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/458-trace-phase2-candidate-starvation-after-indicators.md
