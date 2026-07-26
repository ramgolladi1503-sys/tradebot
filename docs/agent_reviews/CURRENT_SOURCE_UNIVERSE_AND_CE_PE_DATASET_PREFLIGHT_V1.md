mode: RESEARCH_ONLY_SOURCE_UNIVERSE_REPAIR_AND_DATASET_PREFLIGHT
candidate_id: current_source_universe_and_ce_pe_dataset_preflight_v1
decision: CURRENT_CERTIFICATION_SOURCE_UNIVERSE_FROZEN_AND_REAL_CE_PE_DATASET_ACCEPTED
reason: immutable source snapshot package was produced outside the repo, frozen source audit reached primary/oracle agreement with byte-identical Run A/Run B evidence, and frozen CE/PE preflight accepted one real Upstox CE/PE quote dataset without strategy, outcome, P&L, WFA, or holdout access
timestamp: 2026-07-26T00:00:00+05:30
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

- source_agent: Codex
- action: GENERATE_PATCH
- title: Repair immutable source reconciliation and complete CE/PE dataset preflight
- scope: frozen source snapshot packaging, source audit reconciliation diagnostics, oracle traversal repair, CE/PE dataset preflight, compact evidence publication, and focused tests
- requested_paths: research/option_e2e_recertification_v4/current_certification_source_universe_v1, research/option_e2e_recertification_v4/local_unresolved_source_audit_v1, research/option_e2e_recertification_v4/ce_pe_dataset_preflight_v1, tests/research/option_e2e, docs/agent_reviews
- allowed_paths: requested research/test/review paths only
- forbidden_paths: strategies, runtime strategy behavior, broker, order, execution routing, feed, risk, dashboard, live/paper config, outcomes, P&L, WFA, holdout, Git history, Git LFS objects/history
- expected_tests: focused current-source, local-source-audit, CE/PE preflight, full option-E2E research tests, option loader tests, diff check, and Code Excellence gates
- acceptance_proof: frozen source audit primary/oracle agreement, byte-identical Run A/Run B audit artifacts, byte-identical Run C/Run D preflight artifacts, and compact hash-bound evidence committed

# Scope Guard

This work did not run strategy code, development backtests, validation backtests, WFA, holdout, or broker APIs. Evidence remains research-only and explicitly records `read_only=true`, `is_order_action=false`, `broker_api_called=false`, and `allowed_for_live_execution=false` where applicable.

# Prior Blocked Result

The legacy result `LOCAL_SOURCE_AUTHORITY_BLOCKED_MISSING_DECLARED_ROOTS` remains preserved as a historical reproducibility limitation. It is not reinterpreted as current dataset authority.

# Legacy 27-Root Reconstruction

The legacy reconstruction still publishes 27 historical root records and deliberately recovers zero exact prior paths. Its verdict remains `LEGACY_27_ROOT_CENSUS_NON_REPRODUCIBLE_MISSING_PATH_BINDINGS`.

# Current Certification Source Universe

The current source universe is frozen through an external immutable snapshot package at `/Users/madhuram/tradebot-ml-evidence/ce-pe-option-certification-v1/source_snapshot_v1`. The committed portable manifest hash is `76c12fef84b3e7d87b1e5b6bc8ecec26da59f998626aba4f3d92f38f92992b9f`.

# Immutable Snapshot Contents

The snapshot selected three inputs: the execution trace snapshot, `runtime/market_data/upstox/20260714/combined.parquet`, `runtime/strategy_validation/resolved_option_ticks_20260702.parquet`, and `runtime/upstox_instruments/complete.json`. Snapshot construction recorded stable source identity before and after copy, marked selected files read-only, and quarantined 103 non-input denied candidates. No selected input had denied outcome/P&L dependencies.

# Source Reconciliation Repair

The earlier source audit failure is classified as `PRIMARY_ORACLE_LOGIC_DEFECT` / `PATH_NORMALIZATION_DEFECT`, not live mutation. The frozen trace checks passed, and the oracle repair aligned root traversal with the primary manifest iterator.

# Execution Trace Audit

The frozen trace SHA-256 is `dad26984f0b43ac64381729925d140e190d55001c0b821c87210fd9a37d9b4b4`, with 1,710,990 records. The frozen source audit decision remains `LOCAL_SOURCE_CANDIDATES_FOUND_REQUIRES_HUMAN_AUTHORITY_REVIEW`, meaning source candidates exist but do not grant strategy or live authority.

# Primary and Oracle Agreement

Frozen source audit Run A and Run B both reported `primary_oracle_agreement=AGREEMENT`; `diff -qr` returned no differences. The committed summary hash is `814c9ae32e6af81b18672443b47beced25e0e1ab07cee35349a5e7727ede01fa`.

# CE/PE Dataset Preflight

Frozen preflight accepted one real dataset: `CAMPAIGN_WORKTREE:runtime/market_data/upstox/20260714/combined.parquet`, physical SHA-256 `16f88a93c2bc7d4fdd8ff2d0ddf87573ddda7ea9f1afa434f855b04e56d43cd0`. It contains 7,938,310 rows, 3,585,819 CE rows, 3,981,223 PE rows, provider `upstox`, quote timestamp coverage `1.0`, bid/ask joint coverage `0.9696916598117231`, and contract metadata coverage `0.9532308514028804`.

# Dataset Caveats

The accepted Upstox dataset is a tick quote dataset, not a fully normalized bar dataset. It has incomplete bid/ask and contract metadata coverage; those gaps are recorded as `data_quality_warnings`, not acceptance blockers, because executable bid/ask quotes, CE/PE rows, timestamps, provider identity, and frozen physical-hash provenance are present. Any later replay must filter invalid quote rows and must not treat this as a complete strategy-ready ledger.

# Rejected Dataset

`CAMPAIGN_WORKTREE:runtime/strategy_validation/resolved_option_ticks_20260702.parquet` was rejected for missing CE coverage, missing PE coverage, missing quote timestamps, missing contract metadata, and missing provider. Its physical SHA-256 is `7ef6dfae7de94a1f52fac97b007259ada769347ff72299e238b6cac43ab54508`.

# Git LFS Review

`runtime/strategy_validation/resolved_option_ticks_20260702.parquet` matches an LFS filter rule, but `HEAD` stores a full parquet blob of 95,829,241 bytes. Main and campaign worktree physical bytes matched with SHA-256 `7ef6dfae7de94a1f52fac97b007259ada769347ff72299e238b6cac43ab54508`. Verdict: `LFS_POLICY_VIOLATION_FULL_BLOB_TRACKED`.

# Determinism

Frozen source audit Run A/Run B and CE/PE preflight Run C/Run D were byte-identical by `diff -qr`. The committed preflight summary hash is `ed83fed2fb9e3afea9c3a6f852ea990b66f1bd3790241cd958df2ee5bb0ff631`.

# Negative Controls

Focused tests cover missing historical path rejection, overlapping current roots, root-manifest audit mode, reconciliation diagnostic publication, underlying-only rejection, LTP-without-bid/ask rejection, CE-only rejection, frozen snapshot preflight acceptance, and rejected hash/metadata failures.

# QA / Safety Review

The executed commands were snapshot packaging, source-audit diagnostics, frozen source audit, frozen preflight, LFS inspection, and tests. No broker, strategy, outcome, P&L, WFA, or holdout command was run.

# Grill Me Review

Risk verdict: research evidence improved, but this is not a readiness PR. The accepted dataset has incomplete bid/ask and contract metadata coverage, and the source audit still requires human authority review before any strategy use. The known Git LFS policy violation remains unchanged and must not be hidden by this PR.

# Hermes Review

Architecture verdict: the repaired flow keeps mutable runtime bytes outside Git, binds committed evidence to SHA-256 sidecars, and separates current frozen source authority from non-reproducible legacy roots. The next stage must preserve the frozen snapshot boundary and require explicit source-authority approval before any strategy or replay wiring.

# GSD Review

Execution verdict: scope stayed inside research, tests, and review evidence paths. The PR adds focused tests and compact evidence only; it does not touch broker, order, risk, feed, strategy thresholds, dashboard, or live/paper configuration.

# Acceptance Proof

Required evidence exists as compact committed JSON and sidecar SHA-256 files under `research/option_e2e_recertification_v4/current_certification_source_universe_v1` and `research/option_e2e_recertification_v4/ce_pe_dataset_preflight_v1`. The external frozen source bytes remain outside Git under `/Users/madhuram/tradebot-ml-evidence/ce-pe-option-certification-v1/source_snapshot_v1`.

# Runtime Proof Required After Merge

Before any strategy development step, rerun frozen source audit and CE/PE preflight from the committed tools against the immutable snapshot package. Require no outcome/P&L/holdout reads, byte-identical repeated outputs, and explicit human source-authority approval.

# What This PR Does Not Prove

This does not prove profitability, strategy edge, execution readiness, paper/live readiness, pre-outcome signal-ledger authority, WFA validity, holdout validity, broker connectivity, or Phase 2 integration.

# Human Approval

Human review is required before using the accepted dataset for strategy development. The dataset preflight proves real CE/PE quote data availability only; it does not authorize live execution or strategy promotion.
