# Candidate Executability Evidence Pack

mode: REVIEW
candidate_id: PR-CANDIDATE-EXECUTABILITY-EVIDENCE-PACK
decision: add_read_only_candidate_executability_evidence_pack
reason: Create a deterministic offline-only evidence pack that explains why generated candidates do or do not become executable without changing runtime behavior.
timestamp: 2026-06-05T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/candidate-executability-evidence-pack.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (read-only evidence pack + deterministic parser + offline CLI + tests + docs)
title: Candidate Executability Evidence Pack
scope: add a pure read-only evidence pack that explains candidate supply, top candidate status, phase2 drops, trade-builder rejects, feed/runtime blockers, and quote truth split-brain rejects without changing live behavior
requested_paths:
  - core/candidate_executability_evidence.py
  - scripts/write_candidate_executability_evidence.py
  - tests/test_candidate_executability_evidence.py
  - tests/fixtures/candidate_executability/pr489_live_excerpt.log
  - tests/fixtures/candidate_executability/clean_executable_counterexample.log
  - docs/candidate_executability_evidence_pack.md
  - docs/agent_reviews/candidate-executability-evidence-pack.md
allowed_paths:
  - core/candidate_executability_evidence.py
  - scripts/write_candidate_executability_evidence.py
  - tests/test_candidate_executability_evidence.py
  - tests/fixtures/candidate_executability/*
  - docs/candidate_executability_evidence_pack.md
  - docs/agent_reviews/*
forbidden_paths:
  - core/orchestrator.py
  - core/engine_phase2_adapter.py
  - core/runtime_execution_truth.py
  - core/feed_truth_contract.py
  - core/kite_depth_ws.py
  - strategies/*
  - dashboard/*
  - core/broker*
  - core/order*
  - config/*
  - runtime/*
  - logs/*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_candidate_executability_evidence.py -vv
  - PYTHONPATH=. pytest -q tests/test_candidate_executability_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_runtime_states.py tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py tests/test_trade_builder_real_candidate_supply.py tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - git diff --name-status origin/main...HEAD
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr490_changed_paths.txt
acceptance_proof:
  - parser summarizes real evidence from committed log fixtures only
  - top candidate status and blockers are preserved explicitly
  - final emit / phase2 / trade-builder / feed/runtime / quote split-brain evidence is read-only and deterministic
  - clean executable evidence is not misclassified as blocked
  - all safety flags remain non-action/read-only
```

## Scope Guard

- This PR is offline-only evidence tooling.
- It must not call broker APIs, place orders, change strategy or ranking behavior, or wire into runtime.
- It must fail closed on malformed or missing evidence.

## Grill Me Review

- The pack must not soften any execution gate.
- The pack must keep blocked and executable evidence distinct.
- The pack must not misclassify clean executable evidence as blocked.

## Hermes Review

- The parser is deterministic and read-only.
- It summarizes committed evidence only.
- It does not wire into runtime or live execution.

## GSD Review

- Changes are limited to one pure core module, one offline CLI, one focused test file, committed fixtures, and docs.
- No production runtime behavior is modified.

## QA / Safety Review

- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`
- `live_order_allowed=false`
- `live_order_action=false`
- `broker_order_action=false`

## Closed-Environment Rule

- The pack reads committed log-style evidence only.
- No Kite session, no websocket connection, and no live market dependency are allowed.

## Changed Files

- `core/candidate_executability_evidence.py`
- `scripts/write_candidate_executability_evidence.py`
- `tests/test_candidate_executability_evidence.py`
- `tests/fixtures/candidate_executability/pr489_live_excerpt.log`
- `tests/fixtures/candidate_executability/clean_executable_counterexample.log`
- `docs/candidate_executability_evidence_pack.md`
- `docs/agent_reviews/candidate-executability-evidence-pack.md`

## Evidence Produced

- candidate supply by symbol
- post-scan survivor counts by symbol
- real/executable/advisory/blocked counts by symbol
- top candidate status and execution truth blockers
- final emit abort reasons
- phase2 drop counts
- trade-builder reject counts
- feed/runtime blockers
- quote truth split-brain examples
- dominant blocker and suggested next PR type

## Tests Run

- `PYTHONPATH=. pytest -q tests/test_candidate_executability_evidence.py -vv`
- `PYTHONPATH=. pytest -q tests/test_candidate_executability_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_runtime_states.py tests/test_kite_depth_restart.py tests/test_kite_depth_ws_stability.py tests/test_trade_builder_real_candidate_supply.py tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py -vv`

## Validation Commands

- `python scripts/validate_agent_review_evidence.py --base-ref origin/main`
- `git diff --check`
- `git diff --name-status origin/main...HEAD`
- `PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/pr490_changed_paths.txt`

## Acceptance Proof

- Candidate supply is summarized by symbol from committed evidence lines.
- A blocked top candidate with executable-looking inner fields remains non-reportable.
- Final emit blockers, phase2 drops, trade-builder rejects, feed/runtime blockers, and quote split-brain evidence are preserved deterministically.
- Clean executable evidence remains executable and is not reclassified as blocked.
- All reports remain read-only.

## Runtime Proof Required After Merge

- None. This PR is intentionally offline-only.
- Reviewers can regenerate the report from the committed fixtures and compare the JSON/Markdown outputs.

## What This PR Does Not Prove

- It does not prove trading edge, profitability, or live readiness.
- It does not change runtime behavior.
- It does not authorize any order action.

## Expected Changed Files

- `core/candidate_executability_evidence.py`
- `scripts/write_candidate_executability_evidence.py`
- `tests/test_candidate_executability_evidence.py`
- `tests/fixtures/candidate_executability/pr489_live_excerpt.log`
- `tests/fixtures/candidate_executability/clean_executable_counterexample.log`
- `docs/candidate_executability_evidence_pack.md`
- `docs/agent_reviews/candidate-executability-evidence-pack.md`

## Forbidden Scope Not Touched

- No broker/order changes
- No live orders
- No strategy changes
- No ranking changes
- No Phase2 behavior changes
- No dashboard/UI changes
- No websocket changes
- No FeedTruth contract changes
- No runtime behavior changes
- No stale/latency/risk gate relaxation
- No execution threshold changes
- No dependency on live market or Kite session

## Risk Assessment

- Low runtime risk because there is no runtime wiring.
- Main risk is parser drift if future evidence payloads rename fields; this is contained by tests and deterministic fixture parsing.

## Rollback Plan

- Remove the new evidence module, CLI, fixtures, tests, and docs.
- No runtime rollback is required because no runtime path is modified.

## Why This Does Not Prove Trading Edge

- This pack only explains evidence and blockers.
- It does not optimize or validate profitability.
- It does not change execution outcomes.

## Future Work Explicitly Out of Scope

- Wiring this parser into runtime
- Changing strategy or ranking behavior
- Changing Phase2 behavior
- Changing websocket recovery or broker behavior
- Relaxing stale-feed, latency, or execution-truth gates

## Human Approval

This is safe to review as read-only evidence tooling only.


## High-Risk Path Review

N/A
