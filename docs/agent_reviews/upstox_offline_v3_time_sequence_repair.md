# Agent Review Evidence — Upstox Offline V3 Authority Repair

## Evidence contract

This review covers only:

- normalized capture sequence validation;
- V3 offline dataset market-session boundary classification;
- deterministic latest-row selection;
- point-in-time front-future selection;
- deterministic nearest-expiry ATM option-panel selection.

It does not authorize strategy integration, edge validation, broker/order actions, live runtime mutation, or merge.

## Root causes

### Frame sequence

`local_sequence` is incremented once per websocket frame. A single frame can contain updates for many instruments, so equal sequence values across distinct instrument keys are valid.

The prior validator rejected `current <= previous`, producing 6,781 equality-only findings and zero observed backward regressions in the August 5 report.

### Market clock

The V3 generator produced UTC boundaries and compared `boundary.time()` against the Indian market-open literal `09:15`. This excluded valid captured evidence before 09:15 UTC and admitted fresh post-close intervals after 15:30 IST.

### Latest-row identity

`groupby().last()` can select the last non-null value independently for each column and construct a synthetic row. The repair uses deterministic sorting plus `groupby().tail(1)` so all values come from one causal source row.

### Contract selection

The prior generator selected the lexicographically first future key and the first option keys encountered in the loaded frame. Those rules did not encode point-in-time expiry authority, balanced CE/PE representation or ATM proximity.

The August 5 normalized future corpus contains August and September NIFTY futures, and the old key order happened to select the August front month. That historical result is not evidence that the rule was safe. The subscription authority also contains weekly and monthly option surfaces that require deterministic expiry and moneyness selection.

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
- uses stable sorting and actual latest source rows;
- parses ISO and epoch-millisecond expiry values;
- selects the nearest non-expired NIFTY future by expiry, independent of instrument-key ordering;
- selects the nearest non-expired option expiry at each causal boundary;
- constructs a balanced panel of up to five CE and five PE contracts closest to the current causal spot;
- records contract-selection policy, future key/expiry, option rank and moneyness in durable outputs.

## Focused regression coverage

Four sequence tests prove:

1. equal sequence across distinct instruments is valid;
2. backward sequence is rejected;
3. exact duplicate identity requires dedupe;
4. conflicting duplicate identity is rejected.

Ten V3 authority tests prove:

1. 07:30 UTC is 13:00 IST and belongs to the known stale gap;
2. 07:32 UTC is 13:02 IST and is a continuous-market boundary;
3. 09:15 UTC is 14:45 IST, not Indian market open;
4. 10:01 UTC is 15:31 IST and is excluded from continuous-market research;
5. latest-row selection does not fill a newer row's null field from an older row;
6. expiry parsing accepts ISO, numeric milliseconds and numeric-millisecond strings;
7. front-future selection uses nearest valid expiry rather than key order;
8. expired futures are rejected;
9. the option panel is nearest-expiry, balanced CE/PE and ATM-centered;
10. option selection degrades deterministically when fewer contracts are available.

Total focused regression tests added by this repair: **14**.

## Acceptance proof still required

- final-head compilation;
- focused tests in both forward and isolated execution;
- repository safety/governance checks;
- resolve the draft PR's merge conflict before treating GitHub CI absence as meaningful;
- rerun the real August 5 validator;
- regenerate V3 from the sealed corpus;
- reconcile regenerated file hashes, interval counts, contract identities and causal audits;
- independently verify non-null bid/ask coverage before executable replay.

## Current verdict

```text
SEQUENCE_VALIDATOR_IMPLEMENTATION=REPAIRED
V3_TIMEZONE_WINDOW_IMPLEMENTATION=REPAIRED
LATEST_ROW_IDENTITY=REPAIRED
POINT_IN_TIME_FUTURE_SELECTION=REPAIRED
BALANCED_ATM_OPTION_SELECTION=REPAIRED
FOCUSED_REGRESSION_TESTS_ADDED=14
OLD_VALIDATION_REPORT=SUPERSEDED
OLD_V3_DATASET=SUPERSEDED
REAL_CORPUS_REVALIDATION=PENDING
REAL_CORPUS_REGENERATION=PENDING
DATA_READY_FOR_DORL_ONLY=NO
DATA_READY_FOR_PSILOR_PROXY_VALIDATION=NO
EDGE_VALIDATION_ALLOWED=NO
MERGE_ALLOWED=NO
```
