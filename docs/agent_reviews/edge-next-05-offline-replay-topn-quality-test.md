# Agent Work Contract
mode: REVIEW
candidate_id: EDGE-NEXT-05
decision: APPROVE
reason: Offline Top-N replay quality now measures score separation after cost, remains deterministic, and degrades readiness conservatively without weakening fallback, stale-feed, Phase 2, or other safety gates.
timestamp: 2026-06-08T12:00:00+05:30
is_order_action: false
broker_api_called: false
source: Codex (GPT-5.2)
- source_agent: Codex (GPT-5.2)
- action: GENERATE_PATCH
- title: EDGE-NEXT-05 — Offline Replay Top-N Quality Test
- scope: Add a deterministic offline Top-N replay quality helper, CLI, and conservative readiness wiring so score separation can be evaluated after cost without live validation.
- requested_paths:
  - core/expectancy/topn_replay_quality.py
  - scripts/run_topn_replay_quality.py
  - core/expectancy/edge_readiness_report.py
  - scripts/write_edge_readiness_report.py
  - tests/test_topn_replay_quality.py
  - tests/test_edge_readiness_report.py
  - core/expectancy/__init__.py
- allowed_paths:
  - core/expectancy/topn_replay_quality.py
  - scripts/run_topn_replay_quality.py
  - core/expectancy/edge_readiness_report.py
  - scripts/write_edge_readiness_report.py
  - tests/test_topn_replay_quality.py
  - tests/test_edge_readiness_report.py
  - core/expectancy/__init__.py
  - docs/agent_reviews/edge-next-05-offline-replay-topn-quality-test.md
- forbidden_paths:
  - broker/*
  - order/*
  - dashboard/*
  - strategies/*
  - core/feed/*
  - runtime/live*
  - logs/*
- expected_tests:
  - PYTHONPATH=. pytest -q tests/test_topn_replay_quality.py tests/test_edge_readiness_report.py -vv
  - PYTHONPATH=. pytest -q tests/test_top_opportunity_selector.py tests/test_edge_ranking.py tests/test_strategy_baseline_comparison.py -vv
  - PYTHONPATH=. pytest -q tests/test_candidate_outcome_tracker.py tests/test_candidate_journal.py tests/test_cost_slippage_model.py -vv
  - python scripts/validate_agent_review_evidence.py --base-ref origin/main
  - git diff --check
  - PYTHONPATH=. python scripts/run_unified_ce_gates.py --changed-paths-file /tmp/edge_next_05_changed_paths.txt
- acceptance_proof: Top-1 vs Top-5 and Top-3 vs Top-10 after-cost comparisons are explicit and deterministic, gross-positive but after-cost-negative setups do not pass, fallback and blocked candidates are excluded from executable replay-quality stats, and readiness downgrades conservatively when Top-N replay quality underperforms without overriding hard safety gates.

## Scope Guard
- This PR is offline-only.
- It does not call brokers or enable live execution.
- It does not rewrite strategy logic or ranking formulas.
- It does not auto-discover runtime artifacts by default.
- It fails closed when inputs are missing.

## Grill Me Review
- The current weakness was score separation proof, not a claim of live alpha.
- The new helper measures after-cost separation among ranked candidates instead of assuming the top of the list is automatically strong.
- Missing or thin samples remain conservative instead of being stretched into proof.

## Hermes Review
- Added a pure Top-N replay quality helper and CLI.
- Wired the verdict into edge readiness as a conservative readiness signal.
- Kept selector and expectancy layers unchanged except for adding the evidence path.

## GSD Review
- Added deterministic tests for outperformance, matches, underperformance, insufficient sample, regime handling, fallback exclusion, and CLI/report generation.
- Added a readiness path that can downgrade conservatively when Top-N replay quality is weak.
- No runtime trading behavior is enabled by this report.

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
- `tests/test_topn_replay_quality.py` covers Top-1 vs Top-5, Top-3 vs Top-10, naive baseline comparison, insufficient sample, regime separation, fallback exclusion, and deterministic output.
- `tests/test_edge_readiness_report.py` proves the Top-N signal can downgrade readiness conservatively without overblocking healthy evidence.
- The report remains read-only and does not enable live trading.

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
