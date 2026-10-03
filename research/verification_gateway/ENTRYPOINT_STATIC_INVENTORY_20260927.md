# Static research-entrypoint and outcome-access candidate inventory — 2026-09-27

```text
source_agent: gsd
action: MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
read_only=true
append=false
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
```

This is a static filename/content scan from PR #936 commit `043577edd4b2c79c763690a64bbc6cfdf1cb7a0f`. No listed script was run and no outcome, ledger, quote, canonical dataset, credential, or runtime file was opened. Search terms locate candidates; they do not prove that each file is an official research entrypoint, nor that the list is complete.

## Search results

- `scripts/research/` files containing `__main__`: 5 (5 paths).
- `scripts/` files containing one or more of `OutcomeReplay`, `outcome_replay`, `ResearchStore`, `core.analytics.store`, `append_outcome`, `protected.*outcome`, `ledger`: 46 paths.
- `scripts/` files containing `__main__`: 461. This includes non-research commands; it is not an estimate of official research routes.
- Direct textual references to `ResearchPipeline`, `core.research_pipeline`, `run_research_stage`, or `core.analytics.outcome_replay/store` occur in four scanned source files (plus related definitions). This low count does not establish complete call-graph coverage.

## Research-directory command candidates

- `scripts/research/audit_option_depth_feasibility.py`
- `scripts/research/option_e2e_census_build.py`
- `scripts/research/option_e2e_census_v4_1_build.py`
- `scripts/research/reprice_contract_level_all_epochs.py`
- `scripts/research/verify_independent_schedule_regeneration.py`

## Outcome/ledger/API reference candidates requiring classification

- `scripts/activate_model.py`
- `scripts/analyze_mean_reversion_failure.py`
- `scripts/analyze_phase4_9_cohort_edge.py`
- `scripts/audit_mean_reversion_trade_ledger.py`
- `scripts/audit_opening_drive_structural.py`
- `scripts/audit_opening_range_retest_causal_replay.py`
- `scripts/audit_opening_range_retest_outcomes_v2.py`
- `scripts/audit_phase4_10_accounting.py`
- `scripts/audit_phase4_7_integrity.py`
- `scripts/audit_phase4_8_selection_quality.py`
- `scripts/audit_phase4_truth.py`
- `scripts/audit_phase4_v2_structural.py`
- `scripts/audit_pipeline_contract.py`
- `scripts/generate_mean_reversion_trade_ledger.py`
- `scripts/generate_observability_certification.py`
- `scripts/generate_opening_drive_trade_ledger.py`
- `scripts/generate_opening_range_retest_causal_replay.py`
- `scripts/generate_opening_range_retest_outcomes_v2.py`
- `scripts/generate_pipeline_health_report.py`
- `scripts/paper_trading_runbook.py`
- `scripts/pr905_mutation_v2.py`
- `scripts/pr905_verifier_v2.py`
- `scripts/register_model.py`
- `scripts/replay_blocker_outcomes.py`
- `scripts/reproduce_market_event_graph_reversal_v1.py`
- `scripts/research/reprice_contract_level_all_epochs.py`
- `scripts/run_ai_certification_research_manager.py`
- `scripts/run_candidate_ml_historical_options.py`
- `scripts/run_candidate_ml_replay_ledger.py`
- `scripts/run_governed_strategy_research.py`
- `scripts/run_level_c_causal_replay.py`
- `scripts/run_market_story_engine_v1.py`
- `scripts/run_mean_reversion_parameter_discovery.py`
- `scripts/run_mros_trace_pipeline_v3_runner.py`
- `scripts/run_mros_trace_pipeline_v4_runner.py`
- `scripts/run_mros_trace_pipeline_v6_runner.py`
- `scripts/run_opening_drive_parameter_discovery.py`
- `scripts/run_opening_range_retest_phase1_v2_recertification.py`
- `scripts/run_trade_truth_prospective_observer.py`
- `scripts/run_trade_truth_prospective_verifier_mutations_v5.py`
- `scripts/run_trade_truth_prospective_verifier_mutations_v6.py`
- `scripts/status_feed_forensics.py`
- `scripts/validate_mean_reversion_vertical_slice.py`
- `scripts/verify_mros_runtime_call_path.py`
- `scripts/verify_trade_truth_prospective_level_c.py`

## Confirmed architecture observations from source only

- `scripts/run_strategy_pipeline_research.py` calls `run_research_stage()` with a governed run directory and writes a stage result. It is a normal research stage command; it is not yet routed through `research.verification_gateway`.
- `scripts/run_governed_strategy_research.py` exposes `init`, `freeze`, `packet`, evidence-recording, `approve-paper`, and `status` commands through `GovernedResearchStore`. This is a separate control plane and is not yet composed with the verification gateway.
- `core/analytics/walk_forward_pipeline.py` reads JSONL files from `runtime/analytics/outcomes` directly. This is a direct data-path route that a Python-only gateway would not constrain. The file was inspected, but the directory/data were not read.
- `core/auto_retrain.py` calls `ResearchPipeline.run()` on a cooldown. `_monte_carlo()` output is added to its report payload but `_overfit_alarms()` does not consume the `mc` argument. The local Monte Carlo repair therefore changes only its diagnostic distribution output; it does not change the current alarm branch based on Sharpe, expectancy, tail loss, or walk-forward expectancy.
- Other potential CLI routes and library calls require a complete AST/import/call graph and human ownership review. Existing direct filesystem reads mean an API adapter alone is insufficient.

## H gate verdict

`BLOCKED`: all normal official research entrypoints have not been authoritatively enumerated, no single gateway controls them, and direct filesystem access is not OS-restricted. The next safe step is an owner-reviewed source inventory and OS-level read-path policy, followed by a separately contracted integration that routes every authorized research entrypoint through independently generated evidence. Do not run candidates to classify them; use source review and synthetic fixtures.

Reproduction commands (static searches only):

```sh
rg -l '__main__' scripts/research --glob '*.py' | sort
rg -l 'OutcomeReplay|outcome_replay|ResearchStore|core.analytics.store|append_outcome|protected.*outcome|ledger' scripts --glob '*.py' | sort
rg -n 'run_research_stage|ResearchPipeline\(|core\.research_pipeline|from core\.analytics\.outcome_replay|core\.analytics\.store' scripts core --glob '*.py'
```
