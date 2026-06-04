# Real Candidate Supply Contract

mode: REVIEW
candidate_id: PR-REAL-CANDIDATE-SUPPLY-CONTRACT
decision: add_tradebuilder_real_candidate_supply_contract
reason: Add deterministic offline tests proving TradeBuilder can produce a real ranked candidate from strong clean LIVE-like inputs without broker calls, runtime wiring, Kite/websocket dependency, or Phase2/ranking changes.
timestamp: 2026-06-05T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/real-candidate-supply-contract.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (offline contract tests + docs only)
title: Real Candidate Supply Contract
scope: prove TradeBuilder can supply one real ranked candidate from strong clean LIVE-like inputs without broker/runtime wiring or ranking/Phase2 changes
requested_paths:
  - tests/test_trade_builder_real_candidate_supply.py
  - docs/real_candidate_supply_contract.md
  - docs/agent_reviews/real-candidate-supply-contract.md
allowed_paths:
  - tests/test_trade_builder_real_candidate_supply.py
  - docs/real_candidate_supply_contract.md
  - docs/agent_reviews/*
forbidden_paths:
  - strategies/trade_builder.py
  - core/broker*
  - core/order*
  - core/kite_depth_ws.py
  - core/orchestrator.py
  - core/runtime_execution_truth.py
  - core/feed_truth_contract.py
  - dashboard/*
  - runtime/*
  - logs/*
expected_tests:
  - PYTHONPATH=. pytest -q tests/test_trade_builder_real_candidate_supply.py -vv
  - PYTHONPATH=. pytest -q tests/test_trade_builder_real_candidate_supply.py tests/test_trade_builder.py tests/test_trade_builder_candidate_breadth.py tests/test_trade_builder_soft_vetoes.py tests/test_candidate_outcome_truth.py tests/test_candidate_outcome_fixture_loader.py tests/test_candidate_outcome_report_writer.py tests/test_feed_truth_contract.py tests/test_runtime_execution_truth_evidence.py tests/test_feed_truth_audit.py tests/test_feed_truth_audit_proof_pack.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - git diff --name-status origin/main...HEAD
acceptance_proof:
  - live-like inputs produce a real ranked candidate in the TradeBuilder pool
  - no-signal with fallbacks disabled does not create a ranked candidate
  - missing bid/ask does not reach the real candidate pool
  - no broker or runtime side effects occur
```

## Scope Guard

- This PR is offline-only and deterministic.
- It must not import broker, websocket, runtime, or live order modules for behavior changes.
- It must not change strategy, ranking, Phase2, or any live execution path.

## Grill Me Review

- The contract must not over-claim execution readiness beyond what the builder actually proves.
- The no-signal branch must remain fail-closed when fallbacks are disabled.
- Missing liquidity inputs must not be normalized into a false positive candidate.

## Hermes Review

- The work is a narrow offline contract and review package.
- It keeps the runtime boundary intact.
- It deliberately avoids any wiring that would create live behavior.

## GSD Review

- Changes are limited to one test file and docs.
- No runtime, broker, ranking, or Phase2 code is changed.

## QA / Safety Review

- All evidence is read-only.
- No order action is introduced.
- No broker API is called.
- No live mode is enabled.
- The builder-side assertions stay focused on real candidate provenance and pool membership, not broker execution.

## Acceptance Proof

- Strong clean LIVE-like inputs yield a real ranked candidate.
- No-signal with fallbacks disabled yields no ranked candidate.
- Missing bid/ask yields no real candidate in the pool.
- The test suite proves there are no broker or runtime side effects.

## Runtime Proof Required After Merge

- None. This PR is offline-only.

## What This PR Does Not Prove

- It does not prove trading edge, profitability, or live readiness.
- It does not change runtime behavior.
- It does not authorize live orders or websocket/broker activity.

## Human Approval

This is safe to review as a pure offline contract change.
