mode: REVIEW
candidate_id: PR-EDGE-01-RUNTIME-CANDIDATE-JOURNAL
decision: add_runtime_candidate_journal
reason: Add a durable, read-only candidate journal at the final runtime review-queue boundary so executable, advisory, blocked, and fallback candidates can be replayed later without changing trading decisions.
timestamp: 2026-06-07T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr-edge-01-runtime-candidate-journal.md

# PR-EDGE-01 — Runtime Candidate Journal

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (durable candidate journal + focused wiring + deterministic tests)
title: Runtime Candidate Journal
scope: add an append-only candidate journal at the final runtime candidate/reporting boundary without changing decisioning
requested_paths:
  - core/candidate_journal.py
  - core/review_queue.py
  - tests/test_candidate_journal.py
  - docs/agent_reviews/pr-edge-01-runtime-candidate-journal.md
allowed_paths:
  - core/candidate_journal.py
  - core/review_queue.py
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
  - PYTHONPATH=. pytest -q tests/test_candidate_journal.py -vv
  - PYTHONPATH=. pytest -q tests/test_review_queue_decision_engine.py tests/test_runtime_execution_truth_evidence.py -vv
  - python scripts/validate_agent_review_evidence.py
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr_edge_01_changed_paths.txt
acceptance_proof:
  - every journal row is append-only evidence and preserves read-only safety flags
  - executable, advisory, blocked, and fallback candidates can be journaled without changing outcomes
  - journal failure is non-fatal and does not affect candidate ranking or emit decisions
```

## Scope Guard

- This PR is evidence-only.
- It must not change strategy logic, ranking/scoring formulae, Phase 2 behavior, broker/order flows, websocket/feed lifecycle behavior, or dashboard runtime behavior.
- It must not implement fallback execution kill logic, outcome tracking, expectancy aggregation, or setup fingerprinting.

## Grill Me Review

- The journal must not invent truth when a candidate row is incomplete.
- Fallback must be recorded as evidence only; it must not block or rewrite execution decisions.
- Writing the journal must never crash the candidate/reporting path.

## Hermes Review

- The right wiring point is the existing final review-queue artifact boundary, after candidate fields and final lifecycle truth are already resolved.
- This keeps the patch narrow and prevents new decisioning branches.

## GSD Review

- Keep the patch small: one new journal module, one wiring hook, one focused test file, and one evidence doc.
- Reuse existing runtime path helpers and JSONL writer patterns.

## QA / Safety Review

- `read_only=true`
- `append=true` for the journal rows only
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `live_order_action=false`
- `broker_order_action=false`
- `allowed_for_live_execution=false`
- Journal write failure must be caught and logged, not raised.

## Acceptance Proof

- Executable candidates are journaled with their truth flags preserved.
- Blocked candidates preserve blockers and blocked truth.
- Fallback candidates are marked `fallback_used=true` when the row shows fallback evidence, but lifecycle fields are not changed.
- Queue-only/advisory candidates remain queue-only/advisory in the journal.
- A journal write failure returns safely without altering the candidate row.

## Runtime Proof Required After Merge

- Run the CLI and confirm the journal file is written under the runtime candidates directory.
- Confirm missing journal directories or missing prior logs do not crash the runtime reporting path.

## What This PR Does Not Prove

- It does not prove trading edge or expectancy.
- It does not compute outcome tracking or aggregated expectancy.
- It does not change live execution, ranking, or strategy decisions.
- It does not authorize broker activity or live orders.

## Files Changed
- `core/candidate_journal.py`
- `core/review_queue.py`
- `tests/test_candidate_journal.py`
- `docs/agent_reviews/pr-edge-01-runtime-candidate-journal.md`

## Validation
- `PYTHONPATH=. pytest -q tests/test_candidate_journal.py -vv`
- `PYTHONPATH=. pytest -q tests/test_review_queue_decision_engine.py tests/test_runtime_execution_truth_evidence.py -vv`
- `python scripts/validate_agent_review_evidence.py`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr_edge_01_changed_paths.txt`

## Future Work
- PR-EDGE-02: Hard Fallback Execution Kill Gate.
- PR-EDGE-03: Outcome tracking on top of the journal.
- PR-EDGE-05: Expectancy aggregation over journaled outcomes.


## High-Risk Path Review

N/A

## Human Approval

N/A
