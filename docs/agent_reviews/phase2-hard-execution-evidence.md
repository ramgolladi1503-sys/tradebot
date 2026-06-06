# Phase2 Hard-Execution Evidence

mode: REVIEW
candidate_id: PR-PHASE2-HARD-EXECUTION-EVIDENCE
decision: add_phase2_hard_execution_evidence
reason: Expose deterministic Phase2 evidence so no-input starvation, hard-execution rejection, unclear context, feed-truth blocking, and advisory or fallback rows can be distinguished without changing Phase2 behavior.
timestamp: 2026-06-06T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/phase2-hard-execution-evidence.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (Phase2 evidence-only hard-execution diagnostics + deterministic regression tests + review doc)
title: Phase2 Hard-Execution Evidence
scope: make Phase2 evidence distinguish upstream starvation from hard-execution rejection, missing context, feed-truth blocking, advisory or synthetic rows, and accepted output without changing Phase2 decisions
requested_paths:
  - core/_engine_phase2_adapter_base.py
  - core/engine_phase2_adapter.py
  - core/runtime_phase2_rejection_evidence.py
  - tests/test_engine_phase2_adapter.py
  - tests/test_phase2_rejection_evidence_artifact.py
  - docs/agent_reviews/phase2-hard-execution-evidence.md
allowed_paths:
  - core/_engine_phase2_adapter_base.py
  - core/engine_phase2_adapter.py
  - core/runtime_phase2_rejection_evidence.py
  - tests/test_engine_phase2_adapter.py
  - tests/test_phase2_rejection_evidence_artifact.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/runtime_execution_truth.py
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/broker*
  - core/order*
  - strategies/*
  - dashboard/*
  - runtime/live*
  - logs/*
  - core/candidate_state_contract.py
  - core/candidate_soft_reject.py
  - core/runtime_notrade_reason_truth.py
  - core/runtime_strategy_no_qualified_reasons.py
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_engine_phase2_adapter*.py -vv
  - PYTHONPATH=. pytest -q tests/test_phase2_rejection_evidence_artifact.py -vv
  - PYTHONPATH=. pytest -q tests/test_runtime_execution_truth_evidence.py -vv
  - PYTHONPATH=. pytest -q tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr495_changed_paths.txt
acceptance_proof:
  - no input is explicitly labeled NO_INPUT
  - input dropped is explicitly labeled INPUT_DROPPED
  - accepted path preserves existing candidate output behavior
  - hard execution drops are counted explicitly
  - missing live timing, spread, liquidity, and unknown quote source contexts are counted explicitly
  - feed truth blocked and stale option ltp contexts are counted explicitly
  - advisory or queue only and synthetic or fallback rows are counted explicitly
  - evidence failures do not crash runtime
```

## Scope Guard

- This PR is off-market and evidence-only.
- It must not alter Phase2 scoring, filtering thresholds, ranking, strategy logic, broker calls, order behavior, or dashboard/UI behavior.
- It must fail closed and preserve current Phase2 decisions.

## Grill Me Review

- Evidence should not hide starvation behind generic `No input candidates`.
- Hard-execution drops should not be collapsed into opaque no-input messages.
- Category counts should be stable and deterministic so future audits can reason about them.

## Hermes Review

- The adapter is the right place to attach Phase2 evidence because it already owns the evidence writer boundary.
- The evidence payload should keep existing fields while adding explicit state labels and category counts.
- Feed truth should be read as context, not as a gate change.

## GSD Review

- Changes are limited to the Phase2 adapter/evidence writer plus narrow regression tests.
- The patch does not change which candidates survive or how Phase2 ranks them.
- Evidence failures remain soft and do not crash runtime.

## QA / Safety Review

- `read_only=true`, `append=false`, `is_order_action=false`, and `broker_api_called=false` remain enforced.
- `PHASE2: No input candidates` must remain distinguishable from `hard_execution` rejection.
- Candidates that are advisory, synthetic, fallback, feed blocked, or lacking context must remain blocked exactly as before.

## High-Risk Path Review

- `core/_engine_phase2_adapter_base.py` and `core/engine_phase2_adapter.py` are high-risk candidate filtering paths, so the patch is intentionally evidence-only.
- The patch does not change ranking math, strategy formulas, or Phase2 admission criteria.
- The patch only adds deterministic reason labels and counts for already-existing Phase2 outcomes.

## Evidence

- Pre-merge evidence showed `PHASE2: No valid candidates after filtering raw_count=22 drop_counts={'hard_execution': 22}`.
- Fresh post-merge evidence mostly showed `PHASE2: No input candidates`, which hid whether upstream starvation or hard-execution rejection was the real cause.
- The new evidence payload makes those cases explicit.

## Root Cause

- Phase2 emitted logs that were too coarse to distinguish:
  - zero input candidates,
  - all input rejected,
  - and accepted candidates with some rejected siblings.
- The rejection evidence payload did not yet expose the category counts the live audit needs.

## Fix

- Add explicit Phase2 input state labels.
- Add explicit accepted/rejected counts.
- Add explicit drop categories for hard execution, missing live timing, missing spread, missing liquidity, unknown quote source, feed-truth blocked, stale option LTP, advisory/queue-only, and synthetic/fallback rows.
- Preserve existing Phase2 output behavior and rejection evidence writes.

## Acceptance Proof

- `phase2_input_state=NO_INPUT` is emitted when Phase2 receives no candidates.
- `phase2_input_state=INPUT_DROPPED` is emitted when Phase2 receives candidates but all are rejected.
- `phase2_input_state=ACCEPTED` is emitted when Phase2 receives candidates and retains them.
- `hard_execution` drops are counted explicitly and remain distinguishable from no-input starvation.
- `missing_live_timing_context`, `missing_spread_context`, `missing_liquidity_context`, `unknown_quote_source`, `feed_truth_blocked`, `stale_option_ltp`, `advisory_or_queue_only`, and `synthetic_or_fallback` are counted explicitly.
- Evidence failures do not change Phase2 outputs and do not crash runtime.

## Safety Constraints

- No broker/order changes.
- No live orders.
- No strategy changes.
- No ranking/scoring formula changes.
- No Phase2 threshold/decision changes.
- No dashboard/UI changes.
- No stale-feed gate relaxation.
- No risk gate relaxation.
- No fallback promotion.
- No making blocked candidates executable.
- No broad refactor.

## Tests Run

- `PYTHONPATH=. pytest -q tests/test_phase2_rejection_evidence_artifact.py -vv`
- `PYTHONPATH=. pytest -q tests/test_engine_phase2_adapter*.py tests/test_phase2_rejection_evidence_artifact.py tests/test_feed_runtime_states.py tests/test_feed_truth_contract.py -vv`

## What Was Not Changed

- Strategy candidate generation.
- Ranking and scoring math.
- Phase 2 pass/fail behavior.
- Broker/order paths.
- Dashboard/UI paths.
- FeedTruth contract semantics.
- Execution-truth normalization.
- Stale-option mutation guard behavior.

## Remaining Risks

- Category counts are evidence-only and must stay aligned with the candidate fields Phase2 already emits.
- If upstream row schemas change, category classification may need an update to stay readable.

## Next Market Validation Signals

- `PHASE2: No input candidates`
- `phase2_input_state=NO_INPUT`
- `phase2_input_state=INPUT_DROPPED`
- `PHASE2_FILTER_DROP_SUMMARY`
- `hard_execution`
- `missing_spread_context`
- `missing_liquidity_context`
- `missing_live_timing_context`
- `unknown_quote_source`
- `feed_truth_blocked`
- `stale_option_ltp`
- `advisory_or_queue_only`
- `synthetic_or_fallback`
- `RAW_CANDIDATE_COUNT`
- `POST_REAL_FILTER_COUNT`
- `POST_EXECUTABLE_FILTER_COUNT`
- `TB_RANKED_COUNT_EXECUTABLE`
- `FINAL_EMIT_ABORT`

## Runtime Proof Required After Merge

- Re-run the Phase2 adapter and rejection evidence suites.
- Confirm no-input and input-dropped cases are distinguishable in written evidence.
- Confirm evidence failures do not change Phase2 outputs and do not crash runtime.

## What This PR Does Not Prove

- It does not prove trading edge, profitability, or strategy quality.
- It does not change live order placement or broker behavior.
- It does not alter ranking math or Phase 2 behavior.

## Human Approval

This is safe to review as a narrow Phase2 evidence-only patch.
