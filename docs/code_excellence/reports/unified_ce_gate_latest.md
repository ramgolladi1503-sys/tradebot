# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `29`
- total_findings: `42`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `12` | `0` |  |
| `cerberus` | `PASS` | `0` | `29` | `0` |  |
| `evidence` | `PASS` | `0` | `1` | `0` |  |

## Changed Paths

- `core/opportunity_scoring.py`
- `core/orchestrator.py`
- `core/strategy_parameter_profiles.py`
- `docs/agent_reviews/pr_630_agent_review.md`
- `docs/audits/strategy_contract_and_edge_readiness_audit.md`
- `strategies/movement/_utils.py`
- `strategies/movement/compression_breakout.py`
- `strategies/movement/event_volatility_expansion.py`
- `strategies/movement/exhaustion_reversal.py`
- `strategies/movement/failed_breakout_trap.py`
- `strategies/movement/late_day_momentum.py`
- `strategies/movement/mean_reversion_extension.py`
- `strategies/movement/opening_drive.py`
- `strategies/movement/opening_range_breakout.py`
- `strategies/movement/option_pressure.py`
- `strategies/movement/trend_pullback.py`
- `strategies/movement/vwap_reclaim.py`
- `tests/test_candidate_pool.py`
- `tests/test_fallback_never_executable.py`
- `tests/test_jit_quote_revalidation.py`
- `tests/test_opportunity_scoring.py`
- `tests/test_opportunity_scoring_regime_profile_opt_in.py`
- `tests/test_profile_score_delta_evidence.py`
- `tests/test_ranked_pipeline_contract_snapshots.py`
- `tests/test_ranking_orchestrator.py`
- `tests/test_strategy_generators_lineage.py`
- `tests/test_strategy_parameter_profiles.py`
- `tests/test_strategy_promotion_state.py`
- `tests/test_strategy_regime_integration.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/test_candidate_pool.py` | `PASS` | `test_reality_accepted` |
| `tests/test_fallback_never_executable.py` | `PASS` | `test_reality_accepted` |
| `tests/test_jit_quote_revalidation.py` | `PASS` | `test_reality_accepted` |
| `tests/test_opportunity_scoring.py` | `PASS` | `test_reality_accepted` |
| `tests/test_opportunity_scoring_regime_profile_opt_in.py` | `PASS` | `test_reality_accepted` |
| `tests/test_profile_score_delta_evidence.py` | `PASS` | `test_reality_accepted` |
| `tests/test_ranked_pipeline_contract_snapshots.py` | `PASS` | `test_reality_accepted` |
| `tests/test_ranking_orchestrator.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_generators_lineage.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_parameter_profiles.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_promotion_state.py` | `PASS` | `test_reality_accepted` |
| `tests/test_strategy_regime_integration.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/opportunity_scoring.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/strategy_parameter_profiles.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_630_agent_review.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/audits/strategy_contract_and_edge_readiness_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/_utils.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/compression_breakout.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/event_volatility_expansion.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/exhaustion_reversal.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/failed_breakout_trap.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/late_day_momentum.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/mean_reversion_extension.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/opening_drive.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/opening_range_breakout.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/option_pressure.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/trend_pullback.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/movement/vwap_reclaim.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_pool.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_fallback_never_executable.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_jit_quote_revalidation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_opportunity_scoring.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_opportunity_scoring_regime_profile_opt_in.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_profile_score_delta_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_ranked_pipeline_contract_snapshots.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_ranking_orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_generators_lineage.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_parameter_profiles.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_promotion_state.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_strategy_regime_integration.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/pr_630_agent_review.md` | `PASS` | `evidence_contract_satisfied` |
