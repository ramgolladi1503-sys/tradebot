# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/tradebot`
- config_path: `/Users/madhuram/tradebot/.gsd-forensics.yaml`
- changed_paths: `123`
- total_findings: `85`
- total_blocks: `17`
- exit_code: `1`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `BLOCK` | `1` | `8` | `2` |  |
| `cerberus` | `BLOCK` | `1` | `69` | `7` |  |
| `evidence` | `BLOCK` | `1` | `8` | `8` |  |

## Changed Paths

- `core/candidate_audits/cost_model.py`
- `core/candidate_audits/engine.py`
- `core/candidate_audits/htf_engine.py`
- `core/candidate_audits/htf_strategies.py`
- `core/candidate_audits/mean_reversion.py`
- `core/candidate_audits/models.py`
- `core/candidate_audits/orb_variants.py`
- `core/candidate_audits/range_reversal.py`
- `core/candidate_audits/trend_continuation.py`
- `core/decision_dag.py`
- `core/instruments.py`
- `core/option_token_resolver.py`
- `core/orchestrator.py`
- `docs/agent_reviews/htf_real_paper_validation_review.md`
- `docs/operations/htf_range_expansion_real_paper_runbook.md`
- `docs/research/htf_range_expansion_deepdive_timeline.md`
- `docs/research/htf_range_expansion_strategy_spec.md`
- `docs/research/rejected_strategies_index.md`
- `docs/research/strategy_deepdive_checklist.md`
- `docs/research/strategy_research_index.md`
- `docs/research/strategy_research_playbook.md`
- `docs/research/vol_expansion_universe_report.md`
- `pr_body.txt`
- `runtime/candidate_audits/candidate_failure_root_cause_report.md`
- `runtime/candidate_audits/candidate_survival_report.md`
- `runtime/candidate_audits/candidate_trade_forensics_report.md`
- `runtime/candidate_audits/corrected_candidate_survival_report.md`
- `runtime/candidate_audits/corrected_cost_adjusted_scoreboard.csv`
- `runtime/candidate_audits/corrected_random_baseline_comparison.csv`
- `runtime/candidate_audits/cost_adjusted_scoreboard.csv`
- `runtime/candidate_audits/daemon_safety_audit.md`
- `runtime/candidate_audits/daily_paper_report.md`
- `runtime/candidate_audits/distribution_analysis.csv`
- `runtime/candidate_audits/edge_width_analysis.csv`
- `runtime/candidate_audits/edge_width_report.md`
- `runtime/candidate_audits/execution_reality_log.csv`
- `runtime/candidate_audits/execution_reality_report.md`
- `runtime/candidate_audits/higher_tf_cost_adjusted_scoreboard.csv`
- `runtime/candidate_audits/higher_tf_edge_report.md`
- `runtime/candidate_audits/higher_tf_failure_autopsy.csv`
- `runtime/candidate_audits/higher_tf_regime_matrix.csv`
- `runtime/candidate_audits/higher_tf_strategy_scoreboard.csv`
- `runtime/candidate_audits/holding_time_analysis.csv`
- `runtime/candidate_audits/htf_gate_ablation_matrix.csv`
- `runtime/candidate_audits/htf_proxy_comparison_matrix.csv`
- `runtime/candidate_audits/htf_range_expansion_final_survival_verdict.md`
- `runtime/candidate_audits/htf_range_expansion_stress_test.csv`
- `runtime/candidate_audits/htf_range_expansion_survival_report.md`
- `runtime/candidate_audits/htf_scoreboard_atm_option_proxy.csv`
- `runtime/candidate_audits/htf_scoreboard_futures_proxy.csv`
- `runtime/candidate_audits/htf_scoreboard_itm_option_proxy.csv`
- `runtime/candidate_audits/htf_signal_funnel.csv`
- `runtime/candidate_audits/htf_starvation_report.md`
- `runtime/candidate_audits/leakage_audit_v2.md`
- `runtime/candidate_audits/mfe_mae_distribution.csv`
- `runtime/candidate_audits/monthly_stability_report.csv`
- `runtime/candidate_audits/paper_execution_quality.csv`
- `runtime/candidate_audits/paper_execution_quality_report.md`
- `runtime/candidate_audits/paper_trade_log.csv`
- `runtime/candidate_audits/paper_vs_backtest_comparison.csv`
- `runtime/candidate_audits/paper_vs_backtest_report.md`
- `runtime/candidate_audits/random_baseline_comparison.csv`
- `runtime/candidate_audits/real_option_data_feasibility.md`
- `runtime/candidate_audits/real_paper_signal_log.csv`
- `runtime/candidate_audits/regime_frequency_analysis.csv`
- `runtime/candidate_audits/regime_frequency_report.md`
- `runtime/candidate_audits/regime_mfe_mae_matrix.csv`
- `runtime/candidate_audits/rejection_funnel_summary.csv`
- `runtime/candidate_audits/strategy_autopsy_report.md`
- `runtime/candidate_audits/strategy_exit_lab_matrix.csv`
- `runtime/candidate_audits/strategy_failure_autopsy.csv`
- `runtime/candidate_audits/strategy_holding_time_decay.csv`
- `runtime/candidate_audits/strategy_mfe_mae_matrix.csv`
- `runtime/candidate_audits/strategy_regime_expectancy.csv`
- `runtime/candidate_audits/strategy_regime_failure_matrix.csv`
- `runtime/candidate_audits/strategy_stop_postmortem.csv`
- `runtime/candidate_audits/stress_test_reconciliation.md`
- `runtime/candidate_audits/target_reach_probability.csv`
- `runtime/candidate_audits/true_walk_forward_stability.csv`
- `runtime/candidate_audits/walk_forward_stability.csv`
- `runtime/candidate_audits/weekly_paper_report.md`
- `runtime/evidence/live_hits_20260618/live_hit_review.csv`
- `runtime/evidence/live_hits_20260618/live_hit_review.json`
- `runtime/evidence/live_hits_20260618/live_hit_review.md`
- `runtime/evidence/live_hits_20260618/temp_raw.json`
- `runtime/strategy_deepdives/edge_cluster_analysis.csv`
- `runtime/strategy_deepdives/edge_concentration_report.md`
- `runtime/strategy_deepdives/edge_feature_attribution.csv`
- `runtime/strategy_deepdives/next_candidate_recommendation.md`
- `runtime/strategy_deepdives/orb_edge_attribution_matrix.csv`
- `runtime/strategy_deepdives/orb_final_verdict.md`
- `runtime/strategy_deepdives/orb_frequency_analysis.csv`
- `runtime/strategy_deepdives/orb_incremental_alpha_report.md`
- `runtime/strategy_deepdives/orb_stress_test.csv`
- `runtime/strategy_deepdives/strategy_cost_drag_matrix.csv`
- `runtime/strategy_deepdives/strategy_deepdive_report.md`
- `runtime/strategy_deepdives/strategy_deepdive_scoreboard.csv`
- `runtime/strategy_deepdives/strategy_failure_taxonomy.csv`
- `runtime/strategy_deepdives/strategy_regime_matrix.csv`
- `runtime/strategy_deepdives/updated_strategy_failure_taxonomy.csv`
- `runtime/strategy_deepdives/vol_expansion_failure_matrix.csv`
- `runtime/strategy_deepdives/vol_expansion_opportunity_rankings.csv`
- `runtime/strategy_deepdives/vol_expansion_state_expectancy.csv`
- `runtime/strategy_deepdives/vol_expansion_strategy_family.md`
- `runtime/strategy_deepdives/vol_expansion_taxonomy.csv`
- `runtime/strategy_deepdives/vol_expansion_transition_matrix.csv`
- `runtime/trade_management_lab/exit_comparison_matrix.csv`
- `runtime/trade_management_lab/mfe_capture_curve.csv`
- `runtime/trade_management_lab/stop_loss_postmortem.csv`
- `runtime/trade_management_lab/trade_management_report.md`
- `scripts/generate_failure_rca.py`
- `scripts/generate_htf_paper_summary.py`
- `scripts/run_htf_real_paper_monitor.py`
- `scripts/start_htf_real_paper.sh`
- `strategies/trade_builder.py`
- `tests/core/test_critical_paths_warnings.py`
- `tests/test_breakout_entropy_override.py`
- `tests/test_candidate_costs.py`
- `tests/test_critical_no_deprecation_warnings.py`
- `tests/test_expiry_selection_safety.py`
- `tests/test_fallback_quote_safety.py`
- `tests/test_htf_range_expansion_spec_lock.py`
- `tests/test_htf_real_paper_monitor.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/core/test_critical_paths_warnings.py` | `PASS` | `test_reality_accepted` |
| `tests/test_breakout_entropy_override.py` | `PASS` | `test_reality_accepted` |
| `tests/test_candidate_costs.py` | `PASS` | `test_reality_accepted` |
| `tests/test_critical_no_deprecation_warnings.py` | `PASS` | `test_reality_accepted` |
| `tests/test_expiry_selection_safety.py` | `PASS` | `test_reality_accepted` |
| `tests/test_fallback_quote_safety.py` | `PASS` | `test_reality_accepted` |
| `tests/test_htf_range_expansion_spec_lock.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |
| `tests/test_htf_real_paper_monitor.py` | `BLOCK` | `fake_confidence_test_not_valid_proof` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/candidate_audits/cost_model.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_audits/engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_audits/htf_engine.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_audits/htf_strategies.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_audits/mean_reversion.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_audits/models.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_audits/orb_variants.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_audits/range_reversal.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/candidate_audits/trend_continuation.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/decision_dag.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/instruments.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/option_token_resolver.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/orchestrator.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/htf_real_paper_validation_review.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/operations/htf_range_expansion_real_paper_runbook.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/htf_range_expansion_deepdive_timeline.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/htf_range_expansion_strategy_spec.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/rejected_strategies_index.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/strategy_deepdive_checklist.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/strategy_research_index.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/strategy_research_playbook.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/vol_expansion_universe_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/candidate_failure_root_cause_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/candidate_survival_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/candidate_trade_forensics_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/corrected_candidate_survival_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/daemon_safety_audit.md` | `BLOCK` | `forbidden_boundary_marker_in_scoped_file` |
| `runtime/candidate_audits/daemon_safety_audit.md` | `BLOCK` | `forbidden_boundary_marker_in_scoped_file` |
| `runtime/candidate_audits/daily_paper_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/edge_width_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/execution_reality_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/higher_tf_edge_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/htf_range_expansion_final_survival_verdict.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/htf_range_expansion_survival_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/htf_starvation_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/leakage_audit_v2.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/paper_execution_quality_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/paper_vs_backtest_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/real_option_data_feasibility.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/regime_frequency_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/strategy_autopsy_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/stress_test_reconciliation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/candidate_audits/weekly_paper_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/evidence/live_hits_20260618/live_hit_review.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/evidence/live_hits_20260618/live_hit_review.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/evidence/live_hits_20260618/temp_raw.json` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_deepdives/edge_concentration_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_deepdives/next_candidate_recommendation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_deepdives/orb_final_verdict.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_deepdives/orb_incremental_alpha_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_deepdives/strategy_deepdive_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/strategy_deepdives/vol_expansion_strategy_family.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `runtime/trade_management_lab/trade_management_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/generate_failure_rca.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/generate_htf_paper_summary.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_htf_real_paper_monitor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/start_htf_real_paper.sh` | `PASS` | `no_restricted_boundary_marker_found` |
| `strategies/trade_builder.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/core/test_critical_paths_warnings.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_breakout_entropy_override.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_candidate_costs.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_critical_no_deprecation_warnings.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_expiry_selection_safety.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_fallback_quote_safety.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_htf_range_expansion_spec_lock.py` | `BLOCK` | `forbidden_boundary_marker_in_scoped_file` |
| `tests/test_htf_range_expansion_spec_lock.py` | `BLOCK` | `forbidden_boundary_marker_in_scoped_file` |
| `tests/test_htf_real_paper_monitor.py` | `BLOCK` | `forbidden_boundary_marker_in_scoped_file` |
| `tests/test_htf_real_paper_monitor.py` | `BLOCK` | `forbidden_boundary_marker_in_scoped_file` |
| `tests/test_htf_real_paper_monitor.py` | `BLOCK` | `forbidden_boundary_marker_in_scoped_file` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/htf_real_paper_validation_review.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/htf_real_paper_validation_review.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/htf_real_paper_validation_review.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/htf_real_paper_validation_review.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/htf_real_paper_validation_review.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/htf_real_paper_validation_review.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/htf_real_paper_validation_review.md` | `BLOCK` | `required_evidence_field_missing` |
| `docs/agent_reviews/htf_real_paper_validation_review.md` | `BLOCK` | `required_evidence_field_missing` |

## Failed Gates

- `minerva` failed with exit_code `1`: blocked findings present
- `cerberus` failed with exit_code `1`: blocked findings present
- `evidence` failed with exit_code `1`: blocked findings present
