# Upstox 2026-08-04 Corpus Independent Audit

Overall verdict: `PASS_UPSTOX_20260804_REAL_CORPUS_AUDIT`

## Boundaries

- Offline Upstox replay only.
- Not a Kite live certification.
- Not an option corpus.
- No structural-edge or profitability claim.
- Source evidence was opened read-only and checked for mutation.

## Gates

- `SOURCE_IMMUTABLE`: **PASS**
- `RAW_ZSTD_DECOMPRESSIBLE`: **PASS**
- `NORMALIZED_PARQUET_READABLE`: **PASS**
- `MANIFEST_HASH_LINEAGE`: **PASS**
- `DETERMINISTIC_REPLAY`: **PASS**
- `REPLAY_ROW_RECONCILIATION`: **PASS**
- `BAR_INTERVAL_IDENTITIES`: **PASS**
- `BAR_INTERVAL_CLASSIFICATION`: **PASS**
- `PR786_OFFLINE_REHEARSAL`: **PASS**

## Corpus

- Zstandard chunks: `30`
- Normalized Parquet files: `35`
- Normalized rows: `1041828`
- Unique instruments: `55`
- Timestamp span: `2026-08-04T04:00:06.268966Z` → `2026-08-04T10:05:00.887470Z`

## Replay

- Deterministic comparison: `True`
- Run A semantic SHA: `008ab2227b0913e96237ceb2d5beb9124f9be3cf2485d1812aa9ec06b60ab4ae`
- Run B semantic SHA: `008ab2227b0913e96237ceb2d5beb9124f9be3cf2485d1812aa9ec06b60ab4ae`

## MEG / PR #786 rehearsal

- Accepted bar intervals: `353`
- Rehearsal verdict: `PASS_PR786_OFFLINE_REHEARSAL`
- Authority snapshots: `353`
- Primary evaluations: `353`
- Duplicate successful exports: `0`
- Canonical seal gate: `True`

## Next live session

Ready for fresh governed Kite session: `True`

A fresh Kite market-hours run remains mandatory even when every offline gate passes.
