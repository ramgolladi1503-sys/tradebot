# Observation-First Pattern Atlas V1

Research-only campaign. No broker calls, order actions, strategy activation, or live authorization.

## Objective

Discover recurring market geometry and higher-order state sequences directly from historical data before attaching direction, entry, exit, target, stop, P&L, or strategy names.

The campaign order is fixed:

1. inventory and certify source coverage;
2. separate pre-CAS and post-CAS closing regimes;
3. build normalized whole-session trajectories;
4. discover whole-day archetypes without outcomes;
5. discover multi-scale subsequence motifs without outcomes;
6. freeze stable shapes using observation/replication recurrence only;
7. inspect matched failure analogues;
8. formulate hypotheses;
9. attach outcomes only after the pattern contract is frozen;
10. validate chronologically and keep all survivors shadow-only.

## Relationship to the prior campaign

`research/outcome-blind-pattern-observation-v1` is useful prior art. It clusters timestamp-level states and freezes stable two-/three-state transitions. This campaign extends that direction to:

- whole-day trajectory clustering;
- 5/10/15/30/60-minute motif discovery;
- change-point phase segmentation;
- nearest historical analogues;
- empirical retracement distributions;
- pattern-of-pattern graphs;
- a separately governed CAS lane beginning 2026-08-03.

No prior strategy result is inherited as evidence.

## Stage 0: corpus inventory

Run:

```bash
python scripts/run_observation_first_pattern_atlas_inventory_v1.py \
  --repo-root . \
  --search-root research/local_evidence_consolidation_v1 \
  --output-root runtime/research/observation_first_pattern_atlas_v1/inventory
```

The inventory stage is schema- and metadata-focused. It does not calculate returns or profitability. It emits:

- `observation_contract.json`
- `corpus_inventory.json`
- `cas_regime_inventory.json`
- `DATA_READINESS.md`

## Stage 1: normalized trajectory warehouse

Run only after Stage 0 has produced `corpus_inventory.json`:

```bash
python scripts/run_observation_first_pattern_atlas_trajectory_v1.py \
  --repo-root . \
  --inventory-json runtime/research/observation_first_pattern_atlas_v1/inventory/corpus_inventory.json \
  --family underlying \
  --output-root runtime/research/observation_first_pattern_atlas_v1/trajectory
```

This stage produces two separately governed artifacts:

1. `causal_minute_trajectory.parquet`
   - every feature at timestamp `t` uses information available no later than `t`;
   - no backward filling is allowed;
   - suitable for later prefix and nearest-historical-analogue research.
2. `completed_session_vectors.json`
   - fixed-grid descriptions of completed historical sessions;
   - suitable only for post-close whole-day archetype discovery;
   - explicitly prohibited from being treated as intraday-available evidence.

The causal feature set contains:

- return from session open;
- one-minute log return;
- rolling 15-minute realized volatility;
- rolling 15-minute directional efficiency;
- expanding range and range position;
- causal VWAP distance;
- distance in prior-session ATR units;
- session progress.

Default session quality gates are:

- at least 90% observed-minute coverage;
- no more than five minutes without a real observation;
- coverage beginning within the first 2% of the session;
- coverage extending through at least 98% of the session.

PRE_CAS sessions use a 09:15–15:30 grid. POST_CAS sessions use a 09:15–15:40 grid. They remain explicitly labeled and must not be silently pooled.

Stage 1 emits:

- `trajectory_contract.json`
- `trajectory_summary.json`
- `causal_minute_trajectory.parquet`
- `completed_session_vectors.json`
- `rejected_sessions.json`
- `file_diagnostics.json`

## Stage 2: outcome-blind day archetypes

Run after Stage 1 produces accepted completed-session vectors:

```bash
python scripts/run_observation_first_pattern_atlas_archetypes_v1.py \
  --trajectory-vectors runtime/research/observation_first_pattern_atlas_v1/trajectory/completed_session_vectors.json \
  --output-root runtime/research/observation_first_pattern_atlas_v1/archetypes
```

Each instrument and CAS regime is modelled separately. Chronological blocks are fixed as earliest 60% observation, next 25% replication and latest 15% unopened. Scaling is fitted only on observation sessions.

Candidate models are selected without outcomes using:

- observation silhouette;
- observation and replication occupancy;
- occupancy Jensen-Shannon divergence;
- replication centroid drift;
- minimum cross-session support.

The stage emits `day_archetype_catalog.json` with frozen centroids, stable archetype IDs, representative real sessions and full model-selection diagnostics. See `STAGE_2_DAY_ARCHETYPES.md` for the exact contract.

## Safety boundaries

Forbidden during observation and pattern-freeze stages:

- future returns;
- entry or exit prices;
- targets or stops;
- trade labels;
- win/loss labels;
- P&L, expectancy, profit factor, Sharpe, drawdown;
- direction selection;
- CE/PE trade selection;
- validation or holdout outcome access;
- live or paper authorization.

## CAS boundary

Sessions before `2026-08-03` and sessions on/after `2026-08-03` are separate market regimes.

Post-CAS sessions must not be pooled with historical closing behavior unless the analysis explicitly models the regime boundary. A session is CAS-complete only when trustworthy data extends through at least 15:40 Asia/Kolkata for derivatives, or the lane explicitly declares a cash-auction-only endpoint.

## Current verdict

`ARCHETYPE_STAGE_IMPLEMENTED_NOT_PHYSICALLY_EXECUTED`

The inventory, normalized-trajectory and outcome-blind day-archetype stages are implemented. Focused synthetic governance and causality tests pass. Physical corpus execution remains required before any day-shape cluster, motif or edge can be claimed.
