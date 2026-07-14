# CE-11 Unified Code Excellence Gate Report

## Scope Guard

- Runs CE gates on scoped changed paths only.
- No product runtime execution.
- No code mutation.
- No auto-fix.

## Summary

- repo_root: `/Users/madhuram/.antigravity/worktrees/tradebot/feed-websocket-reconnect`
- config_path: `/Users/madhuram/.antigravity/worktrees/tradebot/feed-websocket-reconnect/.gsd-forensics.yaml`
- changed_paths: `386`
- total_findings: `694`
- total_blocks: `0`
- exit_code: `0`

## Gate Status

| Gate | Status | Exit Code | Findings | Blocks | Error |
|---|---:|---:|---:|---:|---|
| `minerva` | `PASS` | `0` | `7` | `0` |  |
| `cerberus` | `PASS` | `0` | `386` | `0` |  |
| `evidence` | `PASS` | `0` | `301` | `0` |  |

## Changed Paths

- `core/feed_fd_trace.py`
- `core/feed_robustness_evidence.py`
- `core/kite_depth_ws.py`
- `core/tick_store.py`
- `docs/AGENT_WORKFLOW.md`
- `docs/BOOK_1_CLIENT_HANDOVER_REPORT.md`
- `docs/BOOK_2_BUILD_AND_STRATEGY_MANUAL.md`
- `docs/DEPTH_SUBSCRIPTION_LIVE_VALIDATION.md`
- `docs/EDGE_44_FEED_RECOVERY_RUNTIME_WIRING.md`
- `docs/EDGE_45_SYMBOL_LEVEL_EXECUTION_SAFETY_GATE.md`
- `docs/EDGE_69_STRATEGY_REGISTRY_CANDIDATE_POOL.md`
- `docs/EDGE_70_CANDIDATE_INTENT_POOL_VALIDATOR.md`
- `docs/EDGE_70_CANDIDATE_NORMALIZATION_DEDUP.md`
- `docs/EDGE_71_CANDIDATE_CLASSIFICATION_LAYER.md`
- `docs/EDGE_80_NO_TRADE_ORACLE.md`
- `docs/EDGE_91A_SESSION_PATH_REPLAY_ANALYTICS.md`
- `docs/EDGE_92_FEED_FAULT_REPLAY_SCENARIOS.md`
- `docs/EDGE_94_END_TO_END_EDGE_ACCEPTANCE_SUITE.md`
- `docs/EDGE_BUG_SOLUTION_ROADMAP.md`
- `docs/LIVE_MARKET_VALIDATION_EVIDENCE.md`
- `docs/LIVE_TRUTH_06_STALE_CANDIDATE_HYGIENE.md`
- `docs/LIVE_TRUTH_08_SENSEX_REJECT_CALIBRATION.md`
- `docs/OFFMARKET_DEPTH_VALIDATION_PLAN.md`
- `docs/OPPORTUNITY_ENGINE_V2_PRODUCT_BIBLE.md`
- `docs/PROJECT_CHAT_EVIDENCE.md`
- `docs/PROJECT_CONTROL.md`
- `docs/PR_FEED_01_FEED_ARCHITECTURE_AUDIT_AND_CONTRACT_LOCK.md`
- `docs/PR_FEED_02R_CANONICAL_FEED_HEALTH_RECONCILIATION.md`
- `docs/PR_FEED_05_EXACT_OPTION_TOKEN_FRESHNESS_GATE.md`
- `docs/PR_FEED_12_RUNTIME_SNAPSHOT_FEED_DECISION.md`
- `docs/PR_FEED_13_CANDIDATE_PIPELINE_FEED_HOLD.md`
- `docs/agent_handoffs/feed-websocket-reconnect-antigravity.md`
- `docs/agent_reviews/441-live-truth-30-indicator-readiness-prewarm-gate.md`
- `docs/agent_reviews/442-live-truth-31-pre-market-live-readiness-gate.md`
- `docs/agent_reviews/452-feed-00-canonical-runtime-feed-truth-state-machine.md`
- `docs/agent_reviews/454-tb-edge-01-kill-fallback-execution-live.md`
- `docs/agent_reviews/458-trace-phase2-candidate-starvation-after-indicators.md`
- `docs/agent_reviews/AGENT_ELITE_06_CERBERUS_NON_ACTION_GATE.md`
- `docs/agent_reviews/CE_01_CODE_EXCELLENCE_ARCHITECTURE_CONTRACT.md`
- `docs/agent_reviews/CE_02_ARIADNE_RCA_TEMPLATE_CONTRACT.md`
- `docs/agent_reviews/CE_03_FINDING_NORMALIZATION_CONTRACT.md`
- `docs/agent_reviews/CE_04_ARIADNE_ROOT_CAUSE_CLUSTERING_ENGINE.md`
- `docs/agent_reviews/CE_05B_AGENT_PARAMETER_BRIDGE.md`
- `docs/agent_reviews/CE_05_DAEDALUS_REMEDIATION_TEMPLATE_CONTRACT.md`
- `docs/agent_reviews/CE_06_REMEDIATION_PLANNER_IMPLEMENTATION.md`
- `docs/agent_reviews/CE_07_VULCAN_PRODUCTION_HARDENING_TEMPLATE.md`
- `docs/agent_reviews/CE_08_MINERVA_TEST_REALITY_HARDENING_GATE.md`
- `docs/agent_reviews/CE_09_CERBERUS_SAFETY_REGRESSION_GATE.md`
- `docs/agent_reviews/CE_10_EVIDENCE_CONTRACT_GATE.md`
- `docs/agent_reviews/CE_11_UNIFIED_CE_GATE_RUNNER.md`
- `docs/agent_reviews/CE_12_PR_EVIDENCE_PACK_GENERATOR.md`
- `docs/agent_reviews/CE_13_CI_WIRING_FOR_CE_GATES.md`
- `docs/agent_reviews/CE_14_FIRST_REMEDIATION_PILOT.md`
- `docs/agent_reviews/EDGE-01-baseline-audit.md`
- `docs/agent_reviews/EDGE-02-paper-outcome-journal-contract.md`
- `docs/agent_reviews/EDGE-03-terminal-paper-outcome-wiring.md`
- `docs/agent_reviews/EDGE-04-runtime-terminal-outcome-hook.md`
- `docs/agent_reviews/EDGE-05-execution-router-outcome-hook.md`
- `docs/agent_reviews/EDGE-06-paper-exit-outcome-truth.md`
- `docs/agent_reviews/EDGE-07-setup-hypothesis-identity.md`
- `docs/agent_reviews/EDGE-08-adopt-setup-identity-in-paper-outcomes.md`
- `docs/agent_reviews/EDGE-09-runtime-setup-identity-adoption.md`
- `docs/agent_reviews/EDGE-10-runtime-readiness-failure-snapshot.md`
- `docs/agent_reviews/EDGE-11-runtime-truth-breakdown.md`
- `docs/agent_reviews/EDGE-12-feed-startup-root-cause.md`
- `docs/agent_reviews/EDGE-13-ws-handshake-proof-contract.md`
- `docs/agent_reviews/EDGE-13b-wire-ws-handshake-proof.md`
- `docs/agent_reviews/EDGE-14-status-provenance.md`
- `docs/agent_reviews/EDGE-15-status-freshness-guard.md`
- `docs/agent_reviews/EDGE-26-debug-forensics-cli-path-and-skew-fix.md`
- `docs/agent_reviews/EDGE-26-fast-engine-cycle-boundary-proof.md`
- `docs/agent_reviews/EDGE-27-legacy-cycle-boundary-proof.md`
- `docs/agent_reviews/EDGE-28-main-post-db-boundary-proof.md`
- `docs/agent_reviews/EDGE-29-fast-loop-timer-trigger-before-feed-debug.md`
- `docs/agent_reviews/EDGE-30-deferred-work-ledger.md`
- `docs/agent_reviews/EDGE-31-executable-trade-truth-firebreak.md`
- `docs/agent_reviews/EDGE-32-candidate-quote-freshness-contract.md`
- `docs/agent_reviews/EDGE-33-option-bid-ask-spread-truth-gate.md`
- `docs/agent_reviews/EDGE-34-execution-first-scoring-reweight.md`
- `docs/agent_reviews/EDGE-35-strategy-signal-quality-contract.md`
- `docs/agent_reviews/EDGE-36-feed-recovery-evidence.md`
- `docs/agent_reviews/EDGE-37-evidence-replay-quality-report.md`
- `docs/agent_reviews/EDGE-39-expired-contract-token-resolution-guard.md`
- `docs/agent_reviews/EDGE-40-quote-timestamp-age-consistency-guard.md`
- `docs/agent_reviews/EDGE_77_STRATEGY_SPECIFIC_EXIT_MODELS.md`
- `docs/agent_reviews/EDGE_78_STRATEGY_PARAMETER_ROBUSTNESS_TESTS.md`
- `docs/agent_reviews/EDGE_79_STRATEGY_CONFLICT_CONSENSUS_ENGINE.md`
- `docs/agent_reviews/EDGE_80_NO_TRADE_ORACLE.md`
- `docs/agent_reviews/EDGE_81_NO_TRADE_EVIDENCE_REVIEW_UI.md`
- `docs/agent_reviews/EDGE_82_FINAL_EXECUTABLE_QUALITY_GATE.md`
- `docs/agent_reviews/EDGE_83_PAPER_TRUTH_JOURNAL.md`
- `docs/agent_reviews/EDGE_84_OUTCOME_REDUCER.md`
- `docs/agent_reviews/EDGE_85_STRATEGY_EXPECTANCY_BY_REGIME.md`
- `docs/agent_reviews/EDGE_86_SLIPPAGE_COST_TRUTH.md`
- `docs/agent_reviews/EDGE_87_STRATEGY_FAMILY_KILL_KEEP_REPORT.md`
- `docs/agent_reviews/EDGE_88_STRATEGY_LIFECYCLE_STATES.md`
- `docs/agent_reviews/EDGE_89_STRATEGY_PROMOTION_GATE.md`
- `docs/agent_reviews/EDGE_90_STRATEGY_SUSPENSION_RETIREMENT_RULES.md`
- `docs/agent_reviews/GSD_FOR_01_REPO_FORENSICS_ARCHITECTURE_CONTRACT.md`
- `docs/agent_reviews/GSD_FOR_02_TRADEBOT_FORENSICS_PROFILE.md`
- `docs/agent_reviews/GSD_FOR_03_REPO_CARTOGRAPHER_SCANNER.md`
- `docs/agent_reviews/GSD_FOR_04_RUNTIME_WIRING_AUDIT.md`
- `docs/agent_reviews/GSD_FOR_05_CRITICAL_MODULE_CALLER_CHECK.md`
- `docs/agent_reviews/GSD_FOR_06_TEST_REALITY_CLASSIFIER.md`
- `docs/agent_reviews/GSD_FOR_07_SAFETY_BOUNDARY_AUDITOR.md`
- `docs/agent_reviews/GSD_FOR_08_EVIDENCE_AUDITOR.md`
- `docs/agent_reviews/GSD_FOR_09_ARCHITECTURE_DRIFT_DETECTOR.md`
- `docs/agent_reviews/GSD_FOR_10_UNIFIED_FORENSICS_RUNNER.md`
- `docs/agent_reviews/GSD_FOR_11_3_AGENT_EVIDENCE_INTEGRATION.md`
- `docs/agent_reviews/GSD_FOR_12_FIRST_TRADEBOT_BASELINE_AUDIT.md`
- `docs/agent_reviews/GSD_FOR_12_TRADEBOT_BASELINE_AGENT_GATE.md`
- `docs/agent_reviews/GSD_FOR_13_FORENSICS_GATE_FOR_FUTURE_PRS.md`
- `docs/agent_reviews/GSD_FOR_14_PRODUCT_REALITY_AUDIT_LAYER.md`
- `docs/agent_reviews/GSD_FOR_15_CI_REQUIRED_FORENSICS_PR_GATE.md`
- `docs/agent_reviews/HOTFIX_EDGE_79A_LIVE_INDICATOR_READINESS_DIAGNOSTICS.md`
- `docs/agent_reviews/HOTFIX_EDGE_79B_MARKET_CLOSE_FEED_STATE_CLASSIFIER.md`
- `docs/agent_reviews/LIVE_TRUTH_01_TOP_OPPORTUNITIES_EXECUTABLE_ALIGNMENT.md`
- `docs/agent_reviews/LIVE_TRUTH_02_LATEST_ARTIFACT_NON_EMPTY_PRESERVATION.md`
- `docs/agent_reviews/LIVE_TRUTH_03_RUNTIME_SNAPSHOT_FRESHNESS_GUARD.md`
- `docs/agent_reviews/LIVE_TRUTH_04_FEED_RUNTIME_WRITER_LIVENESS.md`
- `docs/agent_reviews/LIVE_TRUTH_05_MARKET_CLOSE_STATE_CONSISTENCY.md`
- `docs/agent_reviews/LIVE_TRUTH_06_STALE_CANDIDATE_HYGIENE.md`
- `docs/agent_reviews/LIVE_TRUTH_07_LATENCY_SLO_OSCILLATION.md`
- `docs/agent_reviews/LIVE_TRUTH_08_SENSEX_REJECT_CALIBRATION.md`
- `docs/agent_reviews/LIVE_TRUTH_09_RUNTIME_HEALTH_ARTIFACT_CONSISTENCY.md`
- `docs/agent_reviews/LIVE_TRUTH_10_STRATEGY_PERF_SHADOW_FALLBACK.md`
- `docs/agent_reviews/LIVE_TRUTH_11_INDICATOR_READINESS_DECISION_REJECT.md`
- `docs/agent_reviews/LIVE_TRUTH_12_LATENCY_HOTPATH_EVIDENCE.md`
- `docs/agent_reviews/PR-195-unit-scope-execution-selection-safety.md`
- `docs/agent_reviews/PR-5_strategy_certification.md`
- `docs/agent_reviews/PR-627_edge_proof.md`
- `docs/agent_reviews/PR-6_research_registry.md`
- `docs/agent_reviews/PR-7_live_drift.md`
- `docs/agent_reviews/PR100_LIVE_OBSERVATION_EVIDENCE_HARDENING.md`
- `docs/agent_reviews/PR101_FALLBACK_CONTRACT_EXECUTION_FIREWALL.md`
- `docs/agent_reviews/PR102_CONTRACT_RESOLUTION_FALLBACK_PROPAGATION_GATE.md`
- `docs/agent_reviews/PR103_RUNTIME_TRUTH_CONSISTENCY_REGIME_DIAGNOSTICS.md`
- `docs/agent_reviews/PR104_FINAL_EMIT_TRUTH_CONTRACT.md`
- `docs/agent_reviews/PR105_BLOCKED_CANDIDATE_LIFECYCLE_SCHEMA_CONSISTENCY.md`
- `docs/agent_reviews/PR90_PAPER_DECISION_CONTRACT_SNAPSHOTS.md`
- `docs/agent_reviews/PR91_STRICT_PAPER_ORDER_STATE_MACHINE.md`
- `docs/agent_reviews/PR92_REALISTIC_OPTION_FILL_SLIPPAGE_MODEL.md`
- `docs/agent_reviews/PR93_PAPER_RISK_LEDGER.md`
- `docs/agent_reviews/PR94_FULL_SESSION_PAPER_TRADING_GATE.md`
- `docs/agent_reviews/PR95_PAPER_SESSION_GATE_CONTRACT_SNAPSHOTS.md`
- `docs/agent_reviews/PR95_PAPER_TRADING_RUNBOOK_COMMAND.md`
- `docs/agent_reviews/PR96_LIVE_DRY_RUN_BROKER_PAYLOAD_GATE.md`
- `docs/agent_reviews/PR97_BROKER_RECONCILIATION_DRY_RUN_PROOF.md`
- `docs/agent_reviews/PR98_KILL_SWITCH_RISK_HALT_DRY_RUN_PROOF.md`
- `docs/agent_reviews/PR99_LIVE_OBSERVATION_RUNTIME_SAFETY_FLAGS.md`
- `docs/agent_reviews/PR_FEED_08_PURE_TICK_UTILITY_HELPERS.md`
- `docs/agent_reviews/PR_FEED_09_RECONNECT_DECISION_POLICY.md`
- `docs/agent_reviews/PR_FEED_10_SUBSCRIPTION_BUDGET_POLICY.md`
- `docs/agent_reviews/PR_FEED_11_RUNTIME_SNAPSHOT_BUILDER.md`
- `docs/agent_reviews/PR_FEED_17_RESOLUTION_READ_MODEL.md`
- `docs/agent_reviews/PR_FEED_18_WS_LIFECYCLE_SHELL.md`
- `docs/agent_reviews/PR_FEED_19_CALLBACK_THIN_WIRING.md`
- `docs/agent_reviews/UPSTOX_DAILY_CAPTURE.md`
- `docs/agent_reviews/agent-command-center-live-sidecar.md`
- `docs/agent_reviews/agent-command-center.md`
- `docs/agent_reviews/ai_optimization_layer.md`
- `docs/agent_reviews/all_strategy_available_data_backtest_20260629.md`
- `docs/agent_reviews/backtest-runtime-replay-empty-source-readiness.md`
- `docs/agent_reviews/backtest-runtime-replay-readiness-verdict.md`
- `docs/agent_reviews/candidate-executability-evidence-pack.md`
- `docs/agent_reviews/candidate-outcome-fixture-loader.md`
- `docs/agent_reviews/candidate-outcome-report-writer.md`
- `docs/agent_reviews/candidate-outcome-truth-contract.md`
- `docs/agent_reviews/candidate-supply-zero-attribution.md`
- `docs/agent_reviews/command-center-session-scoped-rca.md`
- `docs/agent_reviews/continuous_architecture_phase2.md`
- `docs/agent_reviews/edge-02-hard-fallback-execution-kill-gate.md`
- `docs/agent_reviews/edge-03-runtime-candidate-outcome-tracker.md`
- `docs/agent_reviews/edge-04-cost-slippage-truth-model.md`
- `docs/agent_reviews/edge-05-strategy-regime-expectancy-aggregator.md`
- `docs/agent_reviews/edge-06-setup-fingerprint-contract.md`
- `docs/agent_reviews/edge-07-kill-keep-strategy-gate.md`
- `docs/agent_reviews/edge-08-expectancy-based-ranking-engine.md`
- `docs/agent_reviews/edge-09-top-opportunity-selector.md`
- `docs/agent_reviews/edge-10-buy-sell-direction-outcome-support.md`
- `docs/agent_reviews/edge-11-shadow-market-validation-runner.md`
- `docs/agent_reviews/edge-12-edge-readiness-report.md`
- `docs/agent_reviews/edge-next-01-score-separation-audit-fix.md`
- `docs/agent_reviews/edge-next-02-regime-aware-ranking-weights.md`
- `docs/agent_reviews/edge-next-03-candidate-pool-quality-gate.md`
- `docs/agent_reviews/edge-next-04-strategy-baseline-comparison.md`
- `docs/agent_reviews/edge-next-05-offline-replay-topn-quality-test.md`
- `docs/agent_reviews/edge-next-06-bearish-range-no-trade-coverage-hardening.md`
- `docs/agent_reviews/edge_38_runtime_evidence_capture_guard.md`
- `docs/agent_reviews/edge_41_fallback_execution_firewall.md`
- `docs/agent_reviews/edge_42_quote_truth_single_source.md`
- `docs/agent_reviews/edge_43_feed_health_split_brain_fix.md`
- `docs/agent_reviews/edge_44_feed_recovery_runtime_wiring.md`
- `docs/agent_reviews/edge_45_symbol_level_execution_safety_gate.md`
- `docs/agent_reviews/edge_46_soft_reject_separation.md`
- `docs/agent_reviews/edge_47_candidate_status_contract_cleanup.md`
- `docs/agent_reviews/edge_48_scoring_truth_hardening.md`
- `docs/agent_reviews/edge_49_opportunity_selector_evidence_upgrade.md`
- `docs/agent_reviews/edge_50_latest_artifact_freshness_guard.md`
- `docs/agent_reviews/edge_51_latest_artifact_freshness_runtime_wiring.md`
- `docs/agent_reviews/edge_52_dashboard_freshness_visibility.md`
- `docs/agent_reviews/edge_53_streamlit_freshness_panel_rendering.md`
- `docs/agent_reviews/edge_54_home_page_freshness_panel_placement.md`
- `docs/agent_reviews/edge_55_tiny_runtime_home_freshness_panel_call.md`
- `docs/agent_reviews/edge_56_home_freshness_failure_visibility.md`
- `docs/agent_reviews/edge_57_fallback_advisory_only_entry_contract.md`
- `docs/agent_reviews/edge_58_top_opportunity_executable_truth.md`
- `docs/agent_reviews/edge_59_top_opportunity_truth_reader_wiring.md`
- `docs/agent_reviews/edge_60_buy_pe_ce_directional_bias_audit.md`
- `docs/agent_reviews/edge_61_capital_selection_policy_contract.md`
- `docs/agent_reviews/edge_62_roadmap_reconciliation.md`
- `docs/agent_reviews/edge_63_market_state_model.md`
- `docs/agent_reviews/edge_64_regime_state_machine.md`
- `docs/agent_reviews/edge_65_strategy_spec_registry.md`
- `docs/agent_reviews/edge_66_strategy_quality_audit.md`
- `docs/agent_reviews/edge_67_strategy_hypothesis_contracts.md`
- `docs/agent_reviews/edge_68_replace_hardcoded_strategy_eligibility.md`
- `docs/agent_reviews/edge_69_strategy_registry_candidate_pool.md`
- `docs/agent_reviews/edge_70_candidate_normalization_dedup.md`
- `docs/agent_reviews/edge_71_candidate_classification_layer.md`
- `docs/agent_reviews/edge_72_hard_downgrade_engine.md`
- `docs/agent_reviews/edge_73_candidate_readiness_summary.md`
- `docs/agent_reviews/elite-backtester-20260613.md`
- `docs/agent_reviews/enable_monitor_run_loop.md`
- `docs/agent_reviews/feat-audit-only-live-supervisor.md`
- `docs/agent_reviews/feed-stab-02-feed-supervisor-state-machine.md`
- `docs/agent_reviews/feed-stab-03-reconnect-quarantine.md`
- `docs/agent_reviews/feed-stab-04-feed-readiness-for-candidates-contract.md`
- `docs/agent_reviews/feed-stab-06-subscription-truth-resubscribe-verification.md`
- `docs/agent_reviews/feed-stab-07-feed-event-journal.md`
- `docs/agent_reviews/feed-stab-08-feed-soak-runner.md`
- `docs/agent_reviews/feed-truth-consistency-evidence-cleanup.md`
- `docs/agent_reviews/feed-zombie-lifecycle-pr555.md`
- `docs/agent_reviews/feed_100k_descriptor_control_audit.md`
- `docs/agent_reviews/feed_20k_descriptor_control_audit.md`
- `docs/agent_reviews/feed_async_descriptor_control_audit.md`
- `docs/agent_reviews/feed_async_persistence_pressure_audit.md`
- `docs/agent_reviews/feed_descriptor_control_audit.md`
- `docs/agent_reviews/feed_integrity_and_health_duration.md`
- `docs/agent_reviews/feed_websocket_reconnect_resubscription_audit.md`
- `docs/agent_reviews/fix-ws-recovery-reactor-not-restartable-thread-storm.md`
- `docs/agent_reviews/fix-ws1006-reactor-fatal-simulation-tests.md`
- `docs/agent_reviews/fix_htf_safety_integration_and_fail_closed.md`
- `docs/agent_reviews/fresh-feedtruth-audit-proof-pack.md`
- `docs/agent_reviews/grid-search-atr-20260613.md`
- `docs/agent_reviews/intelligence-layer-architecture-contract.md`
- `docs/agent_reviews/live-feedtruth-audit-harness.md`
- `docs/agent_reviews/live-rca-auth-tightening.md`
- `docs/agent_reviews/offline-feed-candidate-truth-proof-pack.md`
- `docs/agent_reviews/pairs-trading-live-engine-20260614.md`
- `docs/agent_reviews/pr-612-outcome-evidence-engine.md`
- `docs/agent_reviews/pr-edge-01-runtime-candidate-journal.md`
- `docs/agent_reviews/pr199_observability_architecture.md`
- `docs/agent_reviews/pr2-regime-canonicalization.md`
- `docs/agent_reviews/pr246_advisory_entry_source_normalization.md`
- `docs/agent_reviews/pr247_advisory_schema_boundary_normalization.md`
- `docs/agent_reviews/pr277_test_isolation_decay_input.md`
- `docs/agent_reviews/pr278_trade_builder_candidate_breadth_expiry.md`
- `docs/agent_reviews/pr279_instance_lock_subprocess_readiness.md`
- `docs/agent_reviews/pr3-canonical-regime-score-separation.md`
- `docs/agent_reviews/pr4-selector-fallback-contract.md`
- `docs/agent_reviews/pr527-candidate-lifecycle-snapshot.md`
- `docs/agent_reviews/pr528-phase2-boundary-cleanup.md`
- `docs/agent_reviews/pr529-regime-aware-dynamic-scoring-profiles.md`
- `docs/agent_reviews/pr530-regime-profile-opportunity-scoring-opt-in.md`
- `docs/agent_reviews/pr531-ranking-profile-metadata-propagation.md`
- `docs/agent_reviews/pr532-advanced-score-delta-evidence.md`
- `docs/agent_reviews/pr585-candidate-flow-diagnostics.md`
- `docs/agent_reviews/pr635_canonical_ranked_runtime_bridge.md`
- `docs/agent_reviews/pr636_ranking_proof_pack_truth.md`
- `docs/agent_reviews/pr637_dirty_option_bridge_ranking.md`
- `docs/agent_reviews/pr639_audit_strategy_structural.md`
- `docs/agent_reviews/pr640_audit_regime_evidence.md`
- `docs/agent_reviews/pr641_feed_execution_truth_minimal.md`
- `docs/agent_reviews/pr647_backtest_trust_integration.md`
- `docs/agent_reviews/pr73_opportunity_score_v1.md`
- `docs/agent_reviews/pr_10_certification_persistence.md`
- `docs/agent_reviews/pr_11_live_drift_persistence.md`
- `docs/agent_reviews/pr_4_statistical_validation_engine.md`
- `docs/agent_reviews/pr_595_ml_overlay.md`
- `docs/agent_reviews/pr_607_agent_review.md`
- `docs/agent_reviews/pr_610_agent_review.md`
- `docs/agent_reviews/pr_candidate_outcome_calibration.md`
- `docs/agent_reviews/pr_edge_roadmap_bug_solution_docs.md`
- `docs/agent_reviews/pr_feed_01_feed_architecture_audit_and_contract_lock.md`
- `docs/agent_reviews/pr_feed_02r_canonical_feed_health_reconciliation.md`
- `docs/agent_reviews/pr_feed_03_feed_hold_gate.md`
- `docs/agent_reviews/pr_feed_04_feed_recovery_warmup_gate.md`
- `docs/agent_reviews/pr_feed_05_exact_option_token_freshness_gate.md`
- `docs/agent_reviews/pr_feed_12_runtime_snapshot_feed_decision.md`
- `docs/agent_reviews/pr_feed_13_candidate_pipeline_feed_hold.md`
- `docs/agent_reviews/pr_feed_13a_review_queue_non_blocking_quote_lookup.md`
- `docs/agent_reviews/pr_feed_14_ranking_suppression_for_feed_risky_candidates.md`
- `docs/agent_reviews/pr_feed_15_live_paper_feed_policy_separation.md`
- `docs/agent_reviews/pr_feed_16_feed_config_hardening.md`
- `docs/agent_reviews/pr_feed_20_feed_runtime_evidence_bundle.md`
- `docs/agent_reviews/pr_feed_20r_feed_fault_replay_tests.md`
- `docs/agent_reviews/pr_institutional_paper_trading.md`
- `docs/agent_reviews/pr_ml_acceptance_gate.md`
- `docs/agent_reviews/pr_obs_01_observability_identity.md`
- `docs/agent_reviews/pr_obs_02_decision_event_schema.md`
- `docs/agent_reviews/pr_obs_03_structured_json_logging_adapter.md`
- `docs/agent_reviews/pr_obs_04_runtime_cycle_event_emitter_shell.md`
- `docs/agent_reviews/pr_obs_05_candidate_lifecycle_events.md`
- `docs/agent_reviews/pr_obs_06_feed_state_events.md`
- `docs/agent_reviews/pr_obs_07_tracing.md`
- `docs/agent_reviews/pr_obs_08_metrics.md`
- `docs/agent_reviews/pr_obs_09_local_observability_stack.md`
- `docs/agent_reviews/pr_obs_10_grafana_dashboard_provisioning.md`
- `docs/agent_reviews/pr_obs_11_loki_log_correlation.md`
- `docs/agent_reviews/pr_obs_12_observability_evidence_bundle.md`
- `docs/agent_reviews/pr_obs_13_safety_invariant_tests.md`
- `docs/agent_reviews/pr_obs_14_trace_replay_cli.md`
- `docs/agent_reviews/pr_obs_15a_legacy_evidence_import.md`
- `docs/agent_reviews/pr_wfa_gate_revisit.md`
- `docs/agent_reviews/profit-filters-20260613.md`
- `docs/agent_reviews/provenance_safe_resumable_strategy_edge_audit.md`
- `docs/agent_reviews/qa-edge-first-behavior-strategy.md`
- `docs/agent_reviews/qa-eight-year-backtest-strategy-edge.md`
- `docs/agent_reviews/qa_full_implemented_strategy_truth_audit.md`
- `docs/agent_reviews/rag_00_review.md`
- `docs/agent_reviews/ram_next_isolated_work_pr648.md`
- `docs/agent_reviews/ram_replay_context_proof.md`
- `docs/agent_reviews/real-candidate-supply-contract.md`
- `docs/agent_reviews/real-option-data-backtest-runner-20260614.md`
- `docs/agent_reviews/regime_entropy_truth_contract.md`
- `docs/agent_reviews/research_add_htf_cost_adjusted_edge_retest.md`
- `docs/agent_reviews/runtime_boot_01_token_artifact_scan_cache.md`
- `docs/agent_reviews/strict-research-boundaries-enforcement-20260614.md`
- `docs/agent_reviews/tick_driven_replay_migration.md`
- `docs/agent_reviews/trade-quality-truth-audit.md`
- `docs/agent_reviews/vectorized-signals-20260613.md`
- `docs/audits/profitable_edge_gap_audit_20260629.md`
- `docs/audits/strategy_contract_and_edge_readiness_audit.md`
- `docs/code_excellence/ariadne/MAPPING_RULES.md`
- `docs/code_excellence/daedalus/CHANGE_RULES.md`
- `docs/code_excellence/finding_normalization/DEDUPLICATION_RULES.md`
- `docs/code_excellence/finding_normalization/NORMALIZED_FINDING_SCHEMA.md`
- `docs/code_excellence/finding_normalization/SEVERITY_SOURCE_MAPPING.md`
- `docs/intelligence/ARCHITECTURE.md`
- `docs/intelligence/INTELLIGENCE_LAYER_BIBLE.md`
- `docs/intelligence/ROADMAP.md`
- `docs/mip/01_repository_reverse_engineering.md`
- `docs/mip/09_tradebot_integration_report.md`
- `docs/mip/11_test_report.md`
- `docs/mip_excellence/02_end_to_end_validation.md`
- `docs/mip_excellence/07_security_audit.md`
- `docs/observability/EVENT_SCHEMA.md`
- `docs/observability/OBSERVABILITY_ARCHITECTURE.md`
- `docs/observability/TRACE_REPLAY.md`
- `docs/observability/feed_reconnect_rca_20260629.md`
- `docs/qa/TRADEBOT_FEATURE_TEST_MATRIX.md`
- `docs/qa/TRADEBOT_QA_BEHAVIOR_STRATEGY.md`
- `docs/rca/feed-rca-20260610.md`
- `docs/repo_forensics/AGENT_PARAMETER_CALIBRATION.md`
- `docs/repo_forensics/EVIDENCE_AUDIT_TEMPLATE.md`
- `docs/repo_forensics/SAFETY_BOUNDARY_TEMPLATE.md`
- `docs/repo_forensics/TRADEBOT_AUDIT_CHECKLIST.md`
- `docs/repo_forensics/TRADEBOT_PROFILE.md`
- `docs/repo_forensics/reports/baseline_latest.md`
- `docs/research/final_replay_proof_policy.md`
- `docs/research/replay_candidate_likely_event_search.md`
- `docs/research/replay_context_bundle_oos_rerun_audit.md`
- `docs/research/replay_context_bundle_real_artifact_audit.md`
- `docs/research/replay_context_bundle_recorder.md`
- `docs/research/replay_context_contract.md`
- `docs/research/replay_context_field_roundtrip_audit.md`
- `docs/research/replay_context_policy_rerun_final_audit.md`
- `docs/research/replay_context_regenerated_artifact_audit.md`
- `docs/research/replay_context_remaining_blockers.md`
- `docs/research/replay_context_source_artifact_gap.md`
- `docs/research/strategy_backtesting_engine_audit.md`
- `docs/research/strict_option_replay_export_adapter.md`
- `docs/strategy_truth/07_semantic_gap_audit.md`
- `docs/superpowers/plans/2026-05-06-pro-strategy-shadow-wirein.md`
- `docs/superpowers/plans/2026-06-11-eight-year-backtest-strategy-edge.md`
- `docs/superpowers/specs/2026-05-06-pro-strategy-shadow-wirein-design.md`
- `scripts/run_feed_robustness_replay.py`
- `tests/test_feed_fd_trace.py`
- `tests/test_feed_robustness_replay_runner.py`
- `tests/test_htf_real_paper_monitor.py`
- `tests/test_kite_auth_consistency.py`
- `tests/test_kite_depth_ws_stability.py`
- `tests/test_tick_store.py`
- `tests/test_ws_tick_ingestion_updates_tick_store.py`
- `token_convert.py`

## Minerva Findings

| Path | Verdict | Reason |
|---|---|---|
| `tests/test_feed_fd_trace.py` | `PASS` | `test_reality_accepted` |
| `tests/test_feed_robustness_replay_runner.py` | `PASS` | `test_reality_accepted` |
| `tests/test_htf_real_paper_monitor.py` | `PASS` | `test_reality_accepted` |
| `tests/test_kite_auth_consistency.py` | `PASS` | `test_reality_accepted` |
| `tests/test_kite_depth_ws_stability.py` | `PASS` | `test_reality_accepted` |
| `tests/test_tick_store.py` | `PASS` | `test_reality_accepted` |
| `tests/test_ws_tick_ingestion_updates_tick_store.py` | `PASS` | `test_reality_accepted` |

## Cerberus Findings

| Path | Verdict | Reason |
|---|---|---|
| `core/feed_fd_trace.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/feed_robustness_evidence.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/kite_depth_ws.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `core/tick_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/AGENT_WORKFLOW.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/BOOK_1_CLIENT_HANDOVER_REPORT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/BOOK_2_BUILD_AND_STRATEGY_MANUAL.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/DEPTH_SUBSCRIPTION_LIVE_VALIDATION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_44_FEED_RECOVERY_RUNTIME_WIRING.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_45_SYMBOL_LEVEL_EXECUTION_SAFETY_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_69_STRATEGY_REGISTRY_CANDIDATE_POOL.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_70_CANDIDATE_INTENT_POOL_VALIDATOR.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_70_CANDIDATE_NORMALIZATION_DEDUP.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_71_CANDIDATE_CLASSIFICATION_LAYER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_80_NO_TRADE_ORACLE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_91A_SESSION_PATH_REPLAY_ANALYTICS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_92_FEED_FAULT_REPLAY_SCENARIOS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_94_END_TO_END_EDGE_ACCEPTANCE_SUITE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/EDGE_BUG_SOLUTION_ROADMAP.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/LIVE_MARKET_VALIDATION_EVIDENCE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/LIVE_TRUTH_06_STALE_CANDIDATE_HYGIENE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/LIVE_TRUTH_08_SENSEX_REJECT_CALIBRATION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/OFFMARKET_DEPTH_VALIDATION_PLAN.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/OPPORTUNITY_ENGINE_V2_PRODUCT_BIBLE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/PROJECT_CHAT_EVIDENCE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/PROJECT_CONTROL.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/PR_FEED_01_FEED_ARCHITECTURE_AUDIT_AND_CONTRACT_LOCK.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/PR_FEED_02R_CANONICAL_FEED_HEALTH_RECONCILIATION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/PR_FEED_05_EXACT_OPTION_TOKEN_FRESHNESS_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/PR_FEED_12_RUNTIME_SNAPSHOT_FEED_DECISION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/PR_FEED_13_CANDIDATE_PIPELINE_FEED_HOLD.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_handoffs/feed-websocket-reconnect-antigravity.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/441-live-truth-30-indicator-readiness-prewarm-gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/442-live-truth-31-pre-market-live-readiness-gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/452-feed-00-canonical-runtime-feed-truth-state-machine.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/454-tb-edge-01-kill-fallback-execution-live.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/458-trace-phase2-candidate-starvation-after-indicators.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/AGENT_ELITE_06_CERBERUS_NON_ACTION_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_01_CODE_EXCELLENCE_ARCHITECTURE_CONTRACT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_02_ARIADNE_RCA_TEMPLATE_CONTRACT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_03_FINDING_NORMALIZATION_CONTRACT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_04_ARIADNE_ROOT_CAUSE_CLUSTERING_ENGINE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_05B_AGENT_PARAMETER_BRIDGE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_05_DAEDALUS_REMEDIATION_TEMPLATE_CONTRACT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_06_REMEDIATION_PLANNER_IMPLEMENTATION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_07_VULCAN_PRODUCTION_HARDENING_TEMPLATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_08_MINERVA_TEST_REALITY_HARDENING_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_09_CERBERUS_SAFETY_REGRESSION_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_10_EVIDENCE_CONTRACT_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_11_UNIFIED_CE_GATE_RUNNER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_12_PR_EVIDENCE_PACK_GENERATOR.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_13_CI_WIRING_FOR_CE_GATES.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/CE_14_FIRST_REMEDIATION_PILOT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-01-baseline-audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-02-paper-outcome-journal-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-03-terminal-paper-outcome-wiring.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-04-runtime-terminal-outcome-hook.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-05-execution-router-outcome-hook.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-06-paper-exit-outcome-truth.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-07-setup-hypothesis-identity.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-08-adopt-setup-identity-in-paper-outcomes.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-09-runtime-setup-identity-adoption.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-10-runtime-readiness-failure-snapshot.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-11-runtime-truth-breakdown.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-12-feed-startup-root-cause.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-13-ws-handshake-proof-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-13b-wire-ws-handshake-proof.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-14-status-provenance.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-15-status-freshness-guard.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-26-debug-forensics-cli-path-and-skew-fix.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-26-fast-engine-cycle-boundary-proof.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-27-legacy-cycle-boundary-proof.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-28-main-post-db-boundary-proof.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-29-fast-loop-timer-trigger-before-feed-debug.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-30-deferred-work-ledger.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-31-executable-trade-truth-firebreak.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-32-candidate-quote-freshness-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-33-option-bid-ask-spread-truth-gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-34-execution-first-scoring-reweight.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-35-strategy-signal-quality-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-36-feed-recovery-evidence.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-37-evidence-replay-quality-report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-39-expired-contract-token-resolution-guard.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE-40-quote-timestamp-age-consistency-guard.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_77_STRATEGY_SPECIFIC_EXIT_MODELS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_78_STRATEGY_PARAMETER_ROBUSTNESS_TESTS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_79_STRATEGY_CONFLICT_CONSENSUS_ENGINE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_80_NO_TRADE_ORACLE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_81_NO_TRADE_EVIDENCE_REVIEW_UI.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_82_FINAL_EXECUTABLE_QUALITY_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_83_PAPER_TRUTH_JOURNAL.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_84_OUTCOME_REDUCER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_85_STRATEGY_EXPECTANCY_BY_REGIME.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_86_SLIPPAGE_COST_TRUTH.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_87_STRATEGY_FAMILY_KILL_KEEP_REPORT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_88_STRATEGY_LIFECYCLE_STATES.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_89_STRATEGY_PROMOTION_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/EDGE_90_STRATEGY_SUSPENSION_RETIREMENT_RULES.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_01_REPO_FORENSICS_ARCHITECTURE_CONTRACT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_02_TRADEBOT_FORENSICS_PROFILE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_03_REPO_CARTOGRAPHER_SCANNER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_04_RUNTIME_WIRING_AUDIT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_05_CRITICAL_MODULE_CALLER_CHECK.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_06_TEST_REALITY_CLASSIFIER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_07_SAFETY_BOUNDARY_AUDITOR.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_08_EVIDENCE_AUDITOR.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_09_ARCHITECTURE_DRIFT_DETECTOR.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_10_UNIFIED_FORENSICS_RUNNER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_11_3_AGENT_EVIDENCE_INTEGRATION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_12_FIRST_TRADEBOT_BASELINE_AUDIT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_12_TRADEBOT_BASELINE_AGENT_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_13_FORENSICS_GATE_FOR_FUTURE_PRS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_14_PRODUCT_REALITY_AUDIT_LAYER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/GSD_FOR_15_CI_REQUIRED_FORENSICS_PR_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/HOTFIX_EDGE_79A_LIVE_INDICATOR_READINESS_DIAGNOSTICS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/HOTFIX_EDGE_79B_MARKET_CLOSE_FEED_STATE_CLASSIFIER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_01_TOP_OPPORTUNITIES_EXECUTABLE_ALIGNMENT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_02_LATEST_ARTIFACT_NON_EMPTY_PRESERVATION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_03_RUNTIME_SNAPSHOT_FRESHNESS_GUARD.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_04_FEED_RUNTIME_WRITER_LIVENESS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_05_MARKET_CLOSE_STATE_CONSISTENCY.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_06_STALE_CANDIDATE_HYGIENE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_07_LATENCY_SLO_OSCILLATION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_08_SENSEX_REJECT_CALIBRATION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_09_RUNTIME_HEALTH_ARTIFACT_CONSISTENCY.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_10_STRATEGY_PERF_SHADOW_FALLBACK.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_11_INDICATOR_READINESS_DECISION_REJECT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/LIVE_TRUTH_12_LATENCY_HOTPATH_EVIDENCE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR-195-unit-scope-execution-selection-safety.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR-5_strategy_certification.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR-627_edge_proof.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR-6_research_registry.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR-7_live_drift.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR100_LIVE_OBSERVATION_EVIDENCE_HARDENING.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR101_FALLBACK_CONTRACT_EXECUTION_FIREWALL.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR102_CONTRACT_RESOLUTION_FALLBACK_PROPAGATION_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR103_RUNTIME_TRUTH_CONSISTENCY_REGIME_DIAGNOSTICS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR104_FINAL_EMIT_TRUTH_CONTRACT.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR105_BLOCKED_CANDIDATE_LIFECYCLE_SCHEMA_CONSISTENCY.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR90_PAPER_DECISION_CONTRACT_SNAPSHOTS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR91_STRICT_PAPER_ORDER_STATE_MACHINE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR92_REALISTIC_OPTION_FILL_SLIPPAGE_MODEL.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR93_PAPER_RISK_LEDGER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR94_FULL_SESSION_PAPER_TRADING_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR95_PAPER_SESSION_GATE_CONTRACT_SNAPSHOTS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR95_PAPER_TRADING_RUNBOOK_COMMAND.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR96_LIVE_DRY_RUN_BROKER_PAYLOAD_GATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR97_BROKER_RECONCILIATION_DRY_RUN_PROOF.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR98_KILL_SWITCH_RISK_HALT_DRY_RUN_PROOF.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR99_LIVE_OBSERVATION_RUNTIME_SAFETY_FLAGS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR_FEED_08_PURE_TICK_UTILITY_HELPERS.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR_FEED_09_RECONNECT_DECISION_POLICY.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR_FEED_10_SUBSCRIPTION_BUDGET_POLICY.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR_FEED_11_RUNTIME_SNAPSHOT_BUILDER.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR_FEED_17_RESOLUTION_READ_MODEL.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR_FEED_18_WS_LIFECYCLE_SHELL.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/PR_FEED_19_CALLBACK_THIN_WIRING.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/UPSTOX_DAILY_CAPTURE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/agent-command-center-live-sidecar.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/agent-command-center.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/ai_optimization_layer.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/all_strategy_available_data_backtest_20260629.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/backtest-runtime-replay-empty-source-readiness.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/backtest-runtime-replay-readiness-verdict.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/candidate-executability-evidence-pack.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/candidate-outcome-fixture-loader.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/candidate-outcome-report-writer.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/candidate-outcome-truth-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/candidate-supply-zero-attribution.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/command-center-session-scoped-rca.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/continuous_architecture_phase2.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-02-hard-fallback-execution-kill-gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-03-runtime-candidate-outcome-tracker.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-04-cost-slippage-truth-model.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-05-strategy-regime-expectancy-aggregator.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-06-setup-fingerprint-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-07-kill-keep-strategy-gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-08-expectancy-based-ranking-engine.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-09-top-opportunity-selector.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-10-buy-sell-direction-outcome-support.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-11-shadow-market-validation-runner.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-12-edge-readiness-report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-next-01-score-separation-audit-fix.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-next-02-regime-aware-ranking-weights.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-next-03-candidate-pool-quality-gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-next-04-strategy-baseline-comparison.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-next-05-offline-replay-topn-quality-test.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge-next-06-bearish-range-no-trade-coverage-hardening.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_38_runtime_evidence_capture_guard.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_41_fallback_execution_firewall.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_42_quote_truth_single_source.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_43_feed_health_split_brain_fix.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_44_feed_recovery_runtime_wiring.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_45_symbol_level_execution_safety_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_46_soft_reject_separation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_47_candidate_status_contract_cleanup.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_48_scoring_truth_hardening.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_49_opportunity_selector_evidence_upgrade.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_50_latest_artifact_freshness_guard.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_51_latest_artifact_freshness_runtime_wiring.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_52_dashboard_freshness_visibility.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_53_streamlit_freshness_panel_rendering.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_54_home_page_freshness_panel_placement.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_55_tiny_runtime_home_freshness_panel_call.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_56_home_freshness_failure_visibility.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_57_fallback_advisory_only_entry_contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_58_top_opportunity_executable_truth.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_59_top_opportunity_truth_reader_wiring.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_60_buy_pe_ce_directional_bias_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_61_capital_selection_policy_contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_62_roadmap_reconciliation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_63_market_state_model.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_64_regime_state_machine.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_65_strategy_spec_registry.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_66_strategy_quality_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_67_strategy_hypothesis_contracts.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_68_replace_hardcoded_strategy_eligibility.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_69_strategy_registry_candidate_pool.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_70_candidate_normalization_dedup.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_71_candidate_classification_layer.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_72_hard_downgrade_engine.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/edge_73_candidate_readiness_summary.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/elite-backtester-20260613.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/enable_monitor_run_loop.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feat-audit-only-live-supervisor.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed-stab-02-feed-supervisor-state-machine.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed-stab-03-reconnect-quarantine.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed-stab-04-feed-readiness-for-candidates-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed-stab-06-subscription-truth-resubscribe-verification.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed-stab-07-feed-event-journal.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed-stab-08-feed-soak-runner.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed-truth-consistency-evidence-cleanup.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed-zombie-lifecycle-pr555.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed_100k_descriptor_control_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed_20k_descriptor_control_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed_async_descriptor_control_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed_async_persistence_pressure_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed_descriptor_control_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed_integrity_and_health_duration.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/feed_websocket_reconnect_resubscription_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/fix-ws-recovery-reactor-not-restartable-thread-storm.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/fix-ws1006-reactor-fatal-simulation-tests.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/fix_htf_safety_integration_and_fail_closed.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/fresh-feedtruth-audit-proof-pack.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/grid-search-atr-20260613.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/intelligence-layer-architecture-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/live-feedtruth-audit-harness.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/live-rca-auth-tightening.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/offline-feed-candidate-truth-proof-pack.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pairs-trading-live-engine-20260614.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr-612-outcome-evidence-engine.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr-edge-01-runtime-candidate-journal.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr199_observability_architecture.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr2-regime-canonicalization.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr246_advisory_entry_source_normalization.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr247_advisory_schema_boundary_normalization.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr277_test_isolation_decay_input.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr278_trade_builder_candidate_breadth_expiry.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr279_instance_lock_subprocess_readiness.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr3-canonical-regime-score-separation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr4-selector-fallback-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr527-candidate-lifecycle-snapshot.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr528-phase2-boundary-cleanup.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr529-regime-aware-dynamic-scoring-profiles.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr530-regime-profile-opportunity-scoring-opt-in.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr531-ranking-profile-metadata-propagation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr532-advanced-score-delta-evidence.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr585-candidate-flow-diagnostics.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr635_canonical_ranked_runtime_bridge.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr636_ranking_proof_pack_truth.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr637_dirty_option_bridge_ranking.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr639_audit_strategy_structural.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr640_audit_regime_evidence.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr641_feed_execution_truth_minimal.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr647_backtest_trust_integration.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr73_opportunity_score_v1.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_10_certification_persistence.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_11_live_drift_persistence.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_4_statistical_validation_engine.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_595_ml_overlay.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_607_agent_review.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_610_agent_review.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_candidate_outcome_calibration.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_edge_roadmap_bug_solution_docs.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_01_feed_architecture_audit_and_contract_lock.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_02r_canonical_feed_health_reconciliation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_03_feed_hold_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_04_feed_recovery_warmup_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_05_exact_option_token_freshness_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_12_runtime_snapshot_feed_decision.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_13_candidate_pipeline_feed_hold.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_13a_review_queue_non_blocking_quote_lookup.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_14_ranking_suppression_for_feed_risky_candidates.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_15_live_paper_feed_policy_separation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_16_feed_config_hardening.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_20_feed_runtime_evidence_bundle.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_feed_20r_feed_fault_replay_tests.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_institutional_paper_trading.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_ml_acceptance_gate.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_01_observability_identity.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_02_decision_event_schema.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_03_structured_json_logging_adapter.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_04_runtime_cycle_event_emitter_shell.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_05_candidate_lifecycle_events.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_06_feed_state_events.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_07_tracing.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_08_metrics.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_09_local_observability_stack.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_10_grafana_dashboard_provisioning.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_11_loki_log_correlation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_12_observability_evidence_bundle.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_13_safety_invariant_tests.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_14_trace_replay_cli.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_obs_15a_legacy_evidence_import.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/pr_wfa_gate_revisit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/profit-filters-20260613.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/provenance_safe_resumable_strategy_edge_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/qa-edge-first-behavior-strategy.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/qa-eight-year-backtest-strategy-edge.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/qa_full_implemented_strategy_truth_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/rag_00_review.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/ram_next_isolated_work_pr648.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/ram_replay_context_proof.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/real-candidate-supply-contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/real-option-data-backtest-runner-20260614.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/regime_entropy_truth_contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/research_add_htf_cost_adjusted_edge_retest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/runtime_boot_01_token_artifact_scan_cache.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/strict-research-boundaries-enforcement-20260614.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/tick_driven_replay_migration.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/trade-quality-truth-audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/agent_reviews/vectorized-signals-20260613.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/audits/profitable_edge_gap_audit_20260629.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/audits/strategy_contract_and_edge_readiness_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/ariadne/MAPPING_RULES.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/daedalus/CHANGE_RULES.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/finding_normalization/DEDUPLICATION_RULES.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/finding_normalization/NORMALIZED_FINDING_SCHEMA.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/code_excellence/finding_normalization/SEVERITY_SOURCE_MAPPING.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/intelligence/ARCHITECTURE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/intelligence/INTELLIGENCE_LAYER_BIBLE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/intelligence/ROADMAP.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/01_repository_reverse_engineering.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/09_tradebot_integration_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip/11_test_report.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_excellence/02_end_to_end_validation.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/mip_excellence/07_security_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/observability/EVENT_SCHEMA.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/observability/OBSERVABILITY_ARCHITECTURE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/observability/TRACE_REPLAY.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/observability/feed_reconnect_rca_20260629.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/qa/TRADEBOT_FEATURE_TEST_MATRIX.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/qa/TRADEBOT_QA_BEHAVIOR_STRATEGY.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/rca/feed-rca-20260610.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/repo_forensics/AGENT_PARAMETER_CALIBRATION.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/repo_forensics/EVIDENCE_AUDIT_TEMPLATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/repo_forensics/SAFETY_BOUNDARY_TEMPLATE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/repo_forensics/TRADEBOT_AUDIT_CHECKLIST.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/repo_forensics/TRADEBOT_PROFILE.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/repo_forensics/reports/baseline_latest.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/final_replay_proof_policy.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_candidate_likely_event_search.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_context_bundle_oos_rerun_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_context_bundle_real_artifact_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_context_bundle_recorder.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_context_contract.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_context_field_roundtrip_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_context_policy_rerun_final_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_context_regenerated_artifact_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_context_remaining_blockers.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/replay_context_source_artifact_gap.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/strategy_backtesting_engine_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/research/strict_option_replay_export_adapter.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/strategy_truth/07_semantic_gap_audit.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/superpowers/plans/2026-05-06-pro-strategy-shadow-wirein.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/superpowers/plans/2026-06-11-eight-year-backtest-strategy-edge.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `docs/superpowers/specs/2026-05-06-pro-strategy-shadow-wirein-design.md` | `PASS` | `no_restricted_boundary_marker_found` |
| `scripts/run_feed_robustness_replay.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_fd_trace.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_feed_robustness_replay_runner.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_htf_real_paper_monitor.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_kite_auth_consistency.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_kite_depth_ws_stability.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_tick_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `tests/test_ws_tick_ingestion_updates_tick_store.py` | `PASS` | `no_restricted_boundary_marker_found` |
| `token_convert.py` | `PASS` | `no_restricted_boundary_marker_found` |

## Evidence Findings

| Path | Verdict | Reason |
|---|---|---|
| `docs/agent_reviews/441-live-truth-30-indicator-readiness-prewarm-gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/442-live-truth-31-pre-market-live-readiness-gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/452-feed-00-canonical-runtime-feed-truth-state-machine.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/454-tb-edge-01-kill-fallback-execution-live.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/458-trace-phase2-candidate-starvation-after-indicators.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/AGENT_ELITE_06_CERBERUS_NON_ACTION_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_01_CODE_EXCELLENCE_ARCHITECTURE_CONTRACT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_02_ARIADNE_RCA_TEMPLATE_CONTRACT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_03_FINDING_NORMALIZATION_CONTRACT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_04_ARIADNE_ROOT_CAUSE_CLUSTERING_ENGINE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_05B_AGENT_PARAMETER_BRIDGE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_05_DAEDALUS_REMEDIATION_TEMPLATE_CONTRACT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_06_REMEDIATION_PLANNER_IMPLEMENTATION.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_07_VULCAN_PRODUCTION_HARDENING_TEMPLATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_08_MINERVA_TEST_REALITY_HARDENING_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_09_CERBERUS_SAFETY_REGRESSION_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_10_EVIDENCE_CONTRACT_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_11_UNIFIED_CE_GATE_RUNNER.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_12_PR_EVIDENCE_PACK_GENERATOR.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_13_CI_WIRING_FOR_CE_GATES.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/CE_14_FIRST_REMEDIATION_PILOT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-01-baseline-audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-02-paper-outcome-journal-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-03-terminal-paper-outcome-wiring.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-04-runtime-terminal-outcome-hook.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-05-execution-router-outcome-hook.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-06-paper-exit-outcome-truth.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-07-setup-hypothesis-identity.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-08-adopt-setup-identity-in-paper-outcomes.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-09-runtime-setup-identity-adoption.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-10-runtime-readiness-failure-snapshot.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-11-runtime-truth-breakdown.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-12-feed-startup-root-cause.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-13-ws-handshake-proof-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-13b-wire-ws-handshake-proof.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-14-status-provenance.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-15-status-freshness-guard.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-26-debug-forensics-cli-path-and-skew-fix.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-26-fast-engine-cycle-boundary-proof.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-27-legacy-cycle-boundary-proof.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-28-main-post-db-boundary-proof.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-29-fast-loop-timer-trigger-before-feed-debug.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-30-deferred-work-ledger.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-31-executable-trade-truth-firebreak.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-32-candidate-quote-freshness-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-33-option-bid-ask-spread-truth-gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-34-execution-first-scoring-reweight.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-35-strategy-signal-quality-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-36-feed-recovery-evidence.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-37-evidence-replay-quality-report.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-39-expired-contract-token-resolution-guard.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE-40-quote-timestamp-age-consistency-guard.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_77_STRATEGY_SPECIFIC_EXIT_MODELS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_78_STRATEGY_PARAMETER_ROBUSTNESS_TESTS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_79_STRATEGY_CONFLICT_CONSENSUS_ENGINE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_80_NO_TRADE_ORACLE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_81_NO_TRADE_EVIDENCE_REVIEW_UI.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_82_FINAL_EXECUTABLE_QUALITY_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_83_PAPER_TRUTH_JOURNAL.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_84_OUTCOME_REDUCER.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_85_STRATEGY_EXPECTANCY_BY_REGIME.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_86_SLIPPAGE_COST_TRUTH.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_87_STRATEGY_FAMILY_KILL_KEEP_REPORT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_88_STRATEGY_LIFECYCLE_STATES.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_89_STRATEGY_PROMOTION_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/EDGE_90_STRATEGY_SUSPENSION_RETIREMENT_RULES.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_01_REPO_FORENSICS_ARCHITECTURE_CONTRACT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_02_TRADEBOT_FORENSICS_PROFILE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_03_REPO_CARTOGRAPHER_SCANNER.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_04_RUNTIME_WIRING_AUDIT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_05_CRITICAL_MODULE_CALLER_CHECK.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_06_TEST_REALITY_CLASSIFIER.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_07_SAFETY_BOUNDARY_AUDITOR.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_08_EVIDENCE_AUDITOR.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_09_ARCHITECTURE_DRIFT_DETECTOR.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_10_UNIFIED_FORENSICS_RUNNER.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_11_3_AGENT_EVIDENCE_INTEGRATION.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_12_FIRST_TRADEBOT_BASELINE_AUDIT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_12_TRADEBOT_BASELINE_AGENT_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_13_FORENSICS_GATE_FOR_FUTURE_PRS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_14_PRODUCT_REALITY_AUDIT_LAYER.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/GSD_FOR_15_CI_REQUIRED_FORENSICS_PR_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/HOTFIX_EDGE_79A_LIVE_INDICATOR_READINESS_DIAGNOSTICS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/HOTFIX_EDGE_79B_MARKET_CLOSE_FEED_STATE_CLASSIFIER.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_01_TOP_OPPORTUNITIES_EXECUTABLE_ALIGNMENT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_02_LATEST_ARTIFACT_NON_EMPTY_PRESERVATION.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_03_RUNTIME_SNAPSHOT_FRESHNESS_GUARD.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_04_FEED_RUNTIME_WRITER_LIVENESS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_05_MARKET_CLOSE_STATE_CONSISTENCY.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_06_STALE_CANDIDATE_HYGIENE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_07_LATENCY_SLO_OSCILLATION.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_08_SENSEX_REJECT_CALIBRATION.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_09_RUNTIME_HEALTH_ARTIFACT_CONSISTENCY.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_10_STRATEGY_PERF_SHADOW_FALLBACK.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_11_INDICATOR_READINESS_DECISION_REJECT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/LIVE_TRUTH_12_LATENCY_HOTPATH_EVIDENCE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR-195-unit-scope-execution-selection-safety.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR-5_strategy_certification.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR-627_edge_proof.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR-6_research_registry.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR-7_live_drift.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR100_LIVE_OBSERVATION_EVIDENCE_HARDENING.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR101_FALLBACK_CONTRACT_EXECUTION_FIREWALL.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR102_CONTRACT_RESOLUTION_FALLBACK_PROPAGATION_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR103_RUNTIME_TRUTH_CONSISTENCY_REGIME_DIAGNOSTICS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR104_FINAL_EMIT_TRUTH_CONTRACT.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR105_BLOCKED_CANDIDATE_LIFECYCLE_SCHEMA_CONSISTENCY.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR90_PAPER_DECISION_CONTRACT_SNAPSHOTS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR91_STRICT_PAPER_ORDER_STATE_MACHINE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR92_REALISTIC_OPTION_FILL_SLIPPAGE_MODEL.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR93_PAPER_RISK_LEDGER.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR94_FULL_SESSION_PAPER_TRADING_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR95_PAPER_SESSION_GATE_CONTRACT_SNAPSHOTS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR95_PAPER_TRADING_RUNBOOK_COMMAND.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR96_LIVE_DRY_RUN_BROKER_PAYLOAD_GATE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR97_BROKER_RECONCILIATION_DRY_RUN_PROOF.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR98_KILL_SWITCH_RISK_HALT_DRY_RUN_PROOF.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR99_LIVE_OBSERVATION_RUNTIME_SAFETY_FLAGS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR_FEED_08_PURE_TICK_UTILITY_HELPERS.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR_FEED_09_RECONNECT_DECISION_POLICY.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR_FEED_10_SUBSCRIPTION_BUDGET_POLICY.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR_FEED_11_RUNTIME_SNAPSHOT_BUILDER.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR_FEED_17_RESOLUTION_READ_MODEL.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR_FEED_18_WS_LIFECYCLE_SHELL.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/PR_FEED_19_CALLBACK_THIN_WIRING.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/UPSTOX_DAILY_CAPTURE.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/agent-command-center-live-sidecar.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/agent-command-center.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/ai_optimization_layer.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/all_strategy_available_data_backtest_20260629.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/backtest-runtime-replay-empty-source-readiness.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/backtest-runtime-replay-readiness-verdict.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/candidate-executability-evidence-pack.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/candidate-outcome-fixture-loader.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/candidate-outcome-report-writer.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/candidate-outcome-truth-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/candidate-supply-zero-attribution.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/command-center-session-scoped-rca.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/continuous_architecture_phase2.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-02-hard-fallback-execution-kill-gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-03-runtime-candidate-outcome-tracker.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-04-cost-slippage-truth-model.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-05-strategy-regime-expectancy-aggregator.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-06-setup-fingerprint-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-07-kill-keep-strategy-gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-08-expectancy-based-ranking-engine.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-09-top-opportunity-selector.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-10-buy-sell-direction-outcome-support.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-11-shadow-market-validation-runner.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-12-edge-readiness-report.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-next-01-score-separation-audit-fix.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-next-02-regime-aware-ranking-weights.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-next-03-candidate-pool-quality-gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-next-04-strategy-baseline-comparison.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-next-05-offline-replay-topn-quality-test.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge-next-06-bearish-range-no-trade-coverage-hardening.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_38_runtime_evidence_capture_guard.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_41_fallback_execution_firewall.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_42_quote_truth_single_source.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_43_feed_health_split_brain_fix.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_44_feed_recovery_runtime_wiring.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_45_symbol_level_execution_safety_gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_46_soft_reject_separation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_47_candidate_status_contract_cleanup.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_48_scoring_truth_hardening.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_49_opportunity_selector_evidence_upgrade.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_50_latest_artifact_freshness_guard.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_51_latest_artifact_freshness_runtime_wiring.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_52_dashboard_freshness_visibility.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_53_streamlit_freshness_panel_rendering.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_54_home_page_freshness_panel_placement.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_55_tiny_runtime_home_freshness_panel_call.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_56_home_freshness_failure_visibility.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_57_fallback_advisory_only_entry_contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_58_top_opportunity_executable_truth.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_59_top_opportunity_truth_reader_wiring.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_60_buy_pe_ce_directional_bias_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_61_capital_selection_policy_contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_62_roadmap_reconciliation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_63_market_state_model.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_64_regime_state_machine.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_65_strategy_spec_registry.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_66_strategy_quality_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_67_strategy_hypothesis_contracts.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_68_replace_hardcoded_strategy_eligibility.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_69_strategy_registry_candidate_pool.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_70_candidate_normalization_dedup.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_71_candidate_classification_layer.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_72_hard_downgrade_engine.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/edge_73_candidate_readiness_summary.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/elite-backtester-20260613.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/enable_monitor_run_loop.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feat-audit-only-live-supervisor.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed-stab-02-feed-supervisor-state-machine.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed-stab-03-reconnect-quarantine.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed-stab-04-feed-readiness-for-candidates-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed-stab-06-subscription-truth-resubscribe-verification.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed-stab-07-feed-event-journal.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed-stab-08-feed-soak-runner.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed-truth-consistency-evidence-cleanup.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed-zombie-lifecycle-pr555.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed_100k_descriptor_control_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed_20k_descriptor_control_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed_async_descriptor_control_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed_async_persistence_pressure_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed_descriptor_control_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed_integrity_and_health_duration.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/feed_websocket_reconnect_resubscription_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/fix-ws-recovery-reactor-not-restartable-thread-storm.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/fix-ws1006-reactor-fatal-simulation-tests.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/fix_htf_safety_integration_and_fail_closed.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/fresh-feedtruth-audit-proof-pack.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/grid-search-atr-20260613.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/intelligence-layer-architecture-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/live-feedtruth-audit-harness.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/live-rca-auth-tightening.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/offline-feed-candidate-truth-proof-pack.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pairs-trading-live-engine-20260614.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr-612-outcome-evidence-engine.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr-edge-01-runtime-candidate-journal.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr199_observability_architecture.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr2-regime-canonicalization.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr246_advisory_entry_source_normalization.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr247_advisory_schema_boundary_normalization.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr277_test_isolation_decay_input.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr278_trade_builder_candidate_breadth_expiry.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr279_instance_lock_subprocess_readiness.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr3-canonical-regime-score-separation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr4-selector-fallback-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr527-candidate-lifecycle-snapshot.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr528-phase2-boundary-cleanup.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr529-regime-aware-dynamic-scoring-profiles.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr530-regime-profile-opportunity-scoring-opt-in.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr531-ranking-profile-metadata-propagation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr532-advanced-score-delta-evidence.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr585-candidate-flow-diagnostics.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr635_canonical_ranked_runtime_bridge.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr636_ranking_proof_pack_truth.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr637_dirty_option_bridge_ranking.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr639_audit_strategy_structural.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr640_audit_regime_evidence.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr641_feed_execution_truth_minimal.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr647_backtest_trust_integration.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr73_opportunity_score_v1.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_10_certification_persistence.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_11_live_drift_persistence.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_4_statistical_validation_engine.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_595_ml_overlay.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_607_agent_review.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_610_agent_review.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_candidate_outcome_calibration.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_edge_roadmap_bug_solution_docs.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_01_feed_architecture_audit_and_contract_lock.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_02r_canonical_feed_health_reconciliation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_03_feed_hold_gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_04_feed_recovery_warmup_gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_05_exact_option_token_freshness_gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_12_runtime_snapshot_feed_decision.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_13_candidate_pipeline_feed_hold.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_13a_review_queue_non_blocking_quote_lookup.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_14_ranking_suppression_for_feed_risky_candidates.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_15_live_paper_feed_policy_separation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_16_feed_config_hardening.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_20_feed_runtime_evidence_bundle.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_feed_20r_feed_fault_replay_tests.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_institutional_paper_trading.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_ml_acceptance_gate.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_01_observability_identity.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_02_decision_event_schema.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_03_structured_json_logging_adapter.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_04_runtime_cycle_event_emitter_shell.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_05_candidate_lifecycle_events.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_06_feed_state_events.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_07_tracing.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_08_metrics.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_09_local_observability_stack.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_10_grafana_dashboard_provisioning.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_11_loki_log_correlation.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_12_observability_evidence_bundle.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_13_safety_invariant_tests.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_14_trace_replay_cli.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_obs_15a_legacy_evidence_import.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/pr_wfa_gate_revisit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/profit-filters-20260613.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/provenance_safe_resumable_strategy_edge_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/qa-edge-first-behavior-strategy.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/qa-eight-year-backtest-strategy-edge.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/qa_full_implemented_strategy_truth_audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/rag_00_review.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/ram_next_isolated_work_pr648.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/ram_replay_context_proof.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/real-candidate-supply-contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/real-option-data-backtest-runner-20260614.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/regime_entropy_truth_contract.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/research_add_htf_cost_adjusted_edge_retest.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/runtime_boot_01_token_artifact_scan_cache.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/strict-research-boundaries-enforcement-20260614.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/tick_driven_replay_migration.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/trade-quality-truth-audit.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/agent_reviews/vectorized-signals-20260613.md` | `PASS` | `evidence_contract_satisfied` |
| `docs/repo_forensics/reports/baseline_latest.md` | `PASS` | `evidence_contract_satisfied` |
