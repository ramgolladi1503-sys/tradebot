# Agent Work Contract
mode: REVIEW
candidate_id: EDGE-NEXT-03
decision: APPROVE
reason: Candidate pool quality and diversity penalties are a narrow, read-only ranking/readiness guard that improve separation without touching broker, live execution, or strategy logic.
timestamp: 2026-06-07T22:52:00+05:30
is_order_action: false
broker_api_called: false
source: Codex (GPT-5.2)
- source_agent: Codex (GPT-5.2)
- action: GENERATE_PATCH
- title: EDGE-NEXT-03 — Candidate Pool Opportunity Quality and Diversity Gate
- scope: Penalize concentrated, fallback-heavy, duplicate, and thin candidate pools so ranking and readiness reflect real opportunity diversity instead of surviving heuristics.
- requested_paths:
  - core/candidate_pool_quality.py
  - core/expectancy/top_opportunity_selector.py
  - core/no_trade_engine.py
  - tests/test_candidate_pool_quality.py
  - tests/test_top_opportunity_selector.py
  - tests/test_no_trade_engine.py
- allowed_paths:
  - core/candidate_pool_quality.py
  - core/expectancy/top_opportunity_selector.py
  - core/no_trade_engine.py
  - tests/test_candidate_pool_quality.py
  - tests/test_top_opportunity_selector.py
  - tests/test_no_trade_engine.py
  - docs/agent_reviews/edge-next-03-candidate-pool-quality-gate.md
- forbidden_paths:
  - broker/*
  - order/*
  - dashboard/*
  - strategies/*
  - core/feed/*
  - runtime/live*
  - logs/*
- expected_tests:
  - PYTHONPATH=. pytest -q tests/test_candidate_pool_quality.py tests/test_top_opportunity_selector.py tests/test_no_trade_engine.py -vv
  - PYTHONPATH=. pytest -q tests/test_candidate_scoring.py tests/test_edge_ranking.py tests/test_expectancy_gate.py tests/test_review_queue_decision_engine.py tests/test_review_queue_fallback_execution.py tests/test_candidate_normalizer.py tests/test_candidate_classifier.py tests/test_option_spread_truth_gate.py tests/test_edge_76_option_chain_confirmation.py tests/test_engine_phase2_adapter.py tests/test_edge_79_strategy_conflict_consensus.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge_next_03_changed_paths.txt
- acceptance_proof: Diverse candidate pools outrank duplicate or fallback-heavy pools; fallback and stale/blocked candidates remain non-executable; no broker or live execution paths are introduced.

## Scope Guard
- This PR changes candidate-pool readiness and ranking separation only.
- It does not touch broker/order/live execution behavior.
- It does not weaken fallback, feed freshness, or Phase 2 safety gates.

## Grill Me Review
- The main risk is over-penalizing legitimate concentrated pools and hiding good setups.
- The implementation is conservative and only applies explicit penalties when the pool is demonstrably concentrated, fallback-heavy, or thin.
- The change is deterministic and test-backed, not a hidden heuristic shortcut.

## Hermes Review
- Candidate pools now carry a read-only quality and diversity report.
- Top-opportunity ordering is adjusted by explicit pool-quality penalties so duplicates and fallback contamination do not dominate the top ranks.
- No-trade readiness can now fail closed on concentrated pools instead of pretending a poor pool is trade-ready.

## GSD Review
- Added a pure pool-quality analyzer and tied it into top-opportunity ordering plus no-trade readiness.
- Existing fallback and stale-feed blockers remain intact and still prevent executable promotion.
- Tests prove diverse-vs-duplicate separation, fallback contamination handling, and deterministic ordering.

## QA / Safety Review
- Verified fallback-heavy pools are treated as low quality and can trigger no-trade readiness.
- Verified duplicate and same-symbol concentration are penalized before top-N selection dominates.
- Verified that no broker, order, or live execution code paths were added.

## Acceptance Proof
- `tests/test_candidate_pool_quality.py` covers pool quality diversity, fallback-heavy pools, thin weak pools, and deterministic output.
- `tests/test_top_opportunity_selector.py` covers top-N separation, duplicate de-prioritization, and why-ranked/why-not-ranked explainability.
- `tests/test_no_trade_engine.py` remains green with the new pool-concentration gate.

## Runtime Proof Required After Merge
- Re-run the same deterministic ranking and no-trade regressions on the next branch sync.
- Keep validation fixture-driven; do not use live market validation for this gate.

## What This PR Does Not Prove
- It does not prove durable alpha.
- It does not prove market profitability.
- It does not enable live trading.
- It does not replace out-of-sample forward validation.

## Human Approval
- Required before any broader ranking, strategy, or live-execution changes beyond this scope.


## Agent Work Contract

N/A

## High-Risk Path Review

N/A
