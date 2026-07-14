# Agent Work Contract
mode: REVIEW
candidate_id: EDGE-NEXT-02
decision: APPROVE
reason: Regime-aware ranking weights are a narrow additive ranking change with explicit deterministic tests and no broker/live/execution wiring.
timestamp: 2026-06-07T22:31:00+05:30
is_order_action: false
broker_api_called: false
source: Codex (GPT-5.2)
- source_agent: Codex (GPT-5.2)
- action: GENERATE_PATCH
- title: EDGE-NEXT-02 — Regime-Aware Ranking Weights
- scope: Make regime a first-class ranking driver so strong regime-aligned candidates separate cleanly from weak, mismatched, and CHOP setups.
- requested_paths:
  - core/candidate_scoring.py
  - core/expectancy/edge_ranking.py
  - tests/test_candidate_scoring.py
  - tests/test_edge_ranking.py
- allowed_paths:
  - core/candidate_scoring.py
  - core/expectancy/edge_ranking.py
  - tests/test_candidate_scoring.py
  - tests/test_edge_ranking.py
  - docs/agent_reviews/edge-next-02-regime-aware-ranking-weights.md
- forbidden_paths:
  - broker/*
  - order/*
  - dashboard/*
  - strategies/*
  - core/feed/*
  - runtime/live*
  - logs/*
- expected_tests:
  - PYTHONPATH=. pytest -q tests/test_candidate_scoring.py tests/test_edge_ranking.py tests/test_expectancy_gate.py tests/test_review_queue_decision_engine.py tests/test_top_opportunity_selector.py tests/test_review_queue_fallback_execution.py tests/test_candidate_normalizer.py tests/test_candidate_classifier.py tests/test_no_trade_engine.py tests/test_option_spread_truth_gate.py tests/test_edge_76_option_chain_confirmation.py tests/test_engine_phase2_adapter.py tests/test_edge_79_strategy_conflict_consensus.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge_next_02_changed_paths.txt
- acceptance_proof: Strong TREND-aligned candidates outrank weak and mismatched setups; CHOP directional candidates are penalized into a clearly low band; fallback, broker, and live-execution safety stay unchanged.

## Scope Guard
- This PR changes scoring and ranking separation only.
- It does not touch broker/order/live execution behavior.
- It does not weaken feed, fallback, or Phase 2 safety gates.

## Grill Me Review
- The main risk is over-penalizing legitimate candidates and flattening all scores.
- The implementation keeps the baseline strong TREND case high while making mismatch and CHOP penalties materially stronger.
- The change is deterministic and test-backed, not heuristic guesswork.

## Hermes Review
- Regime is now a first-class ranking driver through explicit regime archetype detection and regime-specific weight profiles.
- TREND, RANGE, CHOP, EXPIRY, HIGH_VOL, and LOW_VOL now alter score separation instead of only nudging a scalar fit value.
- Crowding penalties continue to suppress duplicate/correlated candidates.

## GSD Review
- Candidate scoring now uses a regime-aware weight profile.
- Edge ranking continues to preserve fallback and stale/feed blocks.
- Tests prove strong vs weak separation, TREND/RANGE ordering, and CHOP suppression.

## QA / Safety Review
- Verified that fallback/recovered candidates remain non-executable.
- Verified that stale/feed-blocked candidates remain non-executable.
- Verified that missing expectancy does not invent confidence.
- Verified that no broker or order paths were introduced.

## Acceptance Proof
- `tests/test_candidate_scoring.py` covers strong, weak, TREND, RANGE, CHOP, EXPIRY, HIGH_VOL, LOW_VOL, and UNKNOWN regime behavior.
- `tests/test_edge_ranking.py` covers duplicate/correlated suppression and regime mismatch ranking.
- Broader safety regressions continue to pass, including fallback and Phase 2 tests.

## Runtime Proof Required After Merge
- Re-run the same ranking and safety tests on the next branch sync.
- Compare top opportunity ordering on historical fixtures only; do not use live market validation.

## What This PR Does Not Prove
- It does not prove durable alpha.
- It does not prove market profitability.
- It does not enable live trading.
- It does not replace out-of-sample forward validation.

## Human Approval
- Required before any broader ranking or strategy changes beyond this scope.


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
