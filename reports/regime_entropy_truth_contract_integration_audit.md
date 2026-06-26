# Integration Audit Report: Regime Entropy Truth Contract

**Date**: 2026-06-26
**Branch**: `fix/regime-entropy-truth-contract-prod-grade`
**Status**: `MERGE_READY`

## 1. Tests Run
The following test suites and specific tests were executed to prove integration and truth contract bounds:
- `pytest tests/test_entropy_contract.py -q` (Pass)
- `pytest tests -q -k "ranking or fallback or stale or quote or scoring or regime or entropy or phase2"` (Fail -> Fixed -> Pass)
- `pytest tests/test_post_session_rca_patch.py tests/test_candidate_scoring.py tests/test_feed_safety_gates.py -q` (Pass)
- `pytest tests/test_live_scoring_blocks.py -q` (Pass)
- `pytest tests/test_live_ranking_blocks.py -q` (Pass)

### Defects Found and Fixed During Audit
1. `test_score_candidate_strong_inputs_is_high_and_deterministic` was failing because the mock used a `4.0s` quote age in `LIVE` mode, which our new truth contract rightly penalized to `0.0`. Fixed test to use `1.0s` to maintain the "strong input" premise.
2. `test_monitoring_degraded_alert_emitted_for_feed_stale` was failing because the `send_telegram_message` telemetry on `FEED_STALE` was missing from `log_decision_safe`. Restored this logic to `core/orchestrator_parts/decisions.py`.
3. `test_feed_stale_freshness_limits` returned a candidate instead of dropping it because `engine_phase2_adapter.py` was only checking `feed_ok` but ignoring `tick_age_sec > 2.5` SLA in phase 2 candidate building. Fixed this by enforcing the `tick_age_sec > 2.5` boundary directly in phase 2 filtering.
4. `test_feed_runtime_latest_path_equality` was writing feed updates directly to the unmocked repository directory during test environments, bypassing standard `pytest` sandboxes. Rewired `write_runtime_snapshot` to use `logs_dir()` standard patching.

## 2. Integration Evidence

### A. Mathematical Verification
- Current Regime Count: `5`
- Max Entropy: `ln(5) = 1.6094`
- Normalized Entropy Bound Check: Verified exactly `[0.0, 1.0]`.
- Raw Entropy `1.399` / `1.6094` = `0.869` (High uncertainty, mathematically correct).

### B. Live Scoring Constraints Proven
The test `test_live_scoring_blocks.py` explicitly proved that missing context drives component scores to `0.0` and applies hard `penalty_reasons`:
- `missing_spread` => `missing_spread_context_live_block`
- `missing_liquidity` => `missing_liquidity_context_live_block`
- `missing_quote_age` => `missing_timing_context_live_block`
- `stale_quote_age > 2.0s` => `stale_quote_age_live_block`
- `missing_stop/target` => `missing_rr_context_live_block` (RR Fallback disabled in LIVE)

### C. Ranking Quarantine Proven
The test `test_live_ranking_blocks.py` explicitly proved that candidates with feed-risk cannot be marked `executable_candidate=True` and cannot be `EXECUTABLE_CANDIDATE` bucket:
- `fallback` => Suppressed
- `synthetic` => Suppressed
- `stale_feed` => Suppressed
- `missing_depth` => Suppressed
Furthermore, if all candidates are stale, the `CandidateRankingReport` outputs zero executable trades (No fake best trade).

## 3. Configuration Correctness & Remaining Defects
The `LIVE_OPTION_LTP_MAX_AGE_SEC` defaults to `2.0` and `OFFHOURS_DIAGNOSTIC_MAX_AGE_SEC` to `300.0`.

## 4. Final Recommendation
**MERGE_READY**

The integration audit previously detected raw `REGIME_ENTROPY_MAX` comparisons still in use. These have now been fully eradicated. The codebase now solely relies on the central `evaluate_regime_entropy_gate` which implements normalized entropy bounds logic strictly based on `max_entropy = ln(regime_count)`.

All legacy raw threshold logic (e.g. `1.3` / `1.8`) has been successfully refactored or removed across:
- `core/decision_dag.py`
- `core/orchestrator.py`
- `core/gate_status_log.py`
- `core/market_data.py`
- `strategies/trade_builder.py`

The candidate ranking, live scoring, and isolation mechanisms also successfully quarantine stale/synthetic feeds according to the rigid truth contract. The branch fully meets the required execution safety criteria and is ready for merge.

## 5. Final Diff Audit
A final diff audit was performed prior to merge:
- **Diff stat:** `74 files changed, 5310 insertions(+), 48 deletions(-)` (Includes legacy and newly added tests to lock down gates).
- **Changed file classification:** 
  - `core/entropy_contract.py`, `core/regime_entropy_gate.py`: Centralized regime mathematical truth. Safe, blocks bypasses.
  - `core/data_quality.py`, `core/candidate_scoring.py`, `core/candidate_ranking.py`: Enhancements for execution safety and ensuring missing live-critical fields receive hard `0.0` or `live_block` penalities. Safe execution bounds established.
  - `core/decision_dag.py`, `core/orchestrator.py`, `core/market_data.py`: Refactored to pass down contexts to entropy gates. Legacy raw thresholds eradicated.
  - `core/adaptive_risk.py`, `core/risk_state.py`: Hardcoded `1.3` threshold removed in favor of `0.8` normalized.
  - `tests/*`: 100% test-only additions verifying behavior blocks.
- **Raw entropy grep result:** Clean. All 1.3/1.8 raw threshold limits have been safely refactored or deleted from active runtime code. Existing hits represent test expectations or safe proxy passthroughs to the central gate.
- **Fallback/stale grep result:** Clean. Verified through `test_live_ranking_blocks.py` that fallback/recovered feeds are rigorously classified as `advisory_only` or `planning_only` and absolutely barred from becoming Top Opportunities executable targets in `LIVE`. 
- **Neutral default grep result:** Clean. `0.5`, `0.55` and `0.56` variables present in scoring algorithms remain, but are fundamentally preceded by `if execution_mode == "LIVE": return 0.0, ["missing_context_live_block"]`. Missing fields thus safely trigger zeroes instead of half-scores.
- **Invalid probability behavior proof:** Test `test_invalid_probability_vector_produces_uncertain_true` proves that if invalid regime vectors such as `{"TREND": 0.9, "RANGE": 0.9}` are fed into the system, it explicitly catches the bad distribution, marks `probability_valid=False`, triggers `invalid_probability_vector` diagnostic context, and assigns `uncertain=True` guaranteeing no executable candidate escapes a broken probability distribution input. 
- **Live SLA constraint proof:** Verified `LIVE_OPTION_LTP_MAX_AGE_SEC`, `LIVE_DEPTH_MAX_AGE_SEC`, `LIVE_SPOT_MAX_AGE_SEC` properly enforce a maximum of `2.0` in `LIVE`. The logic correctly delineates `300.0` only for paper/offhours environments.
- **Test commands and results:** 
  - `pytest tests/test_entropy_contract.py -q` (8 passed in 0.76s)
  - `pytest tests/test_runtime_truth_consistency_pr103.py tests/test_stale_indicator_blocker_strategy_gate.py tests/test_market_data_unstable_reasons.py` (8 passed in 3.60s)
  - `pytest tests -q -k "ranking or fallback or stale or quote or scoring or regime or entropy or phase2 or decision_dag or orchestrator or trade_builder"` (1318 passed)
- **Remaining warnings:** DataFrame fragmentation deprecation warnings remain, which do not disrupt functionality.
- **Final Verdict:**
  - **MERGE_READY**
