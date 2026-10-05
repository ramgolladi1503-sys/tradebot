mode: RESEARCH_ONLY_SOURCE_UNIVERSE_REPAIR_AND_DATASET_PREFLIGHT
candidate_id: current_source_universe_and_ce_pe_dataset_preflight_v1
decision: RAW_CE_PE_TICK_SOURCE_NORMALIZER_SMOKE_PASS_METADATA_FIRST_INVENTORY_IMPLEMENTED_LOCAL_EXECUTION_REQUIRED
reason: immutable source evidence and one-session normalization smoke proof remain valid; a bounded metadata-first all-root inventory with independent oracle and real archive evidence is now implemented, but it has not been executed against the Mac-only external roots and sufficient multi-session replay coverage is not established
timestamp: 2026-07-26T16:45:00+05:30
research_only: true
read_only: true
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
outcomes_read: false
pnl_read: false
holdout_outcomes_read: false
source: research/option_e2e_recertification_v4/current_certification_source_universe_v1/portable_source_snapshot_manifest.json; research/option_e2e_recertification_v4/current_certification_source_universe_v1/frozen_source_audit_evidence_v1/local_source_audit_summary.json; research/option_e2e_recertification_v4/ce_pe_dataset_preflight_v1/frozen_preflight_evidence_v1/ce_pe_dataset_preflight.json; research/option_e2e_recertification_v4/ce_pe_replay_normalization_v1/replay_readiness_evidence_v1/ce_pe_replay_readiness_summary.json; research/option_e2e_recertification_v4/ce_pe_history_inventory_v1/tracked_replay_archive_option_history_compact_v1.json

# Agent Work Contract

- source_agent: ChatGPT independent review and direct GitHub implementation
- action: REPAIR_PUBLICATION_BOUNDARY_AND_IMPLEMENT_METADATA_FIRST_INVENTORY
- title: Preserve raw CE/PE evidence, prove one-session replay smoke, and implement bounded local-history discovery
- scope: preflight fail-closed semantics, immutable evidence, raw-to-replay smoke normalization, actual strict-loader proof, metadata-first parquet/ZIP inventory, independent oracle, focused tests, and publication boundary
- allowed_paths: focused CE/PE research packages, focused tests, compact evidence, and this review
- forbidden_paths: strategies, candidate-pool runtime behaviour, broker, order, execution, feed, risk, dashboard, live/paper config, outcome, P&L, WFA, holdout, and Git/LFS history
- acceptance_proof: no raw tick source is promoted without actual strict-loader execution; metadata discovery does not full-read broad parquet files; archive evidence is hash-bound; strategy work remains blocked without sufficient chronological coverage

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

This means actual CE and PE tick rows with real bid/ask observations exist. It does not mean the raw file is directly replay-compatible.

# Strict Option-Replay Smoke

A deterministic research-only normalizer produced selected per-contract CSV files outside Git and invoked the actual loader using `ResearchMode.REAL_EXECUTABLE_RESEARCH`.

- normalized contract files attempted: 12
- actual strict-loader pass count: 12
- actual strict-loader fail count: 0
- normalizer result: `NORMALIZER_SMOKE_PASS`
- independent oracle agreement: `AGREEMENT`
- valid session: `2026-07-14`
- chronological coverage: `ONE_SESSION_SMOKE_ONLY`
- replay dataset verdict: `INSUFFICIENT_REPLAY_COVERAGE`
- strategy development authorized: false

The top-12 contract selection proves only adapter/loader wiring. It does not represent the future deterministic expiry/strike policy and grants no strategy authority.

# Metadata-First Inventory Implementation

The new package `research/option_e2e_recertification_v4/ce_pe_history_inventory_v1` implements the previously missing bounded local-history discovery lane.

It:

- traverses approved roots deterministically with `candidate_limit=null`;
- rejects symlinks, overlapping roots, and special files;
- records denied outcome/P&L paths by metadata only and does not hash or open them;
- inspects parquet footer/schema metadata through `pyarrow.parquet.ParquetFile` rather than `pandas.read_parquet`;
- full-reads no broad parquet table during candidate discovery;
- ignores stale allowed-class lists for discovery so option files in external roots cannot be silently hidden;
- selectively inspects option-like ZIP parquet members without extracting the whole archive;
- separates archive session directories from expiry labels;
- groups exact-content duplicates;
- publishes a primary inventory plus independently implemented oracle and reconciliation matrix;
- always leaves `strategy_development_authorized=false` at inventory stage.

Synthetic controls prove broad parquet tables are not full-read, stale class lists cannot hide option data, denied files stay unopened, and archive expiry labels cannot masquerade as session dates.

# Tracked Replay Archive Result

The PR #713 archive evidence is now bound into a compact committed artifact and sidecar.

- archive: `runtime/upstox_candidate_replay.zip`
- archive SHA-256: `4357f109ed631802b3774c34db9c318f71742f8e99de307408af71bf00810707`
- source full-audit SHA-256: `f9c4d7b92deb45bae64fb3b9bc3eabdfef516864a9eb6988c5a5042fc65aa2d9`
- option-like parquet members: 126
- CE members: 63
- PE members: 63
- option session directories: only `20260709`
- underlyings: BANKNIFTY, NIFTY, SENSEX
- chronological verdict: `ONE_SESSION_SMOKE_ONLY`

The archive's hundreds of underlying parquet dates are not option-history dates. It adds at most one further option smoke session and cannot establish development/validation/holdout coverage.

# Current Exhaustive Inventory Status

The metadata-first implementation is present and CI-testable, but the complete all-root run has not been executed against:

- `/Users/madhuram/tradebot`
- `/Users/madhuram/tradebot-ce-pe-option-certification-v1`
- `/Users/madhuram/tradebot-data`
- `/Users/madhuram/tradebot-ml-evidence`

Those paths are available only on the user's Mac and are inaccessible to GitHub-hosted execution and this connector environment.

Current verdict:

`METADATA_FIRST_INVENTORY_IMPLEMENTED_LOCAL_EXTERNAL_ROOT_EXECUTION_REQUIRED`

This remains a blocker for strategy development.

# Independent Oracle

The replay-readiness oracle agrees with the one-session normalization smoke proof. The new inventory oracle independently walks roots and ZIP members, derives option candidate identities, session dates, footer counts, denied counts, and candidate-manifest hashes without consuming the primary inventory summary.

The inventory publication fails closed on disagreement.

# Git LFS Review

`runtime/strategy_validation/resolved_option_ticks_20260702.parquet` remains a full Git blob despite an LFS rule. Main and campaign bytes previously matched SHA-256 `7ef6dfae7de94a1f52fac97b007259ada769347ff72299e238b6cac43ab54508`.

Verdict remains:

`LFS_POLICY_VIOLATION_FULL_BLOB_TRACKED`

No LFS or Git history repair is included.

# Grill Me Review

A large raw row count or hundreds of underlying dates can create false confidence. The product target is a live-equivalent replay where a strategy chooses an actual CE or PE contract and downstream freshness, liquidity, confidence, ranking, and ask-entry/bid-exit accounting operate on executable quote truth.

That requires sufficient option sessions, deterministic all-contract availability, real strict-loader compatibility, and frozen chronological partitions. One or two smoke sessions cannot support this claim.

# Hermes Review

Architecture remains separated into:

1. immutable raw-source authority;
2. bounded metadata-first source discovery;
3. deterministic raw-to-replay normalization;
4. actual strict-loader compatibility;
5. chronological partition sufficiency;
6. pre-outcome strategy ledger;
7. candidate-pool to strategy to CE/PE to freshness to ranking replay;
8. development, validation and untouched holdout.

PR #717 proves parts of layers 1-4 for smoke use and implements the discovery mechanism for layer 2. It does not prove layers 5-8.

# GSD Review

Changes remain inside research, compact evidence, tests, and this review. No production architecture or strategy workflow is altered.

# Negative Controls

Focused controls require:

- incomplete bid/ask coverage cannot become strict acceptance;
- path-derived provider evidence remains limitation-qualified;
- a raw tick source cannot authorize a replay dataset;
- accepted dataset ID remains null without actual loader invocation;
- independent oracle status cannot be hardcoded to agreement;
- one-session loader success remains insufficient replay coverage;
- broad parquet files are not full-read during inventory;
- stale allowed-class lists cannot hide option candidates;
- denied outcome/P&L files remain unopened;
- archive expiry labels cannot become session dates;
- committed archive evidence and its sidecar must reconcile;
- the archive remains a one-session no-go result.

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

Current proven facts:

- raw source candidate: hash-bound;
- raw-source verdict: `RAW_CE_PE_TICK_SOURCE_VALIDATED`;
- normalization result: `NORMALIZER_SMOKE_PASS`;
- actual strict-loader passes: 12;
- actual strict-loader failures: 0;
- replay-readiness oracle: `AGREEMENT`;
- valid normalized smoke session: `2026-07-14`;
- tracked archive option session: `2026-07-09` only;
- replay verdict: `INSUFFICIENT_REPLAY_COVERAGE`;
- strategy authorization: false;
- metadata-first all-root scanner: implemented;
- local external-root scan: not executed in this environment.

All permanent repository checks must be terminal and successful on the exact final head before publication.

# Runtime Proof Required After Merge

None. This PR must remain draft and unmerged as strategy-readiness evidence. The next required runtime proof is a read-only Mac-local execution of the metadata-first inventory against the regenerated machine-specific root manifest, followed by two deterministic runs and oracle reconciliation.

# What This PR Does Not Prove

This does not prove exhaustive Mac-local source coverage, at least 100 valid option sessions, authoritative provider provenance, development/validation/holdout partitions, candidate-pool equivalence, strategy correctness, edge, confidence calibration, ranking quality, profitability, paper readiness, or live readiness.

# Human Approval

No human approval should promote the one-session raw tick source or the one-session archive into strategy backtesting. Strategy work can start only after the local inventory finds and validates sufficient chronological CE/PE replay coverage.
