# Agent Review Evidence — Candidate Outcome Report Writer

mode: REVIEW
candidate_id: PR-CANDIDATE-OUTCOME-REPORT-WRITER
decision: add_offline_candidate_outcome_report_writer
reason: Add deterministic offline JSON and Markdown report writing for committed Candidate Outcome fixtures without runtime wiring, broker calls, Kite/websocket dependency, or strategy/ranking/Phase2 changes.
timestamp: 2026-06-05T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/candidate-outcome-report-writer.md

Status: DRAFT

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (offline report writer + deterministic tests + docs)
title: Candidate Outcome Report Writer
scope: write deterministic JSON and Markdown reports from committed candidate outcome fixtures using the existing fixture loader and outcome truth contract, with no runtime wiring
requested_paths:
  - core/candidate_outcome_report_writer.py
  - scripts/write_candidate_outcome_report.py
  - tests/test_candidate_outcome_report_writer.py
  - docs/candidate_outcome_report_writer.md
  - docs/agent_reviews/candidate-outcome-report-writer.md
allowed_paths:
  - core/candidate_outcome_report_writer.py
  - scripts/write_candidate_outcome_report.py
  - tests/test_candidate_outcome_report_writer.py
  - docs/candidate_outcome_report_writer.md
  - docs/agent_reviews/*
forbidden_paths:
  - strategies/*
  - dashboard/*
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/runtime_execution_truth.py
  - core/feed_truth_contract.py
  - core/feed_truth_audit.py
  - core/broker*
  - core/order*
  - config/*
  - runtime/*
  - logs/*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_candidate_outcome_report_writer.py -vv
  - PYTHONPATH=. pytest -q tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - git diff --name-status origin/main...HEAD
acceptance_proof:
  - deterministic JSON and Markdown reports are written offline from committed fixtures
  - report rows preserve read-only/non-action safety flags
  - malformed or missing fixture inputs fail closed
```

## Scope Guard

- Closed/off-market environment only.
- No runtime wiring.
- No broker, order, Kite, websocket, or external service access.
- No strategy, ranking, Phase2, dashboard, or FeedTruth changes.
- No live session writes.

## Closed-Environment / Off-Market Rule

All inputs are committed fixtures. The report writer must not depend on live market data, runtime logs, or any external service.

## Grill Me Review

- The report writer must not become fake progress by hiding mismatches or normalizing away failures.
- The JSON and Markdown outputs must be deterministic for the same fixture set.
- The writer must preserve the read-only contract flags for each evaluated result.

## Hermes Review

- The writer is a pure offline formatting layer on top of the existing fixture loader and Candidate Outcome Truth contract.
- It must fail closed when fixtures are missing or malformed.
- It must not introduce runtime side effects.

## GSD Review

- Minimal surface area: a writer module, a CLI wrapper, a test file, fixtures unchanged, and docs.
- Determinism is enforced by sorted fixture loading and stable serialization.

## QA / Safety Review

- Tests prove the report is deterministic across repeated builds.
- Tests prove JSON and Markdown outputs are written to caller-provided paths only.
- Tests prove per-result and report-level safety flags remain read-only and non-action.

## Acceptance Proof

Run:

```bash
PYTHONPATH=. pytest -q tests/test_candidate_outcome_report_writer.py -vv
PYTHONPATH=. pytest -q tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py -vv
```

Expected:

- JSON report writes deterministically.
- Markdown report writes deterministically.
- Report rows match expected fixture outcomes.
- Report remains read-only and non-action.

## Validation Commands

- `PYTHONPATH=. pytest -q tests/test_candidate_outcome_report_writer.py -vv`
- `PYTHONPATH=. pytest -q tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py -vv`
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `git diff --name-status origin/main...HEAD`

## Expected Changed Files

- `core/candidate_outcome_report_writer.py`
- `scripts/write_candidate_outcome_report.py`
- `tests/test_candidate_outcome_report_writer.py`
- `docs/candidate_outcome_report_writer.md`
- `docs/agent_reviews/candidate-outcome-report-writer.md`

## Forbidden Scope Not Touched

- `strategies/*`
- `dashboard/*`
- `core/kite_depth_ws.py`
- `core/orchestrator.py`
- `core/runtime_execution_truth.py`
- `core/feed_truth_contract.py`
- `core/feed_truth_audit.py`
- `core/broker*`
- `core/order*`
- `config/*`
- `runtime/*`
- `logs/*`

## Risk Assessment

Low risk. The writer is offline-only and deterministic. The main risk is accidental runtime coupling or non-deterministic output, which tests must prevent.

## Rollback Plan

Revert the writer module, CLI, tests, and docs if the report shape or validation expectations need to be reset. No runtime rollback is required.

## Runtime Proof Required After Merge

Future consumer PRs may use the generated reports, but this PR itself does not wire runtime behavior.

## What This PR Does Not Prove

- It does not prove trading edge.
- It does not wire into runtime.
- It does not call broker or Kite APIs.
- It does not change strategy, ranking, or execution behavior.
- It does not change FeedTruth or audit behavior.

## Why This Does Not Prove Trading Edge

The report writer only formats deterministic offline fixture evaluations. It does not measure live-market profitability, execution quality, or strategy edge.

## Future Work Explicitly Out of Scope

- Outcome aggregation
- Strategy-family summaries
- Regime breakdowns
- Cost/slippage models
- Replay-vs-forward comparison

## Human Approval

Proceed only if the branch stays offline-only, the writer remains deterministic, and the evidence gate passes without touching forbidden runtime files.


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
