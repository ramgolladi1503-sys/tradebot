# Agent Review Evidence — Upstox Offline V3 Time and Sequence Repair

## Evidence contract

This review covers only:

- normalized capture sequence validation;
- V3 offline dataset market-session boundary classification;
- deterministic latest-row selection used by the offline generator.

It does not authorize strategy integration, edge validation, broker/order actions, live runtime mutation, or merge.

## Root causes

### Frame sequence

`local_sequence` is incremented once per websocket frame. A single frame can contain updates for many instruments, so equal sequence values across distinct instrument keys are valid.

The prior validator rejected `current <= previous`, producing 6,781 equality-only findings and zero observed backward regressions in the August 5 report.

### Market clock

The V3 generator produced UTC boundaries and compared `boundary.time()` against the Indian market-open literal `09:15`. This excluded valid captured evidence before 09:15 UTC and admitted fresh post-close intervals after 15:30 IST.

### Latest-row identity

`groupby().last()` can select the last non-null value independently for each column and construct a synthetic row. The repair uses deterministic sorting plus `groupby().tail(1)` so all values come from one causal source row.

## Implemented repair

Sequence validation now:

- accepts equal frame ties across different instruments;
- rejects backward sequence regression within a connection;
- identifies exact duplicate `(connection_id, local_sequence, instrument_key)` identities and requires deterministic dedupe;
- rejects conflicting duplicate identities;
- records tie, regression and duplicate counts separately.

V3 generation now:

- converts every boundary to `Asia/Kolkata` before market-clock classification;
- admits only 09:15–15:30 IST continuous-market boundaries;
- excludes startup, stale and post-close boundaries explicitly;
- records UTC and IST boundary timestamps in seam evidence;
- preserves the known 07:29–07:31 UTC stale-gap override;
- uses stable sorting and actual latest source rows.

## Focused regression coverage

Sequence tests prove:

1. equal sequence across distinct instruments is valid;
2. backward sequence is rejected;
3. exact duplicate identity requires dedupe;
4. conflicting duplicate identity is rejected.

Session-clock tests prove:

1. 07:30 UTC is 13:00 IST and belongs to the known stale gap;
2. 07:32 UTC is 13:02 IST and is a continuous-market boundary;
3. 09:15 UTC is 14:45 IST, not Indian market open;
4. 10:01 UTC is 15:31 IST and is excluded from continuous-market research;
5. latest-row selection does not fill a newer row's null field from an older row.

## Acceptance proof still required

- final-head compilation;
- focused tests in both forward and isolated execution;
- repository safety/governance checks;
- rerun the real August 5 validator;
- regenerate V3 from the sealed corpus;
- reconcile regenerated file hashes, interval counts and causal audits;
- independently verify non-null bid/ask coverage before executable replay.

## Current verdict

```text
SEQUENCE_VALIDATOR_IMPLEMENTATION=REPAIRED
V3_TIMEZONE_WINDOW_IMPLEMENTATION=REPAIRED
LATEST_ROW_IDENTITY=REPAIRED
OLD_VALIDATION_REPORT=SUPERSEDED
OLD_V3_DATASET=SUPERSEDED
REAL_CORPUS_REVALIDATION=PENDING
REAL_CORPUS_REGENERATION=PENDING
DATA_READY_FOR_DORL_ONLY=NO
DATA_READY_FOR_PSILOR_PROXY_VALIDATION=NO
EDGE_VALIDATION_ALLOWED=NO
MERGE_ALLOWED=NO
```
