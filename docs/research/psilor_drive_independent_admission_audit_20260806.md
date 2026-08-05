# PSILOR Drive Corpus — Independent Admission Audit

**Date:** 2026-08-06  
**Scope:** Evidence already materialized from Google Drive and GitHub.  
**Boundary:** Research only. No merge, strategy change, broker/order action, or edge/profitability claim.

## Principal verdict

```text
SEALED_MANIFEST_RECONCILIATION=PASS
RAW_AUTHORITY=PASS
LEGACY_NORMALIZED_VALIDATION=SUPERSEDED
NORMALIZED_DIRECT_REUSE=NO
OFFLINE_V3_AUTHORITY=SUPERSEDED_REGENERATION_REQUIRED
FRESH_BOUNDED_UPSTOX_SMOKE_REQUIRED=YES
FORMAL_EXTRACTION_APPROVED=NO
DATA_READY_FOR_DORL_ONLY=NO
DATA_READY_FOR_PSILOR_PROXY_VALIDATION=NO
EDGE_VALIDATION_ALLOWED=NO
```

The Drive corpus is genuine and substantial, but the existing normalized validation report and offline V3 derived artifacts cannot be used as admission authority without revalidation/regeneration.

## Manifest and inventory result

The sealed session and normalized chunk manifests reconcile exactly:

```text
SEALED_FILES=11,347
SEALED_BYTES=667,730,913
NORMALIZED_CHUNKS=11,250
NORMALIZED_ROWS=1,315,840
NORMALIZED_BYTES=527,413,368
MISSING_SEALED_PATHS=0
HASH_MISMATCHES=0
DUPLICATE_PATHS=0
DUPLICATE_HASHES=0
NONPOSITIVE_ROW_FILES=0
NONPOSITIVE_SIZE_FILES=0
CHUNK_SEQUENCE_ANOMALY_GROUPS=0
```

The normalized inventory contains 681,043 NIFTY option rows, 16,165 NIFTY future rows, 342,686 equity rows, and 275,946 index rows across NIFTY, BANKNIFTY and INDIA VIX.

## Defect 1 — frame sequence validator

The legacy validation report contains 6,781 sequence findings across 690 files. Independent parsing established:

```text
EQUALITY_CASES=6,781
BACKWARD_REGRESSIONS=0
UNPARSED_CASES=0
```

The capture implementation increments `local_sequence` once per websocket frame and assigns that value to every instrument row decoded from the frame. Equal sequence values across different instruments are therefore expected.

The legacy validator used `current <= previous`, which incorrectly rejected those frame ties. PR #796 now validates sequence by `(connection_id, local_sequence, instrument_key)` identity:

- equal sequence across distinct instruments is accepted;
- backward sequence movement is rejected;
- exact duplicate identities require deterministic dedupe;
- conflicting duplicate identities are rejected.

The old `validation_report.json` remains superseded until the real corpus is rerun through the repaired validator.

## Defect 2 — V3 UTC/IST session boundary

The source corpus starts materially earlier than the derived V3 dataset:

```text
OPTION_SOURCE_START_UTC=2026-08-05T07:25:42.388Z
V3_FIRST_INTERVAL_UTC=2026-08-05T09:15:00Z
V3_LAST_INTERVAL_UTC=2026-08-05T10:29:00Z
```

The V3 generator constructs UTC interval boundaries, then evaluates:

```python
boundary.time() < 09:15
```

That compares a UTC clock with the Indian market-open literal. It misclassifies available evidence from approximately 07:25–09:14 UTC (12:55–14:44 IST) as startup backfill and excludes it.

Consequences:

- the retained 75-row V3 precursor/futures dataset is not representative of the available capture window;
- its internal causality and seam checks remain useful only within the incorrectly truncated window;
- it must be regenerated after an IST-aware boundary repair;
- no edge or response-lag conclusion may be drawn from the retained V3 output.

## Quote authority

A representative option Parquet schema includes `bid_price` and `ask_price`, plus LTP, Greeks, IV, volume and OI. This proves schema presence only. Non-null quote coverage, positive spreads, quote age, executable entry/exit semantics and depth remain unaudited.

The derived V3 option outcomes explicitly use `LTP_ONLY` and contain null bid, ask, spread and depth. They are suitable for pipeline/causality smoke testing only, not executable replay.

## Required next gates

1. Complete PR #796 CI for the repaired sequence validator.
2. Repair the V3 market-session comparison using `Asia/Kolkata` time and add a regression test covering 07:30 UTC = 13:00 IST.
3. Rerun the real normalized corpus through the repaired validator.
4. Regenerate V3 from the full causally available source window.
5. Audit actual bid/ask value coverage and synchronized future/option/constituent overlap.
6. Run the fresh authenticated five-file Upstox smoke on the current PR #795 head.
7. Calculate the missing historical-session delta; at least 30 admitted sessions are still required.

Until those gates pass, the corpus is reusable evidence but not DORL/PSILOR admission evidence.
