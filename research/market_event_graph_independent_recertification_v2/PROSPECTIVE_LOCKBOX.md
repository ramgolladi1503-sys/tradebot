# MEG Prospective Lockbox V1

## Purpose

Accumulate genuinely fresh Market Event Graph evidence after the consumed 2026-07-22 session without tuning, rediscovery, outcome inspection, or promotion. This is a persistence adapter around the existing read-only MEG runtime observer, not a second research architecture.

## Frozen authority

The graph and thresholds are imported from `core.market_event_graph_contract` and must match exactly. Any authority drift fails closed.

Frozen graph:

```text
breadth_down_1:HIGH
-> index_breadth_divergence:LOW
-> breadth_down_1:LOW
```

The last consumed historical session is `2026-07-22`. Sessions on or before that date are inadmissible to the fresh lockbox.

CAS starts `2026-08-03`.

## Separate lanes

- `PRE_CAS_FRESH`: strictly after 2026-07-22 and before 2026-08-03.
- `POST_CAS`: 2026-08-03 onward.

The lanes are never pooled.

## What gets sealed

For each session, the lockbox stores only:

- frozen research authority and hash;
- sanitized completed constituent/index causal inputs;
- a hash of those inputs;
- the existing read-only runtime observer result;
- explicit false authority flags for outcome opening, tuning, certification, options, shadow, paper, live, and orders.

Unrelated metadata and future-return/profit labels are not copied into the sealed record.

Each session date maps to exactly one immutable JSON record. Re-sealing identical evidence is idempotent. A different payload for an already-sealed date fails closed.

## Milestones

Session counts are descriptive only:

```text
0-4   OBSERVATIONAL_ONLY
5-9   OBSERVATIONAL_MILESTONE
10-19 EARLY_PROSPECTIVE_EVIDENCE
20-44 PRELIMINARY_STABILITY_REVIEW_ELIGIBLE
45+   INDEPENDENT_CERTIFICATION_ELIGIBLE
```

`INDEPENDENT_CERTIFICATION_ELIGIBLE` does not mean certified. At 45+ sessions the separate frozen V2 certification procedure may be run. Its statistical, chronological, and robustness gates remain unchanged.

## Prohibited behavior

The lockbox must not:

- compute P&L, expectancy, win rate, or forward outcomes;
- retune graph thresholds;
- rerun graph discovery;
- use the old consumed holdout as fresh evidence;
- pool PRE_CAS and POST_CAS;
- activate options, shadow, paper, live, or order authority;
- mutate production strategy, risk, ranking, execution, or broker paths.

## Current authority

```text
MEG_HISTORICAL_RECERTIFICATION = PENDING_PHYSICAL_ARCHIVE_RECOMPUTATION
PRE_CAS_FRESH_INDEPENDENT_DATA = INSUFFICIENT
POST_CAS_PROSPECTIVE_LOCKBOX = ACCUMULATING
MEG_EDGE_CERTIFIED = NO
```
