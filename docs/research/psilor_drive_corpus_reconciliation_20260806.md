# PSILOR V1 Google Drive Corpus Reconciliation

**Audit date:** 2026-08-06  
**Scope:** Read-only inventory and admission classification of connected Google Drive market-data evidence for DORL/PSILOR.  
**Safety boundary:** No merge, no strategy integration, no threshold tuning, no broker/order changes, and no edge or profitability claim.

## Principal verdict

```text
DRIVE_MARKET_CORPUS_FOUND=YES
DRIVE_CORPUS_HAS_CHECKSUM_AUTHORITY=YES
DRIVE_CORPUS_HAS_LIVE_NIFTY_OPTIONS=YES
DRIVE_CORPUS_HAS_LIVE_NIFTY_FUTURES=YES
DRIVE_CORPUS_HAS_NIFTY50_CONSTITUENTS=YES
DRIVE_CORPUS_HAS_EXECUTABLE_OPTION_ASK_BID_REPLAY=NO
DRIVE_CORPUS_HAS_30_ADMITTED_SESSIONS=NO
DRIVE_EXPIRED_OPTION_CANDLE_ARCHIVE=NOT_PROVEN
DRIVE_CAN_REDUCE_NEW_DOWNLOAD=YES
DRIVE_CAN_REPLACE_FORMAL_HISTORICAL_EXTRACTION=NO
FRESH_BOUNDED_UPSTOX_SMOKE_REQUIRED=YES
DATA_READY_FOR_DORL_ONLY=NO
DATA_READY_FOR_PSILOR_PROXY_VALIDATION=NO
FORMAL_EXTRACTION_APPROVED=NO
```

The Drive corpus is substantial and must be reused. It is primarily a **live tick/replay corpus**, not a proven multi-month expired-option candle corpus. It reduces the missing-data delta but does not satisfy the 30-session DORL/PSILOR admission gate.

## Authoritative Drive roots found

| Drive root | Classification | Evidence |
|---|---|---|
| `tradebot_market_data/upstox_multi_asset` | Primary sealed multi-asset campaign | Contains a 459,107,210-byte archive, offline dataset archives, and a dated campaign hierarchy. |
| `upstox_market_data` | Older dated live captures | Dated folders include 2026-07-13, 2026-07-14, 2026-07-15, 2026-07-20, 2026-08-03 and 2026-08-05. |
| `market_data` | Legacy replay/tick files | Mix of substantial Parquets and invalid/tiny placeholder files; requires per-file validation. |

## Primary sealed campaign

### Identity

```text
CAMPAIGN=meg-dual-provider-20260805-05
TRADE_DATE=2026-08-05
SEALED_AT_UTC=2026-08-05T11:16:25.678607Z
TOTAL_FILES=11347
TOTAL_BYTES=667730913
```

The session manifest contains SHA-256 values for every sealed file.

### Normalized inventory

```text
NORMALIZED_FILES=11250
NORMALIZED_ROWS=1315840
NORMALIZED_BYTES=527413368
PROVIDER=upstox
TRADE_DATES=1
```

| Asset class | Family | Files | Rows | Approx. bytes | Source-time coverage UTC |
|---|---|---:|---:|---:|---|
| Option | NIFTY | 1,783 | 681,043 | 122,016,000 | 07:25:42–10:09:59 |
| Future | NIFTY | 1,779 | 16,165 | 72,480,000 | 07:31:56–10:09:59 |
| Equity | OTHER | 1,703 | 342,686 | 88,310,000 | 07:31:56–10:29:54 |
| Index | NIFTY/BANKNIFTY/INDIA_VIX | 5,985 | 275,946 | 244,600,000 | 07:31:56–10:30:00 |

All normalized chunks have positive row counts. The campaign covers only one date and begins well after the 09:15 IST market open. It is therefore a partial-session shadow/replay sample, not a multi-session confirmation corpus.

### Validation status

```text
RAW_VALID=TRUE
RAW_FRAMES=70202
NORMALIZED_VALID=FALSE
NORMALIZED_ISSUES=6781
ISSUE_CLASS=NON_MONOTONIC_EQUAL_LOCAL_SEQUENCE
PARTITION_VALIDATION=PASS
PARTITION_FILES=11250
PARTITION_ERRORS=0
```

All 6,781 reported issues have the form:

```text
Non-monotonic local sequence N -> N
```

This is an ordering/identity defect, not evidence that OHLC or tick values are invalid. However, the normalized corpus cannot be admitted directly while sequence identity is ambiguous.

**Required handling:** Treat raw frames as authority and deterministically rebuild normalized rows. Do not deduplicate on `local_sequence` alone. The stable identity must include provider/run, instrument key, source timestamp, event/message type, and a payload hash or equivalent immutable source identity.

## Constituent authority

```text
NIFTY50_CONSTITUENT_COUNT=50
MEMBERSHIP_EFFECTIVE_DATE=2026-08-05
UNRESOLVED_SYMBOLS=0
DUPLICATES=0
```

The membership and constituent files are checksum-valid and usable for equal-weight breadth on 2026-08-05.

The weights file states:

```text
OFFICIAL_WEIGHTS_AVAILABLE=FALSE
SOURCE=OFFICIAL_WEIGHT_REFERENCE_UNAVAILABLE
FALLBACK_WEIGHT=2.0_PERCENT_PER_SYMBOL
```

Therefore:

- Equal-weight participation/breadth is admissible for this date after source reconciliation.
- Official-weight participation is **not** admissible.
- No weighted constituent-pressure claim may use the fallback as though it were official index weighting.

## Offline dataset V3

The archive `offline_datasets_v3.tar.gz` was downloaded and independently checksum-verified.

```text
ARCHIVE_SHA256=15f6be1f5636df7ed839c7f5dbc5cdb43380497681223d14fff6b9bedc6487cf
PRECURSOR_ROWS=75
FUTURES_OUTCOME_ROWS=75
OPTION_OUTCOME_ROWS=825
JOIN_ROWS=75
CAUSALITY_AUDIT=PASS
SEAM_AUDIT=PASS
STALE_INTERVALS=3
DETERMINISTIC_TESTS=PASS_REPORTED
INNER_FILE_HASH_RECONCILIATION=PASS
```

### Important schema limitations

The option outcome dataset contains:

```text
ENTRY_QUOTE_AUTHORITY=LTP_ONLY
ENTRY_BID=ALL_NULL
ENTRY_ASK=ALL_NULL
ENTRY_MID=ALL_NULL
ENTRY_SPREAD=ALL_NULL
ENTRY_DEPTH=ALL_NULL
VOLUME_CHANGE=ALL_NULL
OI_CHANGE=ALL_NULL
```

The precursor dataset contains:

```text
OFFICIAL_WEIGHT_PARTICIPATION=ALL_NULL
FUTURE_BID_ASK_IMBALANCE=ALL_NULL
```

Therefore V3 is suitable for:

- deterministic pipeline testing;
- causal timestamp and horizon checks;
- equal-weight participation feature smoke tests;
- futures-to-LTP option response diagnostics.

It is **not** suitable for:

- strict ask-entry/bid-exit replay;
- spread/depth/liquidity gates;
- executable P&L;
- DORL certification;
- PSILOR edge validation.

### V2 disposition

`upstox_offline_datasets_v2_20260805.tar.gz` is checksum-valid but is superseded by V3 for current testing. V2 contains 317 precursor/futures rows and 3,487 option rows, while V3 applies stricter freshness/seam and causal-horizon audits and retains only 75 fresh precursor intervals.

```text
OFFLINE_V2=SUPERSEDE_WITH_REASON
OFFLINE_V3=REUSE_FOR_PIPELINE_SMOKE_ONLY
```

## Older dated captures

### 2026-08-03

```text
TOTAL_MESSAGES=156927
DROPPED_MESSAGES=0
PARSE_FAILURES=0
RECONNECTS=3
COVERAGE_KEYS=722
FINALIZED_AT=2026-08-03T15:35:00.767564
```

Classification: `REUSE_AS_RAW_LIVE_REPLAY_PENDING_SCHEMA_AND_HASH_AUDIT`.

### 2026-07-14

```text
TOTAL_MESSAGES=113465
DROPPED_MESSAGES=0
PARSE_FAILURES=0
RECONNECTS=1
COVERAGE_KEYS=878
FINALIZED_AT=2026-07-14T15:35:00.659041
COMBINED_PARQUET_BYTES=209540762
```

Classification: `REUSE_AS_RAW_LIVE_REPLAY_PENDING_SCHEMA_AND_HASH_AUDIT`.

### Other dated folders

The 2026-07-13, 2026-07-15 and 2026-07-20 folders contain substantial tick/combined Parquet evidence, but their manifests were not independently materialized in this audit.

Classification: `INVENTORY_PRESENT_NOT_YET_ADMITTED`.

### Legacy `market_data` root

The root includes both substantial files and obvious invalid placeholders:

- examples of potentially reusable files: approximately 224 KB, 1.0 MB, 3.2 MB and 60.8 MB;
- multiple 4-byte files: invalid placeholders;
- multiple 747-byte files: too small to assume valid market data without parsing.

Classification must be per file, never by extension alone.

## PR #719 reconciliation

PR #719 provides the expired-option acquisition and governance implementation. Its committed offline replay reports show a smaller checked-in test surface, including 12 parsed contracts and 21,399 one-minute rows. The larger historical corpus previously reported outside the small committed fixtures must still be materialized and hash-reconciled.

No Drive item was proven to be the complete PR #719 expired-option candle archive during this audit.

```text
PR719_CODE_AND_REPORTS=REUSE_DIRECTLY
PR719_LFS_POINTERS=NOT_DATA
PR719_LARGE_CORPUS_IN_DRIVE=NOT_PROVEN
BLIND_REDOWNLOAD=PROHIBITED
```

## Reuse matrix

| Evidence | Decision | Permitted use | Blocker before higher authority |
|---|---|---|---|
| 2026-08-05 raw frames/archive | `REUSE_DIRECTLY_AFTER_MATERIALIZATION` | Raw replay and deterministic renormalization | Archive must be materialized and every manifest hash verified |
| 2026-08-05 normalized chunks | `WRAP_OR_REBUILD_FROM_RAW` | Feature/replay after deterministic repair | 6,781 equal-sequence ordering issues |
| Session/chunk/checksum manifests | `REUSE_DIRECTLY` | Inventory, integrity, provenance | None after local hash reconciliation |
| NIFTY50 membership/constituents | `REUSE_DIRECTLY_FOR_2026-08-05` | Equal-weight breadth | Only one effective date |
| NIFTY50 fallback weights | `RESTRICTED` | Explicit equal-weight proxy only | Official weights unavailable |
| Offline dataset V3 | `REUSE_FOR_SMOKE_ONLY` | Causal and pipeline tests | LTP-only; no executable quotes/depth |
| Offline dataset V2 | `SUPERSEDE_WITH_REASON` | Historical comparison only | Older semantics |
| 2026-08-03 and 2026-07-14 live captures | `WRAP_WITH_ADAPTER` | Additional live-session replay | Schema, hash and contract coverage audit required |
| Other dated captures | `INVENTORY_PRESENT_NOT_ADMITTED` | None yet | Manifest and schema materialization required |
| 4-byte/tiny placeholder Parquets | `INVALID_OR_QUARANTINE` | None | Not valid data evidence |
| PR #719 implementation/reports | `REUSE_DIRECTLY` | Acquisition, validation and governance logic | Large corpus must be materialized |
| Fresh bounded Upstox smoke | `REQUIRED` | Certify current fetcher on current head | Exactly five current-run populated files and hash reconciliation |

## Exact missing delta

Drive reuse reduces the missing work to the following:

1. **Materialize and verify existing archives**
   - Restore the 459 MB multi-asset archive locally through authenticated Drive sync.
   - Recalculate every manifest SHA-256.
   - Rebuild normalized rows from raw authority or apply a reviewed composite-identity adapter.

2. **Admit every dated live session independently**
   - Require its own manifest, hash set, schema, instrument universe and timestamp coverage.
   - Quarantine empty/tiny placeholders.
   - Do not combine sessions until identity and time semantics agree.

3. **Reach the minimum multi-session corpus**
   - At least 30 completed, independently admitted sessions.
   - Synchronized NIFTY future, selected CE/PE and constituent observations.
   - Point-in-time membership with at least 45 constituent symbols per admitted session.

4. **Obtain executable option authority**
   - Bid, ask, spread, depth, quote age and available quantity at entry and exit.
   - LTP-only outcomes cannot satisfy this requirement.

5. **Reconcile the historical expired-option lane**
   - Materialize the PR #719 corpus if available locally/LFS/Drive.
   - Verify its hashes, schema, centering policy and per-session CE+PE coverage.
   - Fetch only the genuinely missing contracts/sessions after reconciliation.

6. **Run the repaired five-file authenticated smoke**
   - 1 expired future, 2 CE, 2 PE, 2 completed sessions.
   - Exactly five populated current-run files.
   - Successful Parquet/schema/date/contract/hash reconciliation.

## Current authority

```text
DRIVE_RECONCILIATION_PHASE=INVENTORY_AND_CLASSIFICATION_COMPLETE
ARCHIVE_MATERIALIZATION=BLOCKED_BY_CONNECTOR_100MB_DOWNLOAD_LIMIT
RAW_20260805_REUSE=APPROVED_AFTER_LOCAL_HASH_VERIFICATION
NORMALIZED_20260805_DIRECT_REUSE=NO
OFFLINE_V3_PIPELINE_SMOKE=APPROVED
OFFLINE_V3_EXECUTABLE_REPLAY=NO
DORL_VALIDATION_ALLOWED=NO
PSILOR_VALIDATION_ALLOWED=NO
FORMAL_EXTRACTION_APPROVED=NO
EDGE_TESTING_STARTED=NO
MERGE_ALLOWED=NO
```

## Next executable task

The next task is a **local read-only Drive materialization and reconciliation run**, not a broad historical download:

```text
SYNC_EXISTING_DRIVE_ARCHIVES
VERIFY_SESSION_MANIFEST_HASHES
REBUILD_OR_ADAPT_NORMALIZED_ROWS
AUDIT_OLDER_SESSION_MANIFESTS
RECONCILE_PR719_CORPUS
CALCULATE_MISSING_DELTA
RUN_FIVE_FILE_AUTHENTICATED_SMOKE
```

Only after those gates pass may formal missing-delta extraction begin.
