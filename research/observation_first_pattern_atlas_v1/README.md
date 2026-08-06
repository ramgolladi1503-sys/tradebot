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

`IMPLEMENTATION_STARTED`

The branch currently establishes the evidence inventory and governance layer. No pattern or edge has been claimed.
