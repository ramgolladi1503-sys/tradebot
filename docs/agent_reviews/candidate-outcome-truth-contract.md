# Candidate Outcome Truth Contract

mode: REVIEW
candidate_id: PR-CANDIDATE-OUTCOME-TRUTH-CONTRACT
decision: add_read_only_outcome_truth_contract
reason: Create a deterministic offline-only candidate outcome truth contract from synthetic observations without wiring runtime behavior or touching trade execution paths.
timestamp: 2026-06-05T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/candidate-outcome-truth-contract.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (pure offline contract + deterministic tests + docs)
title: Candidate Outcome Truth Contract
scope: add a pure deterministic outcome truth contract that derives post-signal candidate outcomes from synthetic observations only
requested_paths:
  - core/candidate_outcome_truth.py
  - tests/test_candidate_outcome_truth.py
  - docs/candidate_outcome_truth.md
  - docs/agent_reviews/candidate-outcome-truth-contract.md
allowed_paths:
  - core/candidate_outcome_truth.py
  - tests/test_candidate_outcome_truth.py
  - docs/candidate_outcome_truth.md
  - docs/agent_reviews/*
forbidden_paths:
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/runtime_execution_truth.py
  - core/feed_truth_contract.py
  - core/broker*
  - core/order*
  - strategies/*
  - dashboard/*
  - config/*
  - runtime/*
  - logs/*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_candidate_outcome_truth.py -vv
  - PYTHONPATH=. pytest -q tests/test_candidate_outcome_truth.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - git diff --name-status origin/main...HEAD
acceptance_proof:
  - deterministic offline-only outcome truth contract with no runtime wiring
  - tests prove target/stop/timeout/MFE/MAE/cost-adjusted R and fail-closed handling
  - all safety flags remain non-action/read-only
```

## Scope Guard

- This PR is offline-only and deterministic.
- It must not import broker, websocket, session, or runtime modules.
- It must not change strategy, ranking, Phase2, or any live execution path.

## Grill Me Review

- The contract must fail closed on bad inputs.
- Ambiguous same-bar target/stop hits must not be forced into a win/loss.
- Unsupported directions must not be silently interpreted.

## Hermes Review

- The module is a pure data contract and derivation helper.
- It preserves the offline boundary and keeps behavior deterministic.
- It is intentionally not wired into runtime yet.

## GSD Review

- Changes are limited to one new core module, one focused test file, and docs.
- No existing runtime, feed, or execution behavior is modified.

## QA / Safety Review

- The returned truth object is always read-only.
- `read_only=true`, `append=false`, `is_order_action=false`, `broker_api_called=false`, `live_order_allowed=false`, `live_order_action=false`, and `broker_order_action=false` remain enforced.

## Acceptance Proof

- Target hit before stop returns `TARGET_HIT`.
- Stop hit before target returns `STOP_HIT`.
- Timeout returns `TIMEOUT` and computes MFE/MAE.
- Missing or invalid price data returns `INVALID_INPUT`.
- Non-executable candidates return `NOT_EXECUTABLE`.
- Same-bar ambiguity fails closed.

## Runtime Proof Required After Merge

- None. This PR is intentionally not wired into runtime.
- Validation is offline only.

## What This PR Does Not Prove

- It does not prove trading edge, profitability, or strategy quality.
- It does not change runtime behavior.
- It does not authorize live orders or websocket/broker activity.

## Human Approval

This is safe to review as a pure offline contract change.
