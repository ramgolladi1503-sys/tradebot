# Stage 3 — Outcome-Blind Native-Cadence Motifs

## Authority

Research only. No broker calls, order actions, direction selection, option selection, entry, exit, stop, target, P&L, future return, validation outcome or live authorization.

## Input authority

The stage accepts only the corrected continuous-index causal trajectory emitted by `run_observation_first_pattern_atlas_index_trajectory_v2.py`.

Required fields:

- `timestamp`
- `instrument`
- `session_date`
- `regime`
- `price`
- `volume`
- `causal_vwap`
- `session_progress`
- `observed_this_minute`

Only rows where `observed_this_minute=true` are eligible. Forward-filled one-minute rows are excluded from motif geometry.

## Regime boundary

`PRE_CAS` and `POST_CAS` are independent lanes. They are never pooled during scaling, clustering, recurrence measurement or freezing.

POST_CAS remains insufficient for statistical motif freezing until enough complete sessions accumulate. A small post-CAS sample must return an insufficiency verdict rather than borrow pre-CAS evidence.

## Horizons

Motifs are evaluated independently at:

- 5 minutes
- 10 minutes
- 15 minutes
- 30 minutes
- 60 minutes

The required number of native observations is derived from the measured native cadence. For a five-minute source, a 15-minute motif contains four inclusive observations.

## Motif representation

Each window contains robustly normalized components:

1. path from the first observation;
2. native-bar return sequence;
3. return acceleration;
4. expanding-window range position;
5. causal VWAP distance.

Descriptive metadata is retained separately:

- net log return;
- amplitude;
- realized volatility;
- directional efficiency;
- start and end session progress.

These descriptors describe geometry. They are not outcome labels and do not authorize a trade direction.

## Anti-duplication sampling

Highly overlapping windows can create false recurrence by counting nearly identical windows repeatedly.

The stage therefore uses:

- a default stride of half the window length in native points;
- at most 20 deterministically spaced windows per session and horizon;
- no random window sampling.

This preserves time-of-day coverage while preventing a single smooth session from dominating motif frequency through hundreds of near-duplicates.

## Chronological blocks

For each eligible instrument/regime lane:

- earliest 60% of sessions: observation;
- next 25%: replication;
- latest sessions: unopened;
- at least 10 sessions remain unopened where the lane size permits.

The robust scaler and cluster model are fitted only on observation windows. Replication windows are predicted using the frozen observation transform and centroids. Unopened sessions are not scored.

## Model selection

Candidate MiniBatchKMeans models use `K=5..10` by default.

Selection evidence includes:

- observation silhouette on a deterministic sample of at most 1,000 windows;
- observation and replication occupancy;
- occupancy Jensen-Shannon divergence;
- replication centroid drift;
- cross-session recurrence support.

A motif cluster is frozen only when all gates pass:

- observation share at least 1%;
- replication share at least 0.5%;
- at least 20 observation sessions;
- at least 8 replication sessions;
- replication/observation share ratio between 0.25 and 4.0;
- normalized replication centroid drift no greater than 2.5.

## Outputs

- `native_motif_catalog.json`
- `MOTIF_RESULT.md`

The catalog includes full model-selection records, frozen motif IDs, observation and replication descriptors, representative real occurrences, semantic hashes and the unopened-session policy.

## Validation

Focused synthetic tests verify:

1. outcome-like columns fail closed;
2. windows do not cross session boundaries;
3. native cadence determines point counts;
4. chronological splits preserve an unopened tail;
5. insufficient post-CAS data fails without fitting a model;
6. intentionally repeating synthetic geometry can pass observation/replication freezing gates.

## Current verdict

`NATIVE_MOTIF_STAGE_IMPLEMENTED_NOT_PHYSICALLY_EXECUTED`

No real NIFTY motif is certified until the corrected physical continuous-index trajectory has run and the resulting catalog has been independently inspected.
