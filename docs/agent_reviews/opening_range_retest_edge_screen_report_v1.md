# ORB Structural-Edge Screen v1

- mode: ORB_EDGE_SCREEN_REPORT_V1
- candidate_id: ALL_ORB_OUTCOME_V2_CANDIDATES
- decision: ORB_NO_STRUCTURAL_EDGE
- reason: applied frozen structural and conditional verdict gates to recomputed evidence
- timestamp: 2026-07-20T00:00:00Z
- source: opening_range_retest_outcome_ledger_v2.json
- is_order_action: false
- broker_api_called: false
- verdict: ORB_NO_STRUCTURAL_EDGE
- primary_horizon_minutes: 15
- primary_candidate_count: 2155
- primary_session_equal_mean_bps: -0.064401
- primary_ci_bps: [-0.927855, 0.796142]
- matched_time_coverage: 1.000000
- random_direction_p: 0.591409
- within_stratum_p: 0.534466

This is pre-cost underlying-only research evidence. It is not option PnL, not profitability proof, and not paper/live readiness.

## Failed Structural Gates
- primary_15m_session_equal_mean_gt_0
- mean_ge_1bp
- lower_ci_gt_0
- sign_test_one_sided_lte_0_05
- random_advantage_lower_ci_gt_0
- random_permutation_p_lte_0_05
- matched_time_advantage_lower_ci_gt_0
- within_stratum_p_lte_0_05
- at_least_2_of_3_years_positive
- at_least_2_of_3_symbols_positive
- positive_after_five_most_positive_sessions_removed
- positive_after_most_positive_year_removed
- positive_after_most_positive_symbol_removed
- positive_after_most_positive_symbol_direction_removed
- positive_after_winsorized_session_means
- overlap_one_per_component_positive
- overlap_earliest_symbol_session_positive

STOP ORB RESEARCH
FREEZE ACCEPTED IMPLEMENTATION
DO NOT TUNE ORB
SELECT NEXT STRATEGY HYPOTHESIS

## Agent Work Contract
- source_agent: Codex
- action: GENERATE_PATCH
- scope: offline ORB structural-edge screen over certified outcome ledger only
- allowed_paths: research/opening_range_retest_edge_screen_v1, scripts/*edge_screen_v1.py, tests/*edge_screen*, docs/agent_reviews/opening_range_retest_edge_screen_*_v1*
- forbidden_paths: production strategy, core, config, broker, risk, feed, dashboard, runtime source data, Phase 1 v2 artifacts, Outcome v2 artifacts, PR #674

## Scope Guard
- production files touched: none
- source data copied: none
- source symlinks created: none
- ORB tuning performed: none

## Grill Me Review
- Verdict is constrained by failed structural gates; no profitability, option PnL, WFA, paper, or live readiness claim is made.

## Hermes Review
- The workflow separates contract freeze, implementation freeze, deterministic evidence generation, and independent oracle audit.

## GSD Review
- Implementation stays inside the approved research, script, test, and evidence paths.

## QA / Safety Review
- Evidence is read-only, append=false, is_order_action=false, broker_api_called=false, and allowed_for_live_execution=false.

## Acceptance Proof
- Contract, metrics, controls, concentration, replication, overlap, verdict, audit, and report artifacts have SHA-256 sidecars.
- Independent oracle verdict required: ORB_EDGE_SCREEN_AUDIT_CERTIFIED.

## Runtime Proof Required After Merge
- None. This PR is offline research evidence only and is not production integration.

## What This PR Does Not Prove
- It does not prove option profitability, transaction-cost survivability, WFA stability, paper readiness, live readiness, or production promotion.

## Human Approval
- Required before any WFA follow-up or next strategy-hypothesis selection work.
