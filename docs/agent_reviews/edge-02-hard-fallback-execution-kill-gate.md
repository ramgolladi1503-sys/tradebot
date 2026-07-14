mode: REVIEW
candidate_id: PR-EDGE-02-HARD-FALLBACK-EXECUTION-KILL-GATE
decision: add_hard_fallback_execution_kill_gate
reason: Fallback, recovered, and synthetic candidate rows must remain advisory/debug only and must never be reportable executable or execution eligible.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-02-hard-fallback-execution-kill-gate.md

# PR-EDGE-02 — Hard Fallback Execution Kill Gate

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (fallback execution kill gate + deterministic tests + evidence doc)
title: Hard Fallback Execution Kill Gate
scope: keep fallback/recovered/synthetic candidate rows advisory/debug only and never executable
requested_paths:
  - core/review_queue.py
  - core/candidate_journal.py
  - tests/test_review_queue_decision_engine.py
  - tests/test_candidate_journal.py
  - docs/agent_reviews/edge-02-hard-fallback-execution-kill-gate.md
allowed_paths:
  - core/review_queue.py
  - core/candidate_journal.py
  - tests/test_review_queue_decision_engine.py
  - tests/test_candidate_journal.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/risk*
  - core/kite_depth_ws.py
  - core/runtime_execution_truth.py
  - core/candidate_outcome_truth.py
  - strategies/*
  - dashboard/*
  - runtime/*
  - logs/*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_candidate_journal.py tests/test_review_queue_decision_engine.py -vv
  - PYTHONPATH=. pytest -q tests/test_runtime_execution_truth_evidence.py -vv
  - python scripts/validate_agent_review_evidence.py
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge_02_changed_paths.txt
acceptance_proof:
  - fallback rows are preserved as advisory/debug evidence only
  - fallback rows never become reportable executable or execution eligible
  - clean executable rows remain executable
  - journal output records fallback_used=true and the non-executable lifecycle when that lifecycle is present
```

## Scope Guard

- This PR is evidence-only and lifecycle-safety only.
- It must not change strategy logic, ranking/scoring formulae, Phase 2 behavior, broker/order flows, websocket/feed lifecycle behavior, or dashboard runtime behavior.
- It must not implement outcome tracking, expectancy aggregation, or any fallback outcome promotion.

## Grill Me Review

- Fallback rows must not leak into executable reporting even if they look clean enough to promote.
- Detection must cover recovered, rest, synthetic, softened, and soft-reject fallback signals consistently.
- The kill gate must fail closed and preserve the specific reason when the row already has one.

## Hermes Review

- The correct control point is the final review-queue lifecycle path, where executable eligibility is already being resolved.
- The journal remains evidence-only; it must reflect the lifecycle rather than invent a new one.

## GSD Review

- Keep the patch small and centralize fallback suppression in a single helper.
- Add deterministic tests for each fallback signal family and for one clean non-fallback executable row.

## QA / Safety Review

- `read_only=true` where applicable
- `append=true` only for the candidate journal evidence row
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `live_order_allowed=false`
- `live_order_action=false`
- `broker_order_action=false`
- The runtime path must never promote a fallback row to EXECUTE.

## Acceptance Proof

- Fallback candidates are always advisory/debug only.
- `reportable_executable=false` for fallback rows.
- `execution_allowed=false` and `eligible_for_execution=false` for fallback rows.
- `selected_for_execution=false`, `tradable=false`, and `is_executable=false` for fallback rows.
- `permission`, `final_action`, `execution_status`, `readiness`, `candidate_status`, and `visibility_bucket` are normalized to non-executable lifecycle values.
- `final_emit_block_reason` preserves any specific reason already present; otherwise it becomes `fallback_not_executable`.

## Runtime Proof Required After Merge

- Run the focused tests and confirm fallback rows cannot be emitted as executable in the review queue.
- Confirm the candidate journal continues to write read-only evidence and records fallback rows without altering the safe lifecycle.

## What This PR Does Not Prove

- It does not prove trading edge.
- It does not change outcome tracking, expectancy, ranking, or strategy decisions.
- It does not authorize broker activity or live orders.

## Human Approval

- This PR is safety-sensitive and requires human review before merge.

## Files Changed

- `core/review_queue.py`
- `core/candidate_journal.py`
- `tests/test_review_queue_decision_engine.py`
- `tests/test_candidate_journal.py`
- `docs/agent_reviews/edge-02-hard-fallback-execution-kill-gate.md`

## Validation

- `PYTHONPATH=. pytest -q tests/test_candidate_journal.py tests/test_review_queue_decision_engine.py -vv`
- `PYTHONPATH=. pytest -q tests/test_runtime_execution_truth_evidence.py -vv`
- `python scripts/validate_agent_review_evidence.py`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge_02_changed_paths.txt`

## Future Work

- PR-EDGE-03: Outcome Tracker for Runtime Candidates.


## High-Risk Path Review

N/A
