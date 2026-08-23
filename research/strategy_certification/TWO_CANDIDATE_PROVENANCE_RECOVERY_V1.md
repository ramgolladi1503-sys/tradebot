# Two-Candidate Provenance Recovery V1

Status: `RECOVERY_IN_PROGRESS_FAIL_CLOSED`

Research only. Runtime authority: `NONE`. Broker actions permitted: `false`.

This document records source-authority evidence recovered from Git history before any Strategy Certification Kernel execution.

## 1. HTF_RANGE_EXPANSION

### 1.1 Frozen source authority recovered

The locked HTF strategy was committed in:

- commit: `39612d296b07a4800c4f574c8a0dd92c20906e7c`
- PR: `#597`
- date: `2026-06-18`
- spec: `docs/research/htf_range_expansion_strategy_spec.md`

The frozen spec confirms:

- Opening Drive = first three completed 15-minute candles, 09:15-10:00
- trigger = completed 15-minute close beyond Opening Drive high/low
- regime = `VOL_EXPANSION` only
- 15m/30m trailing direction alignment required
- legal entry = next 1-minute open, never same trigger candle
- session window = 10:15-14:30
- gap exclusion = >0.5% versus prior close rejects the session
- stop = opposite Opening Drive side, minimum 2 index points
- target = fixed 1R/2R geometry
- time stop = 15:15

### 1.2 Historical audit artifacts recovered

Committed artifacts include:

- `runtime/candidate_audits/htf_range_expansion_survival_report.md`
- `runtime/candidate_audits/htf_range_expansion_final_survival_verdict.md`
- `runtime/candidate_audits/higher_tf_edge_report.md`
- `runtime/candidate_audits/htf_signal_funnel.csv`
- `runtime/candidate_audits/htf_gate_ablation_matrix.csv`
- `docs/research/htf_range_expansion_deepdive_timeline.md`
- `docs/research/vol_expansion_universe_report.md`

The committed survival report contains a materially important distinction:

- all-regime aggregate baseline expectancy is negative (`-0.0638245R`)
- `VOL_EXPANSION` regime expectancy is positive (`+0.504796R`, 727 trades)

The committed final verdict separately states:

- `PROMOTE_TO_PAPER`
- 1x expectancy `+0.47`
- break-even friction multiplier `>3.00x`

The survival report also states that the candidate does not survive its listed 3x slippage stress. These two committed summaries therefore MUST NOT be treated as a single reconciled authority without recovering the underlying trade ledger and exact cost/slippage definitions.

Required reconciliation verdict:

`HTF_HISTORICAL_METRIC_RECONCILIATION=PASS|FAIL|INSUFFICIENT_EVIDENCE`

### 1.3 Dataset provenance blocker

The HTF research engine (`core/candidate_audits/htf_engine.py`) accepts an externally supplied `data_dir`, loads every `*.csv` in that directory, concatenates them, parses timestamps as UTC, converts to `Asia/Kolkata`, and then resamples.

No exact historical source directory, source file list, or dataset SHA has yet been recovered from committed Git artifacts.

Therefore Git history alone is insufficient to bind the candidate-of-record dataset identity.

Current state remains:

`HTF_DATASET_AUTHORITY=UNPROVEN`

Do not generate the final candidate fingerprint until local/external evidence proves:

- exact data directory used for the historical run
- exact ordered source file set
- per-file SHA-256
- aggregate corpus SHA-256 / deterministic manifest hash
- timestamps/timezone semantics
- date range and row/session counts

### 1.4 Mandatory local recovery search

Search read-only across protected local evidence roots for:

- `htf_range_expansion_survival_report.md`
- `htf_range_expansion_final_survival_verdict.md`
- `higher_tf_edge_report.md`
- `htf_signal_funnel.csv`
- `htf_gate_ablation_matrix.csv`
- references to `HTFEngine(`
- shell history / command logs invoking HTF audits
- `data_dir` values adjacent to HTF audit execution

Preferred roots include existing worktrees plus `/Volumes/TradeBotData` and TradeBot OS archives.

Do not accept filename similarity as identity proof. Hash the bytes.

---

## 2. COMMON_FACTOR_OPTION_UNDERREACTION_V1

### 2.1 Frozen implementation authority recovered

Source branch:

`research/common-factor-option-underreaction-v1`

Frozen implementation:

`research/common_factor_option_underreaction_v1/campaign.py`

Frozen contract:

`research/common_factor_option_underreaction_v1/research_contract.json`

### 2.2 Exact source resolution contract recovered

The source resolver in:

`research/dispersion_ignition_straddle_v1/data.py`

requires the consolidated evidence root:

`research/local_evidence_consolidation_v1`

and deterministically prioritizes:

1. constituent/index corpus:

`external_local_dirs/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/normalized/constituent_index_5m.parquet`

2. Upstox option contract inventory:

an `upstox-expired-options-v1/.../manifests/contract_inventory.parquet` selected by the frozen resolver.

The recovered V2 normalization report records:

- original local path: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2/normalized/constituent_index_5m.parquet`
- start date: `2024-01-01`
- end date: `2025-08-29`
- raw rows: `2,532,075`
- normalized accepted rows: `2,532,066`
- invalid OHLC quarantined: `9`
- conflicting duplicate rows rejected: `0`

This identifies the intended logical corpus but DOES NOT substitute for hashing the exact current bytes.

### 2.3 The original campaign already emits the provenance needed for recovery

Before outcome gating, `campaign.py` writes:

`data_contract_report.json`

including:

- constituent relative path
- `constituent_sha256`
- contract inventory relative path
- `contract_inventory_sha256`
- constituent row count
- feature row count
- causal option-pair state row/session counts
- split counts
- a semantic SHA-256 of the data contract

It also writes:

- `session_split_manifest.json`
- `pre_outcome_freeze.json`
- `oof_signal_ledger.csv`
- `oof_trade_ledger.csv`
- `oof_screen.json`
- when reached: `validation_ledger.csv`
- when reached: `validation_screen.json`
- when reached: `holdout_ledger.csv`
- when reached: `holdout_screen.json`
- `final_decision.json`

`final_decision.json` explicitly records whether validation and holdout were opened.

Therefore prior-run archaeology should first search for these exact artifact names rather than rerunning the campaign.

### 2.4 Holdout integrity rule

Recover the oldest authoritative prior output root first.

If a recovered `final_decision.json` says:

- `holdout_opened: true` -> holdout is already consumed.
- `holdout_opened: false` -> preserve that evidence together with artifact hash and run/source SHA.

If multiple output roots conflict, do not choose the most favorable one. Record all roots and return:

`COMMON_FACTOR_HOLDOUT_INTEGRITY=UNKNOWN`

until lineage is resolved.

Absence of a `holdout_ledger.csv` is not by itself proof that holdout was never accessed; use the final decision, workflow/command evidence and artifact lineage together.

### 2.5 Historical execution limitation remains binding

The source README explicitly states historical bid/ask and IV are unavailable. The campaign therefore cannot acquire spread-certified executable-option authority by reinterpreting historical OHLC/LTP data.

No synthetic bid/ask or IV may be introduced.

---

## 3. Next gate

Before any certification replay, produce one compact recovery manifest containing:

```text
HTF_EXACT_SOURCE_FILES=
HTF_SOURCE_SHA256_SET=
HTF_CORPUS_MANIFEST_SHA256=
HTF_HISTORICAL_LEDGER_HASH=
HTF_HISTORICAL_METRIC_RECONCILIATION=

COMMON_FACTOR_CONSTITUENT_PATH=
COMMON_FACTOR_CONSTITUENT_SHA256=
COMMON_FACTOR_CONTRACT_INVENTORY_PATH=
COMMON_FACTOR_CONTRACT_INVENTORY_SHA256=
COMMON_FACTOR_DATA_CONTRACT_SEMANTIC_SHA256=
COMMON_FACTOR_PRIOR_OUTPUT_ROOT=
COMMON_FACTOR_PRIOR_FINAL_DECISION_SHA256=
COMMON_FACTOR_VALIDATION_ACCESSED=
COMMON_FACTOR_HOLDOUT_ACCESSED=
COMMON_FACTOR_HOLDOUT_INTEGRITY=
```

Only when those fields are evidence-backed may the registry dataset SHA values and candidate fingerprints be populated.

No certification run is authorized by this recovery note itself.
