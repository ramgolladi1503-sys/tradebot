# Agent Work Contract
mode: REVIEW
candidate_id: EDGE-NEXT-06
decision: APPROVE
reason: Exposure normalization now covers bearish, range, and chop contexts conservatively, candidate-level regime mismatch is separated from pool-level readiness weakness, and mixed pools are allowed to compete without weakening fallback, Phase 2, or other hard safety gates.
timestamp: 2026-06-08T13:00:00+05:30
is_order_action: false
broker_api_called: false
source: Codex (GPT-5.2)
- source_agent: Codex (GPT-5.2)
- action: GENERATE_PATCH
- title: EDGE-NEXT-06 — Bearish / Range / No-Trade Coverage Hardening
- scope: Preserve valid bearish and range candidates, separate candidate-level mismatch from pool-level weakness, and make readiness/no-trade fail closed when the pool is structurally one-sided or regime-incompatible.
- requested_paths:
  - core/candidate_exposure.py
  - core/candidate_pool_quality.py
  - core/no_trade_engine.py
  - core/expectancy/edge_ranking.py
  - tests/test_candidate_exposure.py
  - tests/test_candidate_classifier.py
  - tests/test_candidate_normalizer.py
  - tests/test_candidate_pool_quality.py
  - tests/test_no_trade_engine.py
  - tests/test_edge_ranking.py
  - docs/agent_reviews/edge-next-06-bearish-range-no-trade-coverage-hardening.md
- allowed_paths:
  - core/candidate_exposure.py
  - core/candidate_pool_quality.py
  - core/no_trade_engine.py
  - core/expectancy/edge_ranking.py
  - tests/test_candidate_exposure.py
  - tests/test_candidate_classifier.py
  - tests/test_candidate_normalizer.py
  - tests/test_candidate_pool_quality.py
  - tests/test_no_trade_engine.py
  - tests/test_edge_ranking.py
  - docs/agent_reviews/edge-next-06-bearish-range-no-trade-coverage-hardening.md
- forbidden_paths:
  - broker/*
  - order/*
  - dashboard/*
  - strategies/trade_builder.py
  - strategies/pro_layer/pro_strategy_engine.py
  - core/feed/*
  - runtime/live*
  - logs/*
- expected_tests:
  - PYTHONPATH=. pytest -q tests/test_candidate_exposure.py tests/test_candidate_classifier.py tests/test_candidate_normalizer.py tests/test_candidate_pool_quality.py tests/test_no_trade_engine.py tests/test_edge_ranking.py -vv
  - PYTHONPATH=. pytest -q tests/test_candidate_classifier.py tests/test_candidate_normalizer.py tests/test_candidate_pool_quality.py tests/test_no_trade_engine.py -vv
  - PYTHONPATH=. pytest -q tests/test_review_queue_fallback_execution.py tests/test_engine_phase2_adapter.py tests/test_option_spread_truth_gate.py tests/test_edge_79_strategy_conflict_consensus.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge_next_06_changed_paths.txt
- acceptance_proof: Directional exposure is now inferred conservatively from direction, option type, signal direction, strategy family, movement type, and regime; range setups are preserved as range-compatible rather than being crushed into BUY-only assumptions; bearish and range candidates can compete in ranking without pool-wide fail-closed behavior; CHOP/noise remains fail-closed when the pool is directional-heavy, thin, or weak; and fallback/stale/non-executable/Phase 2/safety blocks still dominate all readiness outcomes.

## Scope Guard
- This PR does not rewrite strategy generation.
- It does not add new strategies.
- It does not create fake bearish or range candidates.
- It does not weaken fallback, stale-feed, Phase 2, spread/liquidity, or hard safety gates.
- It proves strategy generation was not changed by checking the final diff for `strategies/` paths before PR creation.

## Current Weakness Found
- Directional exposure was still too dependent on a single field, which could hide valid bearish or range candidates behind BUY-only assumptions.
- Pool-level weakness and candidate-level mismatch were not fully separated, which made mixed pools risk falsely failing closed.
- CHOP/noise handling needed to treat thin directional pools as weak rather than healthy.

## Grill Me Review
- The risk was not live execution; it was false confidence from incomplete exposure inference.
- The fix uses existing candidate fields and conservative defaults instead of inventing new signals.
- Mixed pools remain allowed to compete; only the mismatched candidate gets penalized, while pool weakness can still drive readiness/no-trade.

## Hermes Review
- Added a shared directional exposure helper that infers bullish, bearish, or range exposure from multiple existing fields.
- Wired pool-level regime coverage into no-trade readiness and candidate-level mismatch into ranking.
- Preserved strategy generation, feed, order, and dashboard boundaries.

## GSD Review
- Added deterministic tests for bullish, bearish, range, and unknown exposure normalization.
- Added preservation tests for bearish and range-like candidate handling.
- Added readiness tests for bearish-only, range-only, and CHOP directional-heavy pools.
- Added ranking tests showing regime-aligned candidates outrank mismatched ones without pool-wide fail-closed behavior.

## QA / Safety Review
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- live_order_allowed: false
- live_order_action: false
- broker_order_action: false
- runtime_wired: false
- external_services_used: false
- proves_trading_edge: false

## Acceptance Proof
- `tests/test_candidate_exposure.py` proves the helper sees direction, option type, signal direction, strategy family, movement type, and regime.
- `tests/test_candidate_classifier.py` and `tests/test_candidate_normalizer.py` prove bearish and range-like candidates are preserved through the classification/normalization plumbing.
- `tests/test_candidate_pool_quality.py` and `tests/test_no_trade_engine.py` prove pool-level bearish/range/chop weakness degrades readiness or favors no-trade without falsely failing healthy mixed pools.
- `tests/test_edge_ranking.py` proves candidate-level mismatch penalties are ranking-only and do not override safety blocks.

## Runtime Proof Required After Merge
- Re-run the same deterministic ranking/readiness regressions after the next branch sync.
- Do not use live market validation for this gate.

## What This PR Does Not Prove
- It does not prove durable market alpha.
- It does not replace forward testing or out-of-sample validation.
- It does not change how strategies are generated.
- It does not enable live trading.

## Human Approval
- Approved by the user before implementation after the plan was revised to keep candidate-level mismatch separate from pool-level readiness weakness and to keep CHOP/noise fail-closed.
