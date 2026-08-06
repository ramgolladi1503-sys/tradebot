# Stage 2 — Outcome-Blind Day Archetypes

This stage consumes only `completed_session_vectors.json` produced by the normalized trajectory warehouse.

## Purpose

Discover recurring whole-session geometry before reading any future outcome, P&L, direction, trade label, entry, exit, target or stop.

## Lane separation

Models are fitted separately for every:

- instrument;
- `PRE_CAS` regime;
- `POST_CAS` regime.

A small POST_CAS sample is reported as insufficient. It is never pooled into PRE_CAS merely to reach a frequency threshold.

## Chronological blocks

Each eligible lane is divided without shuffling:

1. earliest 60% — observation block;
2. next 25% — replication block;
3. latest 15% — unopened block.

The robust median/IQR scaler is fitted only on the observation block.

## Model selection

Candidate KMeans models are evaluated using only outcome-blind properties:

- observation silhouette;
- observation/replication cluster occupancy;
- Jensen-Shannon occupancy divergence;
- replication centroid drift;
- minimum observation and replication support.

A cluster is stable only when it has:

- at least 10 observation sessions;
- at least 4 replication sessions;
- at least 4% observation share;
- at least 2% replication share;
- normalized replication centroid drift no greater than 2.5.

## Outputs

`day_archetype_catalog.json` contains:

- lane verdicts;
- observation, replication and unopened date ranges;
- selected cluster count;
- stable archetype IDs;
- observation-fitted scaler;
- centroids;
- representative observation sessions;
- representative replication sessions;
- complete model-selection diagnostics;
- semantic hashes and research-only authority flags.

Representative sessions are selected by distance to each centroid. No performance field is used.

## Run

```bash
python scripts/run_observation_first_pattern_atlas_archetypes_v1.py \
  --trajectory-vectors runtime/research/observation_first_pattern_atlas_v1/trajectory/completed_session_vectors.json \
  --output-root runtime/research/observation_first_pattern_atlas_v1/archetypes
```

## Current authority

Implementation and synthetic tests exist. Physical corpus execution is still required.

No archetype, pattern or edge may be claimed until the physical output is generated and independently inspected.
