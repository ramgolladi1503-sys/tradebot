# Hermes Addendum — Issue 7 Prior-Day Capture Recheck

**source_agent:** hermes
**action:** DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
**title:** Classify the September 30 stitched capture for October 1 T-1 use
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Scope

Read-only inspection of the September 30, 2026 stitched capture as a possible prior-session reference for the October 1 session. This addendum does not authorize prerequisite synthesis, network retrieval, source promotion, runtime wiring, or code changes.

## Evidence

The candidate input is:

`/Volumes/TradeBotData/live market capture/2026-09-30/upstox_full_ticks_20260930_stitched.parquet`

SHA-256: `107755a4afa76f84e269d4169bdd56dc31f6347d610fa521b0b55e06ed4e0dfc`
Rows: `3,689,091`
Schema: `ts, token, symbol, ltp, bid, ask, vol, oi, depth`

The run-matched stitch summary is:

`/Volumes/TradeBotData/live market capture/2026-09-30/stitching_summary_20260930.json`

SHA-256: `26e2b435478ab5249da920a89db9988a3ec3f5dd82036f9ffc14882cdf0a6302`
It reports 389 valid chunks and 3,689,091 ticks. The summary's `stitched_at_utc` is `2026-09-30T10:11:42.832006+00:00`.

A bounded PyArrow scan of all rows found no `symbol` containing `FUT`; the schema has no distinct receive timestamp, original source-event ID, or source-payload hash.

## Contract and disposition

- This capture may be used as a deterministic replay/reference input only.
- It does not establish an exact NIFTY futures contract identity or authoritative 15:29 futures close.
- It does not establish the source-event lineage, receive-time authority, pinned prior-session calendar, or 200-session daily-close ancestry required by the existing T-1 contract.
- Do not derive a futures prerequisite from spot/index or option rows, row ordering, or synthetic identifiers.
- Keep Issue 7 `UNKNOWN_T1_SOURCE_AND_MANIFEST_AUTHORITY_NOT_ESTABLISHED`; the existing loader must remain fail-closed.

## Acceptance proof

The GSD evidence update must record the two file hashes, row count, schema, scan method, and explicit replay-only disposition. No source or runtime files may change. Recompute the two hashes and verify the graph/verdict JSON remains parseable after the evidence update.

**Hermes verdict:** bounded read-only evidence update approved. No prerequisite values are authorized by this capture.
