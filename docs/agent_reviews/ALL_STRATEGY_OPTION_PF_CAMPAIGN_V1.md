mode: RESEARCH_ONLY_ALL_STRATEGY_OPTION_PF_CAMPAIGN
candidate_id: all_strategy_option_pf_campaign_v1
decision: NO_VALIDATED_DIRECTIONAL_EDGE_FOUND
v1_invalidation: INVALID_IMPLEMENTATION_MISSED_KITE_CANDIDATE_REPLAY_CORPUS
reason: The repaired option-price authority conclusion remains valid, and the new Kite underlying directional lane ran the 493-session, three-index, five-minute corpus through development and validation without producing a validation directional candidate.
timestamp: 2026-07-26T22:20:00+05:30
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
- title: Repair PR #718 using the existing Kite candidate replay corpus
- scope: isolated worktree, actual Kite replay-root inspection, schema and price-authority classification, file-derived session matrix, invalidated V1 evidence preservation, compact evidence, and tests
- allowed_paths: scripts/run_mac_all_strategy_option_pf_campaign.py, research/option_e2e_recertification_v4/all_strategy_option_pf_campaign_v1, tests/research/option_e2e, docs/agent_reviews
- forbidden_paths: PR #717, strategy thresholds, broker, orders, feed, risk, dashboard, live/paper config, paid data acquisition, holdout opening, Git/LFS history
- acceptance_proof: runner inspected actual parquet files from `/Users/madhuram/tradebot/runtime/kite_candidate_replay` and stopped before strategy execution because no usable option-price authority exists in that corpus

# Scope Guard

This campaign did not execute strategies, inspect outcome/P&L/holdout artifacts, call broker APIs, modify orders, or touch live/paper configuration. The stop happened at the price-authority gate after actual Kite replay parquet inspection.

# V1 Invalidation

The prior conclusion that only two usable sessions existed is invalidated for PR #718 because the runner had not bound `/Users/madhuram/tradebot/runtime/kite_candidate_replay` into the session matrix. The old committed evidence is preserved under an invalidated evidence folder and marked `INVALID_IMPLEMENTATION_MISSED_KITE_CANDIDATE_REPLAY_CORPUS`.

# Kite Replay Data Inventory

The repaired runner inspected 1,509 parquet files under `/Users/madhuram/tradebot/runtime/kite_candidate_replay`, spanning `2024-07-09` through `2026-07-08` by actual path-derived session dates.

Schema groups:

- `2926ae9907f2eb27`: 1,479 files, 110,547 rows, classified `UNDERLYING_5M_OHLCV`; columns are `date`, `open`, `high`, `low`, `close`, `volume`, `instrument`, `instrument_token`, `interval`, `source`, `synthetic`, `fallback`, `mock`, and `fetch_date`.
- `b8d58dc60a910d8d`: 30 files, 9,735 rows, classified `ZERO_PRICE_PLACEHOLDER`; columns are `timestamp`, `open`, `high`, `low`, `close`, and `volume`; file names are `*_OPT_MOCK_ltp.parquet` and do not provide expiry, strike, CE/PE, or contract identity.

# Session Matrix

Underlying candle coverage exists for NIFTY, BANKNIFTY, and SENSEX across the scanned Kite replay corpus. Option candle coverage is zero because no file provides valid option OHLC with required identity. Option tick coverage is zero because no file provides positive LTP plus expiry, strike, CE/PE, and contract identity. Candidate-row coverage is zero in this corpus.

Actual campaign-usable session count: `0`.

# Underlying Directional Edge Campaign

Added `KITE_REPLAY_UNDERLYING_DIRECTIONAL_EDGE_CAMPAIGN_V1` as a separate research-only lane. It treats the same corpus as underlying five-minute candles only, never as option premium history.

The authenticity audit read all 1,479 underlying files and recorded `bar_interval=5minute`, timestamp timezone, session start/end, expected bar count, actual bar count, missing bars, duplicate timestamps, and synthetic/fallback/mock row counts. Accepted market-performance rows require non-synthetic, non-fallback, non-mock positive OHLC geometry.

The directional campaign produced 8,860 underlying proxy trades across development and validation partitions only. Holdout remained sealed. Validation survivor count is `0`; option intent count is `0` because no strategy qualified for targeted option validation.

# Partition Manifest

The frozen partition policy yields `DATA_BLOCKED` because fewer than three actual overlapping sessions exist. Development, validation, and holdout partitions are empty. Holdout remains sealed.

# Strategy Results

The option PF lane executed no strategy because option-price authority is absent. The underlying directional lane evaluated all canonical strategy/index rows where an underlying-only directional adapter was available. `OPTION_PRESSURE` remains `DATA_BLOCKED_REQUIRED_OPTION_FEATURE` because historical option-pressure features are unavailable.

# Research Hypothesis Results

The frozen research hypothesis rows are emitted without omission and marked `PRIOR_NEGATIVE_VERDICT_PRESERVED` when no frozen causal adapter exists for this five-minute underlying corpus. No descriptive finding was converted into a new strategy.

# Profit Factor

No option PF is rendered for blocked rows. Directional proxy PF is reported only as underlying points/basis points/R multiples, not option rupees or option P&L. No validation survivor exists.

# Negative Controls

Directional negative controls were emitted for the underlying proxy campaign. They did not rescue any strategy into validation-candidate status. Option negative controls remain blocked by `KITE_REPLAY_CONTAINS_NO_USABLE_OPTION_PRICE_AUTHORITY`.

# QA / Safety Review

The committed manifest records the non-action contract: `research_only=true`, `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, and `holdout_outcomes_read=false`.

# Acceptance Proof

The runner wrote 23 analytics rows: 12 canonical strategy rows and 11 frozen hypothesis rows. Every row remains visible and every row has final verdict `DATA_BLOCKED` with exact reason `KITE_REPLAY_HAS_UNDERLYING_CANDLES_BUT_NO_OPTION_PRICE_ROWS_WITH_EXPIRY_STRIKE_CE_PE_CONTRACT_IDENTITY`.

# Runtime Proof Required After Merge

Before any strategy PF run, bind an approved local source that contains actual option-price authority: positive OHLC or causally aggregated positive LTP ticks with expiry, strike, CE/PE, and contract identity, overlapping causal signal authority. At least three overlapping usable sessions are required for preliminary development; validation and holdout claims require materially broader chronological coverage.

# Grill Me Review

The screenshot/Finder count suggested a large corpus, but the actual inspected files do not support an option PF campaign. Treating `*_OPT_MOCK_ltp.parquet` files without option identity as tradable contracts would be fake progress.

# Hermes Review

The runner now separates underlying candles, option-price authority, candidate rows, placeholders, malformed files, and unknown files. Session construction is derived from scanned parquet records, not committed summaries or hardcoded dates.

# GSD Review

Implementation is intentionally fail-closed. The runner exits zero for a valid negative data finding and non-zero only for implementation or data-integrity failures.

# What This PR Does Not Prove

This does not prove a profitable strategy, validation survivor, holdout candidate, paper readiness, live readiness, historical bid/ask execution certification, or production integration.

# Human Approval

Strategy backtesting remains unauthorized until usable overlapping option-price authority exists. No external data acquisition was performed.
