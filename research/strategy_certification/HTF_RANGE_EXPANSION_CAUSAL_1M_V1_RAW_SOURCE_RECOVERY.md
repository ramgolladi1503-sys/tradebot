# HTF_RANGE_EXPANSION_CAUSAL_1M_V1 — Raw Source Recovery Gate

Status: PRE-CERTIFICATION DATA RECOVERY ONLY

Research only. Runtime authority NONE. Broker actions prohibited. No validation/locked outcomes may be read.

## Why this gate exists

The derived file `canonical_nifty_1minute.parquet` is no longer present locally. The candidate has not been frozen and no outcome-bearing execution occurred.

Historical evidence preserves the exact raw-source lineage used to construct that missing derived file:

- selected source manifest:
  `research/local_evidence_consolidation_v1/worktrees/ml-meta-labeling-sprint-v1/research/unified_nifty_underlying_feature_warehouse_v1/selected_source_manifest.json`
- artifact-recorded physical SHA256 of selected source manifest:
  `fbf74e66664b92712c451769c94da47ef54f73acbadb208e01d3449bd50be192`
- selected raw sessions: 441
- expected derived 1m rows: 164745
- expected derived semantic SHA256:
  `cf7a7c0e385e5f1ccefec772853b7b7b7acbea9c64e7a79c29e36e256a80646c`
- expected complete sessions: 441
- expected timestamp range: 2024-09-26 09:15 Asia/Kolkata through 2026-07-21 15:29 Asia/Kolkata

The selected manifest lists, for each session:

- date
- exact historical source path
- exact raw-file SHA256
- expected rows in target (375)
- repair action

Typical raw path form:

`/Users/madhuram/tradebot/runtime/upstox_candidate_replay/YYYYMMDD/underlying/NIFTY_YYYYMMDD.parquet`

## Legal recovery path

1. Parse the committed selected-source manifest. Do not manually substitute dates or paths.
2. For each of all 441 selected entries:
   - test the recorded path first;
   - if absent, search `/Users/madhuram` and `/Volumes/TradeBotData` for a file whose **physical SHA256 exactly equals that entry's recorded SHA256**;
   - do not accept filename/date similarity without hash equality.
3. Produce an inventory with one row per selected session:
   - date
   - expected path
   - resolved path
   - expected SHA256
   - observed SHA256
   - expected rows
   - observed rows
   - status = EXACT_MATCH | MISSING | HASH_MISMATCH | ROW_MISMATCH
4. Recovery may proceed only if all 441 entries are EXACT_MATCH.
5. Reconstruct the derived canonical 1m frame from those exact raw files under the historical frozen data contract:
   - NIFTY spot index only
   - 09:15–15:29 Asia/Kolkata
   - 375 bars per complete session
   - bar-open timestamp semantics
   - completed bars only
   - no future filling
   - no cross-session forward filling
   - no synthetic holiday/session filling
   - duplicate timestamp+symbol is a hard failure
   - sort chronologically
6. Independently verify:
   - rows = 164745
   - sessions = 441
   - incomplete sessions = 0
   - duplicate rows = 0
   - OHLC violations = 0
   - 1m/5m reconciliation = PASS
   - semantic SHA256 = `cf7a7c0e385e5f1ccefec772853b7b7b7acbea9c64e7a79c29e36e256a80646c`
7. Only if the semantic SHA matches exactly may the rebuilt derived parquet become the physical source for `HTF_RANGE_EXPANSION_CAUSAL_1M_V1`.
8. Persist the rebuilt parquet outside Git and write a new provenance manifest containing:
   - all 441 raw source hashes
   - aggregate manifest hash
   - rebuilt physical SHA256
   - semantic SHA256
   - rows/sessions/time range
   - reconstruction code SHA256
   - reconstruction environment/package versions
9. Only after this data gate passes may the previously defined 352 DEV / 89 LOCKED partition and candidate freeze be created.

## Fail-closed outcomes

If any of the 441 raw source files is missing or hash-mismatched:

`KERNEL_STATE=ROBUSTNESS_REQUIRED`

`REASON=RAW_ONE_MINUTE_SOURCE_SET_INCOMPLETE`

Do not replace missing source files by refetching under this identity. A refetch is new source authority and therefore requires a new dataset/candidate identity.

If all 441 raw source files match but reconstructed semantic SHA differs:

`KERNEL_STATE=ROBUSTNESS_REQUIRED`

`REASON=HISTORICAL_CANONICALIZATION_NOT_REPRODUCED`

No candidate freeze or outcome access is authorized by this recovery document itself.
