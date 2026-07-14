# Agent Work Contract
mode: REVIEW
candidate_id: EDGE-NEXT-04
decision: APPROVE
reason: Readiness-aware baseline comparison now influences ranking and readiness conservatively without weakening fallback, stale-feed, or Phase 2 safety gates.
timestamp: 2026-06-07T23:00:00+05:30
is_order_action: false
broker_api_called: false
source: Codex (GPT-5.2)
- source_agent: Codex (GPT-5.2)
- action: GENERATE_PATCH
- title: EDGE-NEXT-04 — Strategy Edge Baseline Comparison
- scope: Add deterministic baseline comparison verdicts and feed them into ranking/readiness conservatively so below-baseline or insufficient setup groups can reduce readiness without overriding hard safety gates.
- requested_paths:
  - core/expectancy/strategy_baseline_comparison.py
  - core/expectancy/strategy_regime_expectancy.py
  - core/expectancy/edge_ranking.py
  - core/expectancy/edge_readiness_report.py
  - core/no_trade_engine.py
  - tests/test_strategy_baseline_comparison.py
  - tests/test_strategy_regime_expectancy.py
  - tests/test_edge_readiness_report.py
  - tests/test_edge_ranking.py
  - tests/test_no_trade_engine.py
- allowed_paths:
  - core/expectancy/strategy_baseline_comparison.py
  - core/expectancy/strategy_regime_expectancy.py
  - core/expectancy/edge_ranking.py
  - core/expectancy/edge_readiness_report.py
  - core/no_trade_engine.py
  - tests/test_strategy_baseline_comparison.py
  - tests/test_strategy_regime_expectancy.py
  - tests/test_edge_readiness_report.py
  - tests/test_edge_ranking.py
  - tests/test_no_trade_engine.py
  - docs/agent_reviews/edge-next-04-strategy-baseline-comparison.md
- forbidden_paths:
  - broker/*
  - order/*
  - dashboard/*
  - strategies/*
  - core/feed/*
  - runtime/live*
  - logs/*
- expected_tests:
  - PYTHONPATH=. pytest -q tests/test_strategy_baseline_comparison.py tests/test_strategy_regime_expectancy.py tests/test_edge_readiness_report.py tests/test_edge_ranking.py tests/test_no_trade_engine.py -vv
  - PYTHONPATH=. pytest -q tests/test_review_queue_decision_engine.py tests/test_runtime_execution_truth_evidence.py tests/test_candidate_journal.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge_next_04_changed_paths.txt
- acceptance_proof: OUTPERFORMS gets a capped boost, MATCHES stays neutral, INSUFFICIENT_SAMPLE stays conservative, UNDERPERFORMS is penalized, and readiness degrades to PAPER_ONLY/NO_TRADE when the mature pool is below baseline or insufficient without ever overriding fallback, stale-feed, Phase 2, or other safety gates.

## Scope Guard
- This PR changes ranking and readiness only through explicit baseline comparison.
- It does not touch broker, order, live execution, or strategy generation behavior.
- It does not weaken fallback, freshness, Phase 2, spread/liquidity, or other safety gates.

## Grill Me Review
- The key risk is overreacting to weak or missing baselines and turning a conservative signal into a hard block.
- The implementation avoids that by treating insufficient baseline evidence as conservative, not as executable proof, and by keeping all hard safety gates dominant.

## Hermes Review
- Baseline comparison now has deterministic verdicts and explicit penalty/boost values.
- Ranking receives only small controlled adjustments, while readiness can degrade conservatively when the mature pool is below baseline.
- The report chain remains read-only and auditable.

## GSD Review
- Added a pure baseline comparison helper, wired its verdicts into edge ranking, and surfaced baseline summaries in expectancy/readiness reports.
- Pool-level weakness can now reduce readiness without allowing fallback or stale candidates to become executable.
- Tests prove boost, penalty, neutrality, insufficient baseline handling, and readiness degradation.

## QA / Safety Review
- Verified that fallback, stale-feed, non-executable, and Phase 2 safety gates still dominate all baseline adjustments.
- Verified that missing or insufficient baseline data does not create fake confidence.
- Verified deterministic outputs and no broker/order imports in the new helper and report path.

## Acceptance Proof
- `tests/test_strategy_baseline_comparison.py` covers baseline verdicts, boost/penalty caps, fallback-to-eligible lookup, and deterministic output.
- `tests/test_edge_ranking.py` proves baseline boost/penalty affects ranking conservatively without overriding safety.
- `tests/test_strategy_regime_expectancy.py` and `tests/test_edge_readiness_report.py` prove baseline summary propagation and readiness degradation.
- `tests/test_no_trade_engine.py` proves pool-level baseline weakness can contribute to no-trade readiness.

## Runtime Proof Required After Merge
- Re-run the same deterministic ranking/readiness regressions after the next branch sync.
- Do not use live market validation for this gate.

## What This PR Does Not Prove
- It does not prove durable market alpha.
- It does not replace forward testing or out-of-sample validation.
- It does not enable live trading.

## Human Approval
- Required before any broader ranking, strategy, or live-execution changes beyond this scope.


## Agent Work Contract

N/A

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
