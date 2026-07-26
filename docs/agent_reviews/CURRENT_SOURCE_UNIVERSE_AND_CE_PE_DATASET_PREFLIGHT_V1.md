mode: RESEARCH_ONLY_SOURCE_UNIVERSE_REPAIR_AND_DATASET_PREFLIGHT
candidate_id: current_source_universe_and_ce_pe_dataset_preflight_v1
decision: RAW_CE_PE_TICK_SOURCE_IDENTIFIED_STRICT_OPTION_REPLAY_DATASET_NOT_YET_ESTABLISHED
reason: immutable source evidence is preserved, but independent review invalidated the prior dataset-acceptance claim because the raw tick parquet was not passed through the actual strict option-replay loader, incomplete bid/ask and contract metadata were weakened into warnings, provider provenance was inferred from a path, and preflight oracle agreement was hardcoded
timestamp: 2026-07-26T12:30:00+05:30
research_only: true
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
outcomes_read: false
pnl_read: false
holdout_outcomes_read: false
source: research/option_e2e_recertification_v4/current_certification_source_universe_v1/portable_source_snapshot_manifest.json; research/option_e2e_recertification_v4/current_certification_source_universe_v1/frozen_source_audit_evidence_v1/local_source_audit_summary.json; research/option_e2e_recertification_v4/ce_pe_dataset_preflight_v1/frozen_preflight_evidence_v1/ce_pe_dataset_preflight.json

# Agent Work Contract

- source_agent: ChatGPT independent review and GitHub repair
- action: REPAIR_PUBLICATION_BOUNDARY
- title: Invalidate weak CE/PE acceptance while preserving immutable raw-source evidence
- scope: preflight fail-closed semantics, focused tests, compact evidence, Agent Review, and PR publication boundary
- allowed_paths: existing CE/PE preflight research package, focused tests, compact evidence, and this review
- forbidden_paths: strategies, candidate-pool runtime behaviour, broker, order, execution, feed, risk, dashboard, live/paper config, outcome, P&L, WFA, holdout, and Git/LFS history
- acceptance_proof: raw-source and replay-dataset authority are separated; no raw tick source is promoted without actual strict-loader execution and independent oracle evidence

# Scope Guard

No strategy code, development backtest, validation backtest, WFA, holdout, broker API, order action, P&L calculation, or outcome read was performed. PR #717 remains draft and unmerged.

# Prior Invalid Verdict

The earlier verdict `CURRENT_CERTIFICATION_SOURCE_UNIVERSE_FROZEN_AND_REAL_CE_PE_DATASET_ACCEPTED` is invalidated for the dataset lane as:

`INVALID_PREFLIGHT_ACCEPTANCE_WEAKENED_STRICT_CONTRACT`

Confirmed causes:

- the actual loader in `core/option_backtest/loader.py` was not invoked;
- `strict_loader_acceptance` was a preflight-created Boolean rather than loader evidence;
- incomplete bid/ask and contract metadata were converted from rejection reasons into warnings;
- the oracle copied primary selections and hardcoded `AGREEMENT`;
- provider identity was inferred from the path and overstated as complete provenance;
- the selected raw source contains one trading session only.

# Immutable Source Snapshot

The immutable source snapshot and execution-trace evidence remain useful research evidence. The frozen execution trace retains SHA-256 `dad26984f0b43ac64381729925d140e190d55001c0b821c87210fd9a37d9b4b4` and 1,710,990 records. Frozen source-audit Run A/Run B previously reached primary/oracle agreement.

This does not grant dataset, strategy, paper, or live authority.

# Raw CE/PE Tick Source

The frozen raw candidate is:

- candidate: `CAMPAIGN_WORKTREE:runtime/market_data/upstox/20260714/combined.parquet`
- physical SHA-256: `16f88a93c2bc7d4fdd8ff2d0ddf87573ddda7ea9f1afa434f855b04e56d43cd0`
- rows: 7,938,310
- CE rows: 3,585,819
- PE rows: 3,981,223
- CE contracts: 416
- PE contracts: 416
- quote timestamp coverage: 1.0
- bid/ask joint coverage: 0.9696916598117231
- contract metadata coverage: 0.9532308514028804
- session count: 1
- provider claim: `upstox`
- provider authority: `PATH_INFERRED_LIMITATION`

Truthful raw-source verdict:

`RAW_CE_PE_TICK_SOURCE_VALIDATED`

This verdict means actual CE and PE tick rows with real bid/ask observations exist. It does not mean the file is directly replay-compatible.

# Strict Option-Replay Readiness

The raw schema lacks the normalized replay contract required by the existing loader, including canonical timestamp/OHLC, canonical bid/ask names, quote timestamp, underlying, option type, strike, expiry, provider, dataset hash, and bar interval in loader-compatible rows.

The source also has incomplete bid/ask and contract metadata coverage. The actual strict loader has not been invoked against a deterministic normalized output.

Current verdict:

`STRICT_OPTION_REPLAY_DATASET_NOT_YET_ESTABLISHED`

Chronological coverage:

`ONE_SESSION_SMOKE_ONLY`

No strategy backtest is authorized.

# Independent Oracle

The previous preflight oracle was not independent. The corrected compact evidence now states:

- `primary_oracle_agreement=NOT_ESTABLISHED`
- `oracle_verdict=INDEPENDENT_ORACLE_REQUIRED`
- `primary_summary_consumed=false`

A future oracle must independently inspect candidate identities, hashes, CE/PE counts, quote coverage, metadata mapping, provider evidence, normalized outputs, actual loader results, selection ordering, and final verdict.

# Git LFS Review

`runtime/strategy_validation/resolved_option_ticks_20260702.parquet` remains a full Git blob despite an LFS rule. Main and campaign bytes previously matched SHA-256 `7ef6dfae7de94a1f52fac97b007259ada769347ff72299e238b6cac43ab54508`.

Verdict remains:

`LFS_POLICY_VIOLATION_FULL_BLOB_TRACKED`

No LFS or Git history repair is included.

# Grill Me Review

A large row count and partial valid-quote coverage can create false confidence. TradeBot's target is a live-equivalent pipeline where a directional signal selects an actual CE or PE contract, then freshness, liquidity, confidence and ranking operate on executable quote truth. That requires deterministic normalization and strict-loader acceptance, not merely a raw parquet containing some bid/ask rows.

The prior implementation violated this boundary by redefining acceptance until the candidate passed. This repair restores fail-closed semantics.

# Hermes Review

Architecture must separate:

1. immutable raw-source authority;
2. deterministic raw-to-replay normalization;
3. actual strict-loader compatibility;
4. chronological partition sufficiency;
5. pre-outcome strategy ledger;
6. candidate-pool to strategy to CE/PE to freshness to ranking replay;
7. development, validation and untouched holdout.

PR #717 currently proves only parts of layer 1.

# GSD Review

The GitHub repair updates preflight semantics, focused tests, compact evidence, sidecars, the PR title/body and this Agent Review. It does not alter production architecture or execute local external data workflows.

# Negative Controls

Focused controls now require:

- incomplete bid/ask coverage cannot become strict acceptance;
- path-derived provider evidence remains limitation-qualified;
- a raw tick source cannot authorize a replay dataset;
- accepted dataset ID remains null without actual loader invocation;
- independent oracle status cannot be hardcoded to agreement.

# QA / Safety Review

Safety invariants:

- `research_only=true`
- `read_only=true`
- `is_order_action=false`
- `broker_api_called=false`
- `allowed_for_live_execution=false`
- `outcomes_read=false`
- `pnl_read=false`
- `holdout_outcomes_read=false`
- `strategy_code_invoked=false`
- `backtests_run=false`

# Acceptance Proof

The corrected compact evidence states:

- accepted replay dataset ID: null;
- raw source candidate: hash-bound;
- raw-source verdict: `RAW_CE_PE_TICK_SOURCE_VALIDATED`;
- replay verdict: `STRICT_OPTION_REPLAY_DATASET_NOT_YET_ESTABLISHED`;
- coverage verdict: `ONE_SESSION_SMOKE_ONLY`;
- oracle agreement: `NOT_ESTABLISHED`.

Repository CI on the corrected exact head is still required.

# Runtime Proof Required After Merge

None. This PR must not merge as strategy-readiness evidence. Before strategy development, a local-data lane must perform exhaustive candidate discovery, deterministic normalization, actual strict-loader execution, independent oracle reconciliation, and prove sufficient multi-session chronological coverage.

# What This Does Not Prove

This work does not prove a normalized replay dataset, sufficient development/validation/holdout coverage, strategy correctness, strategy edge, candidate-pool equivalence, confidence calibration, ranking quality, profitability, paper readiness or live readiness.

# Human Approval

No human approval should promote the one-session raw tick source directly into strategy backtesting. The next local execution must first establish normalized strict replay readiness and adequate historical coverage.
