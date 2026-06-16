# PR #585 - Candidate Flow Diagnostics

mode: PAPER
candidate_id: pr585-candidate-flow-diagnostics
signal_id: pr585-candidate-flow-diagnostics
strategy_id: candidate_flow_summary
decision: REVIEW_ONLY
reason: add_read_only_candidate_dropoff_summary_to_ranking_pipeline
timestamp: 2026-06-15T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr585-candidate-flow-diagnostics.md

## Agent Work Contract

This PR adds a read-only candidate flow summary to the ranking pipeline metadata so candidate drop-off can be inspected without manually correlating candidate pool, classification, scoring, and ranking reports.

Source contract:

```text
source_agent: Codex (GPT-5)
action: GENERATE_PATCH
title: Add candidate flow diagnostics to ranking pipeline
scope: add a read-only candidate funnel summary and focused tests; do not change strategy, execution, broker, risk, or live behavior
requested_paths:
  - core/candidate_flow_summary.py
  - core/ranking_orchestrator.py
  - tests/test_candidate_flow_summary.py
  - docs/agent_reviews/pr585-candidate-flow-diagnostics.md
allowed_paths:
  - core/candidate_flow_summary.py
  - core/ranking_orchestrator.py
  - tests/test_candidate_flow_summary.py
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
  - tests/test_candidate_flow_summary.py
  - tests/test_candidate_pool_orchestrator.py
  - agent review evidence validator
acceptance_proof:
  - ranking report metadata exposes candidate_flow_summary
  - raw, classified, scored, ranked, and no-trade drop-off counts are preserved
  - dominant blockers and warnings are surfaced without mutating ranking behavior
  - summary remains read_only by contract and does not call brokers or place orders
```

## Scope Guard

In scope:

- Add `CandidateFlowSummary`.
- Add `build_candidate_flow_summary(...)`.
- Attach `candidate_flow_summary` to ranking orchestrator metadata.
- Add focused tests for no-trade suppression visibility and count consistency.

Out of scope:

- No broker calls.
- No order actions.
- No live execution changes.
- No strategy threshold changes.
- No regime classifier logic changes.
- No scoring formula changes.
- No ranking selection behavior changes.
- No dashboard or UI wiring.

Boundary verification:

- [x] No broker code touched
- [x] No order code touched
- [x] No runtime execution wiring changed
- [x] No risk gate weakened
- [x] No strategy formula changed
- [x] No threshold changed

## Grill Me Review

The main risk is cosmetic diagnostics that look authoritative but misstate the funnel. This PR avoids that by only composing counts and blocker/warning labels from reports that already exist in the pipeline.

The second risk is accidental semantic drift in ranking behavior. This PR does not feed the summary back into scoring or ranking. It is metadata only.

The third risk is low-value tests that prove only object shape. The tests assert exact drop-off counts and blocker visibility for the no-trade suppression path.

Verdict: PASS. Useful observability improvement with narrow blast radius.

## Hermes Review

Architecture boundary is acceptable.

Changed files:

- `core/candidate_flow_summary.py`
- `core/ranking_orchestrator.py`
- `tests/test_candidate_flow_summary.py`
- `docs/agent_reviews/pr585-candidate-flow-diagnostics.md`

The new module composes existing report truth instead of introducing new ranking or strategy logic. The orchestrator change is additive metadata wiring only.

No high-risk path review is required because this PR does not touch config, auth, feed/WebSocket, orchestrator main loop, execution, risk, or strategies as defined by the validator's high-risk path list.

Verdict: PASS.

## GSD Review

Delivery stayed scoped.

- One new read-only summary module.
- One additive metadata wiring change.
- One focused test file.
- No unrelated cleanup.

This moves the broader remediation plan forward because later PRs can now explain why candidates vanish before final ranking without re-instrumenting the pipeline.

Verdict: PASS.

## QA / Safety Review

Safety properties preserved:

- `is_order_action=false`
- `broker_api_called=false`
- no broker adapter imports
- no live mode changes
- no execution path mutation

Test proof targets:

- no-trade suppression remains visible in the summary
- component counts remain internally consistent
- ranking report metadata contains the new diagnostic payload

## Acceptance Proof

Commands run:

```bash
python -m pytest -q tests/test_candidate_flow_summary.py tests/test_candidate_pool_orchestrator.py
python scripts/validate_agent_review_evidence.py
```

Observed result before merge:

- focused pytest slice passed locally: `8 passed`
- agent review validator passes once this file is included in the PR

Acceptance expectations:

- PR contains a `docs/agent_reviews/*.md` file with all required sections
- ranking report metadata includes `candidate_flow_summary`
- diagnostics do not alter ranking outcomes

## Runtime Proof Required After Merge

No live runtime proof is required for this PR to establish correctness because the change is read-only metadata composition.

Follow-up runtime proof becomes relevant only when later PRs consume this summary in runtime observability, dashboards, or decision-quality workflows.

## What This PR Does Not Prove

This PR does not prove trading edge.

It does not prove the current regime model is correct.

It does not prove candidate suppression is desirable.

It does not fix ranking quality, strategy quality, or backtest truth.

It only proves the current candidate funnel can be summarized deterministically and exposed for diagnosis.

## Human Approval

Human approval is still required before merge.

Reviewers should confirm the summary is read-only, the tests remain deterministic, and no downstream consumer treats this metadata as new execution truth.
