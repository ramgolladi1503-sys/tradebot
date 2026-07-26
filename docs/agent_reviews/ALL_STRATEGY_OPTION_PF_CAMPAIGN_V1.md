mode: RESEARCH_ONLY_ALL_STRATEGY_OPTION_PF_CAMPAIGN
candidate_id: all_strategy_option_pf_campaign_v1
decision: NO_VALIDATED_PROFITABLE_STRATEGY_FOUND
reason: Mac-local CE/PE option history contains only two usable option sessions under the approved evidence sources, below the frozen minimum of three sessions for PF analysis; all 12 canonical strategies and 11 frozen hypotheses are therefore completed as DATA_BLOCKED rows
timestamp: 2026-07-26T21:30:00+05:30
research_only: true
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
outcomes_read: false
pnl_read: false
holdout_outcomes_read: false
source: research/option_e2e_recertification_v4/all_strategy_option_pf_campaign_v1/evidence/manifest.json

# Agent Work Contract

- source_agent: Codex
- action: GENERATE_PATCH
- title: Run Mac-local CE/PE strategy profit-factor campaign
- scope: isolated worktree, metadata-first source inventory, chronological partition gate, one-command runner, complete blocked analytics rows, compact evidence, and tests
- allowed_paths: scripts/run_mac_all_strategy_option_pf_campaign.py, research/option_e2e_recertification_v4/all_strategy_option_pf_campaign_v1, tests/research/option_e2e, docs/agent_reviews
- forbidden_paths: PR #717, strategy thresholds, broker, orders, feed, risk, dashboard, live/paper config, paid data acquisition, holdout opening, Git/LFS history
- acceptance_proof: runner generated all required strategy/hypothesis rows and stopped before strategy execution because usable sessions were below the frozen minimum

# Scope Guard

This campaign did not execute strategies, inspect outcome/P&L/holdout artifacts, call broker APIs, modify orders, or touch live/paper configuration. The stop happened at the chronological partition gate before PF analysis because the usable option-session count is below the frozen threshold.

# Data Inventory

The runner inspected approved roots passed by CLI and wrote metadata-first inventory artifacts outside Git under `/Users/madhuram/tradebot-ml-evidence/all-strategy-option-pf-v1`. Denied outcome/P&L paths are metadata-only. Malformed parquet candidates are rejected rather than fatal.

# Usable Session Coverage

Valid option sessions are:

- `2026-07-09` from tracked replay archive compact evidence;
- `2026-07-14` from PR #717 Upstox CE/PE raw tick and normalized smoke evidence.

Chronological coverage verdict: `DATA_BLOCKED_FOR_PF_ANALYSIS`.

# Partition Manifest

The frozen policy says fewer than three usable sessions is data-blocked for PF analysis. Development, validation and holdout partitions are empty. Holdout remains sealed.

# Strategy Results

All 12 canonical strategies are present and marked `DATA_BLOCKED`: `COMPRESSION_BREAKOUT`, `EVENT_VOLATILITY_EXPANSION`, `EXHAUSTION_REVERSAL`, `FAILED_BREAKOUT_TRAP`, `LATE_DAY_MOMENTUM`, `MEAN_REVERSION_EXTENSION`, `OPENING_DRIVE`, `OPENING_RANGE_BREAKOUT`, `OPTION_PRESSURE`, `SIMPLE_ORB`, `TREND_PULLBACK`, and `VWAP_RECLAIM`.

# Research Hypothesis Results

All 11 frozen hypothesis rows are present and marked `DATA_BLOCKED`: `CONSTITUENT_BREADTH`, `CONSTITUENT_LEAD_LAG`, `CONTINUOUS_STRUCTURAL_EDGE_DISCOVERY`, `FIVE_MINUTE_GOVERNED_DISCOVERY`, `ML_STRATEGY_DISCOVERY`, `OPENING_RANGE_RETEST`, `OPENING_STATE_MOMENTUM`, `RESIDUAL_MEAN_REVERSION`, `RSI2_MEAN_REVERSION`, `STRUCTURAL_PATTERN_SUITE`, and `STRUCTURAL_STATE_DISCOVERY`.

# Profit Factor

No PF is rendered for blocked rows. No no-loss or no-trade row is represented as an infinite or robust edge. Trade ledger is empty by design because strategy execution is unauthorized under the coverage gate.

# Negative Controls

Negative controls are recorded as `DATA_BLOCKED`. Running direction flip, delayed entry, random controls, strike shift, or slippage stress without enough chronological sessions would create fake precision.

# QA / Safety Review

The committed manifest records the non-action contract: `research_only=true`, `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `outcomes_read=false`, `pnl_read=false`, and `holdout_outcomes_read=false`.

# Acceptance Proof

The runner wrote `23` analytics rows: `12` canonical strategy rows and `11` frozen hypothesis rows. Every row remains visible and every row has final verdict `DATA_BLOCKED` with exact reason `INSUFFICIENT_USABLE_SESSIONS_LT_3`.

# Runtime Proof Required After Merge

Before any strategy PF run, rerun the one-command campaign runner with additional approved local data roots and require at least three usable overlapping CE/PE sessions for preliminary development. Validation and holdout claims require materially broader chronological coverage per the frozen partition policy.

# Grill Me Review

The evidence supports two option-history sessions and does not support a PF campaign. Ranking strategies from two sessions would be overfit and misleading.

# Hermes Review

The runner keeps the campaign reproducible: approved roots are explicit, data inventory is metadata-first, partitions are frozen before any strategy execution, all rows stay visible, and large artifacts remain outside Git.

# GSD Review

Implementation is intentionally fail-closed. The runner exits zero for negative economics or insufficient coverage because those are valid research outcomes; it exits non-zero only for implementation or data-integrity failures.

# What This PR Does Not Prove

This does not prove a profitable strategy, validation survivor, holdout candidate, paper readiness, live readiness, historical bid/ask execution certification, or production integration.

# Human Approval

Strategy backtesting remains unauthorized until at least three usable overlapping sessions exist for preliminary development, and materially more sessions are required for validation and holdout claims.
