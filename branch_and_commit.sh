#!/bin/bash
set -e

# Save current branch
MAIN_BRANCH=$(git branch --show-current)

# 1. Pipeline Contract Verification
git checkout -b audit-pipeline-contracts
git add core/pipeline_contracts.py scripts/audit_pipeline_contract.py scripts/generate_pipeline_health_report.py tests/test_pipeline_contracts.py
git add runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_contract_audit.* runtime/strategy_validation/MEAN_REVERSION_EXTENSION/pipeline_health_report.* runtime/strategy_validation/MEAN_REVERSION_EXTENSION/lineage_audit.* || true
git commit -m "test(pipeline): Add pipeline contract verification gates and tests" || true
git checkout $MAIN_BRANCH

# 2. Strategy Structural Audits
git checkout -b audit-strategy-structural
git add scripts/audit_opening_drive_structural.py scripts/generate_mean_reversion_trade_ledger.py scripts/generate_opening_drive_trade_ledger.py scripts/run_opening_drive_parameter_discovery.py scripts/run_offline_feed_candidate_truth_proof_pack.py scripts/replay_blocker_outcomes.py scripts/resolve_upstox_instrument_keys.py
git add runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_* runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_* runtime/strategy_validation/MEAN_REVERSION_EXTENSION/blocker_* runtime/strategy_validation/MEAN_REVERSION_EXTENSION/missing_* runtime/strategy_validation/MEAN_REVERSION_EXTENSION/ranking_* || true
git add runtime/strategy_validation/OPENING_DRIVE/ || true
git commit -m "test(strategy): Implement structural audits for Opening Drive and Mean Reversion" || true
git checkout $MAIN_BRANCH

# 3. Evidence-based Regime Audit
git checkout -b audit-regime-evidence
git add core/market_context.py core/regime_monitor.py scripts/audit_regime_strategy_switching.py scripts/generate_regime_timeline_from_replay.py scripts/reference_regime_classifier.py scripts/inventory_regime_audit_data.py tests/test_audit_independence.py
git add runtime/strategy_validation/regime_* runtime/strategy_validation/real_regime_audit_report.md || true
git add scripts/inventory_market_data.py scripts/fetch_option_replay_paths.py || true
git commit -m "test(regime): Implement strict evidence-based regime audit harness

- Replaces tautological regime matching with SQL-style timestamp join
- Adds independent OHLC reference classifier
- Injects non-mutating market_timestamp telemetry into core monitors
- Adds 4 negative-control tests to enforce audit integrity" || true
git checkout $MAIN_BRANCH

echo "Done organizing branches!"
