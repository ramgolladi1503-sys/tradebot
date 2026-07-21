# ML Strategy Discovery Real-Run Audit v1

mode: ML_STRATEGY_DISCOVERY_REAL_RUN_AUDIT_V1
candidate_id: tree_rule_edb855245d2f, tree_rule_7a6855962eee
decision: BOTH_CANDIDATES_UNSTABLE
reason: Independent source/provenance, causality, rule-reproduction, fold, concentration, control, and holdout-isolation checks completed. LONG shows positive validation expectancy but fails concentration because the largest fold contributes 55.56% of validation total R and top five trades contribute 111.11% of positive validation contribution. SHORT fails validation support and expectancy with one validation session, 20.00% trade-bearing folds, and -0.600000 label expectancy R.
timestamp: 2026-07-21T14:16:52+00:00
source: /Users/madhuram/tradebot-ml-evidence/audit-v1
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
append: false

## Claim Boundary

All reported values are underlying research-label metrics. They are not executable metrics, broker fills, option P&L, live readiness, or structural edge proof.

NO_STRUCTURAL_EDGE_OR_OPTION_PROFITABILITY_PROVEN.

## Agent Work Contract

source_agent: Codex
action: GENERATE_PATCH
title: Replace placeholder PR #687 audit with independent real-run audit
scope: `scripts/audit_ml_strategy_discovery_real_run.py`, `tests/test_ml_strategy_discovery_real_run_audit.py`, and this evidence document only.
requested_paths: `scripts/audit_ml_strategy_discovery_real_run.py`; `tests/test_ml_strategy_discovery_real_run_audit.py`; `docs/agent_reviews/ml_strategy_discovery_real_run_audit_v1.md`
allowed_paths: same as requested paths, plus generated read-only artifacts under `/Users/madhuram/tradebot-ml-evidence/audit-v1`
forbidden_paths: production strategy code, broker/execution/order/risk/feed/ranking/dashboard code, production ML code, configuration, credentials, source parquet files, and PR #686 implementation files
expected_tests: compile audit script and tests; run discovery core/source tests; run audit tests; regenerate audit artifacts
acceptance_proof: exact commands and results are listed below; local upstream discovery-core pytest slice is blocked by missing `libomp.dylib` for xgboost on this machine

## Scope Guard

No production strategy, broker, execution, order, risk, feed, ranking, dashboard, production ML, configuration, credential, source parquet, or PR #686 implementation files were modified. The audit is offline and read-only.

## Grill Me Review

Risk review result: the previous placeholder audit must not be used. The replacement computes inputs before verdict selection, rejects holdout access in metric/control functions, emits structured error codes, and records exact hashes/counts. Remaining risk: this is still an offline research-label audit and does not prove a tradable edge.

## Hermes Review

Architecture review result: audit behavior is isolated in importable pure functions plus a CLI. Ordered gates cover input validity, source provenance, causality/leakage, rule reproduction, support, base-rate lift, folds, concentration, controls, and holdout isolation. Generated outputs carry schema version, deterministic seed, code SHA, input hashes, status, reasons, and safety fields.

## GSD Review

Implementation review result: placeholder phases, placeholder output objects, pass-only tests, and hard-coded final verdict behavior were removed. The verdict is computed from audit results after the real artifact calculations complete.

## QA / Safety Review

Every generated JSON envelope records the same read-only audit safety contract as the scalar fields at the top of this document. Tests exercise missing/empty/malformed inputs, sidecar mismatch, source mismatch, path escape, source mutation, causality failures, forbidden future-label features, rule/imputation/support mismatch, holdout metric rejection, deterministic folds/concentration/controls, interaction counts, and verdict variation.

## Acceptance Proof

- `python3 -m compileall -q scripts/audit_ml_strategy_discovery_real_run.py tests/test_ml_strategy_discovery_real_run_audit.py`: passed.
- `PYTHONPATH=. python3 -m pytest -q tests/test_ml_strategy_discovery_real_run_audit.py`: 27 passed.
- `PYTHONPATH=. python3 scripts/audit_ml_strategy_discovery_real_run.py ...`: completed and wrote final verdict `BOTH_CANDIDATES_UNSTABLE`.
- `git diff --check`: passed.
- `PYTHONPATH=. python3 -m pytest -q tests/test_ml_strategy_discovery_core.py tests/test_ml_strategy_discovery_upstox_source.py tests/test_ml_strategy_discovery_real_run_audit.py`: 41 passed, 1 failed due to missing local `libomp.dylib` required by xgboost, not due to the audit code.

## Runtime Proof Required After Merge

None. This PR must not create runtime behavior. Any future runtime use of these research candidates would require a separate human-approved PR with paper/live safety gates, broker boundary proof, slippage/spread validation, and no holdout leakage.

## What This PR Does Not Prove

This PR does not prove structural edge, option profitability, live readiness, broker execution quality, production arbitration, slippage tolerance, spread robustness, or risk-gate acceptance.

## Human Approval

No live behavior is enabled. No broker API call is made. No order action is possible from this audit. Human approval remains required before any runtime or production strategy integration.

## Input Hashes

- certified manifest: `/Users/madhuram/tradebot-ml-evidence/certified-source/opening_range_retest_causal_replay_source_manifest_v2.json` sha256 `3390fad00ae40f0ab77eb05386fb8e04af3127081843dba63b8a3af050b40926`
- certified sidecar: `/Users/madhuram/tradebot-ml-evidence/certified-source/opening_range_retest_causal_replay_source_manifest_v2.json.sha256` sha256 `ae5a035a0bf824ec25e0e08a5fc5298c522031e0695a32fef36356b7e725402f`
- LONG candidates: `/Users/madhuram/tradebot-ml-evidence/nifty-long/candidates.json` sha256 `374ca9dcf1951c383a619efb4b45525c7be53441010561ccba33496840064f61`
- LONG dataset: `/Users/madhuram/tradebot-ml-evidence/nifty-long/discovery_dataset.parquet` sha256 `996f138c54c022a9a5481a4d2d04ffd3e13ade28529646f313eca6406c9fa13e`
- LONG evidence manifest: `/Users/madhuram/tradebot-ml-evidence/nifty-long/evidence_manifest.json` sha256 `92e5ed3bc596d85bce530b1c3bc4e71cceb78e46ad0b82156966fcc16433f508`
- LONG source adapter: `/Users/madhuram/tradebot-ml-evidence/nifty-long/source_adapter_manifest.json` sha256 `01a09748054f28f14f9810ee622118726468cef53195cf1ce296534188ee93e6`
- SHORT candidates: `/Users/madhuram/tradebot-ml-evidence/nifty-short/candidates.json` sha256 `e0e2f837acaf207716af80fbf57321c5b07cac29902b94f599f7acfc60660caf`
- SHORT dataset: `/Users/madhuram/tradebot-ml-evidence/nifty-short/discovery_dataset.parquet` sha256 `0a45dbd2733d23f65c49ffaf88574bcf0108054acf97976f03983b230b465ceb`
- SHORT evidence manifest: `/Users/madhuram/tradebot-ml-evidence/nifty-short/evidence_manifest.json` sha256 `b5536fdda700ac0b121e57f8bdc9a6b05d378a11414c53c36732bd42db48ba6f`
- SHORT source adapter: `/Users/madhuram/tradebot-ml-evidence/nifty-short/source_adapter_manifest.json` sha256 `01a09748054f28f14f9810ee622118726468cef53195cf1ce296534188ee93e6`

## Source Reconciliation

- certified records: 1512
- selected NIFTY records: 510
- LONG adapter records: 510
- SHORT adapter records: 510
- reopened source rows per side: 191250
- LONG dataset rows: 175888; sessions: 510; split rows: DEVELOPMENT 105508, VALIDATION 35190, HOLDOUT_LOCKED 35190
- SHORT dataset rows: 175888; sessions: 510; split rows: DEVELOPMENT 105508, VALIDATION 35190, HOLDOUT_LOCKED 35190

Every selected source path was checked under `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`; hashes, row counts, one-minute cadence, required columns, and selected source IDs reconciled.

## Rule Oracle

- LONG `tree_rule_edb855245d2f`: independent rule oracle reproduced 53 development rows across 22 sessions; all-support rows 97; support rate 0.0005514873101064313.
- SHORT `tree_rule_7a6855962eee`: independent rule oracle reproduced 59 development rows across 6 sessions; all-support rows 44; support rate 0.00025015976189245315.
- package helper masks were not used as the primary oracle.

## Candidate Metrics

LONG development: rows 53; sessions 22; win rate 0.7924528301886793; expectancy R 0.8264150943396229; label PF 7.6363636363636385; total R 43.80000000000001.

LONG validation: rows 21; sessions 12; win rate 0.47619047619047616; expectancy R 0.25714285714285723; label PF 1.8181818181818183; total R 5.400000000000001; max drawdown R -1.7999999999999998; same-side base validation expectancy R 0.022393406822013226; lift 0.234749450320844.

SHORT development: rows 59; sessions 6; win rate 0.7627118644067796; expectancy R 0.7728813559322035; label PF 6.4285714285714315; total R 45.60000000000001.

SHORT validation: rows 8; sessions 1; win rate 0.0; expectancy R -0.6; label PF 0.0; total R -4.8; max drawdown R -4.2; same-side base validation expectancy R 0.017608335416697048; lift -0.617608335416697.

## Fold Screen

FROZEN_RULE_VALIDATION_FOLD_SCREEN:

- LONG: trade-bearing folds 100.00%; positive-expectancy folds 80.00%; positive-total-R folds 80.00%; median expectancy 0.42857142857142855; best fold total R 3.0; worst fold total R -1.7999999999999998; largest fold contribution 0.5555555555555555.
- SHORT: trade-bearing folds 20.00%; positive-expectancy folds 0.00%; positive-total-R folds 0.00%; median expectancy -0.6; best fold total R 0.0; worst fold total R -4.8; largest fold contribution -0.0.

## Concentration And Controls

- LONG session bootstrap seed 68742: expectancy CI [-0.10909090909090909, 0.72], win-rate CI [0.2727272727272727, 0.7333333333333333], label-PF CI [0.75, 5.499999999999999].
- LONG concentration: top five trade contribution 1.111111111111111; best 5% trade contribution 0.2; longest losing sequence 3.
- SHORT session bootstrap seed 68742: expectancy CI [-0.6, -0.6], win-rate CI [0.0, 0.0], label-PF CI [0.0, 0.0].
- SHORT concentration: top five trade contribution 0.625; best 5% trade contribution undefined because validation positive contribution is zero; longest losing sequence 8.
- Controls generated for DEVELOPMENT and VALIDATION only: deterministic label permutation, session-aware label permutation, timestamp shift, delayed features, placebo decision times, reversed-direction comparison, every-condition ablation, strongest-condition removal, threshold perturbations at -20%, -10%, -5%, +5%, +10%, +20%, leave-one-year-out, leave-one-regime-out, one-additional-bar latency proxy, and abstract label-cost stress.

## LONG/SHORT Interaction

- overlapping decision timestamps: 0
- opposite-side simultaneous signals: 0
- same-session overlap: 2
- shared feature names: `distance_from_opening_high_atr`
- rule-state similarity: 0.16666666666666666
- combined signal frequency: 141
- conflict count: 0

## Holdout Proof

- isolation status: HOLDOUT_OUTCOMES_NOT_CONSUMED_BY_METRIC_OR_CONTROL_FUNCTIONS
- LONG holdout rows: 35190
- LONG holdout sessions: 102
- SHORT holdout rows: 35190
- SHORT holdout sessions: 102
- acknowledgement token imported: false
- holdout performance metrics emitted: false

Metric and control functions reject any dataframe containing `HOLDOUT_LOCKED`.

## Generated Artifacts

- `/Users/madhuram/tradebot-ml-evidence/audit-v1/input_inventory.json`
- `/Users/madhuram/tradebot-ml-evidence/audit-v1/long_candidate_audit.json`
- `/Users/madhuram/tradebot-ml-evidence/audit-v1/short_candidate_audit.json`
- `/Users/madhuram/tradebot-ml-evidence/audit-v1/candidate_comparison.json`
- `/Users/madhuram/tradebot-ml-evidence/audit-v1/holdout_non_consumption.json`
- `/Users/madhuram/tradebot-ml-evidence/audit-v1/final_report.md`
- `/Users/madhuram/tradebot-ml-evidence/audit-v1/audit.log`

Invalid placeholder output inventory preserved at `/Users/madhuram/tradebot-ml-evidence/audit-v1-invalid-inventory.json`.

## Limitations

This audit is offline and read-only. It does not validate broker execution, slippage, spread, option-chain availability, production arbitration, or live-market readiness. The verdict is computed from the current artifacts only and must be rerun if any input hash changes.
