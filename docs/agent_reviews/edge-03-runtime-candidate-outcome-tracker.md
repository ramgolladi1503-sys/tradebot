mode: REVIEW
candidate_id: PR-EDGE-03-RUNTIME-CANDIDATE-OUTCOME-TRACKER
decision: add_runtime_candidate_outcome_tracker
reason: Add read-only candidate outcome tracking on top of journaled runtime candidates using the existing CandidateOutcomeTruth contract and deterministic observations.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge-03-runtime-candidate-outcome-tracker.md

# PR-EDGE-03 — Outcome Tracker for Runtime Candidates

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (read-only runtime candidate outcome tracker + deterministic tests + evidence doc)
title: Outcome Tracker for Runtime Candidates
scope: build candidate outcome records from journaled runtime candidates and price observations without changing execution behavior
requested_paths:
  - core/candidate_outcome_tracker.py
  - tests/test_candidate_outcome_tracker.py
  - tests/test_candidate_outcome_truth.py
  - docs/agent_reviews/edge-03-runtime-candidate-outcome-tracker.md
allowed_paths:
  - core/candidate_outcome_tracker.py
  - tests/test_candidate_outcome_tracker.py
  - tests/test_candidate_outcome_truth.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/risk*
  - strategies/*
  - dashboard/*
  - runtime/*
  - logs/*
  - core/kite_depth_ws.py
  - core/runtime_execution_truth.py
  - core/review_queue.py
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_tracker.py -vv
  - PYTHONPATH=. pytest -q tests/test_candidate_journal.py tests/test_review_queue_decision_engine.py -vv
  - python scripts/validate_agent_review_evidence.py
  - git diff --check
acceptance_proof:
  - runtime candidate outcomes are generated read-only from journaled rows plus deterministic observations
  - fallback and non-executable candidates remain NOT_EXECUTABLE rather than being misrepresented as executable outcomes
  - the tracker can write JSONL without changing trading decisions or requiring broker/API access
```

## Scope Guard

- This PR is read-only analytics/evidence plumbing.
- It must not change strategy logic, ranking/scoring, Phase 2 behavior, broker/order flows, websocket/feed lifecycle behavior, or dashboard runtime behavior.
- It must not introduce kill/keep gates, outcome aggregation, expectancy aggregation, or setup fingerprints.

## Grill Me Review

- The tracker must fail closed when candidate rows are non-executable or fallback-derived.
- Price observation handling must be deterministic and bounded by explicit windows.
- Write failures must be non-fatal and must not alter the candidate or outcome truth.

## Hermes Review

- The tracker should use the existing `CandidateOutcomeTruth` contract rather than inventing a new truth model.
- The safest boundary is a pure builder plus a write helper that can later be wired in minimally or left off by default.

## GSD Review

- Keep the implementation narrow: a single module, deterministic tests, and no runtime behavior change.
- Preserve explicit read-only flags in all generated outcome rows and reports.

## QA / Safety Review

- `read_only=true`
- `append=true` only for the outcome JSONL rows
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `live_order_action=false`
- `broker_order_action=false`
- `runtime_wired=false` unless an explicit future wiring path is approved

## Acceptance Proof

- Executable candidates produce outcome rows for target/stop/timeout evaluation.
- Non-executable candidates produce `NOT_EXECUTABLE`.
- Fallback candidates never count as executable outcomes.
- Missing observations fail closed to `NO_OBSERVATIONS`.
- Timeout evaluation uses the latest observation before the window end.
- Cost-adjusted R multiple is derived as `gross_r - estimated_cost_r`.

## Runtime Proof Required After Merge

- Run the tracker against journaled runtime candidates and deterministic observations and confirm JSONL output is written under the runtime candidates directory.
- Confirm the tracker can be used offline without broker/API access or live order permissions.

## What This PR Does Not Prove

- It does not prove trading edge.
- It does not change execution eligibility, ranking, strategy, or broker behavior.
- It does not add expectancy aggregation or any outcome-based promotion logic.

## Human Approval

- This PR is safety-sensitive and requires human review before merge.

## Files Changed

- `core/candidate_outcome_tracker.py`
- `tests/test_candidate_outcome_tracker.py`
- `tests/test_candidate_outcome_truth.py`
- `docs/agent_reviews/edge-03-runtime-candidate-outcome-tracker.md`

## Validation

- `PYTHONPATH=. pytest -q tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_tracker.py -vv`
- `PYTHONPATH=. pytest -q tests/test_candidate_journal.py tests/test_review_queue_decision_engine.py -vv`
- `python scripts/validate_agent_review_evidence.py`
- `git diff --check`

## Future Work

- PR-EDGE-04: Cost and Slippage Truth Model.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
