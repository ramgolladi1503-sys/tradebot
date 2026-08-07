# Stage 3B — PRE-CAS Motif Recertification on Trajectory-Accepted Sessions

## Why this stage exists

The first physical Stage-3 run produced 24 PRE_CAS motifs. Stage-4 deterministic reconstruction later failed closed.

The root cause is now identified: the original motif CLI read the full causal trajectory directly and did not restrict clustering to the Stage-1 trajectory-accepted session universe. Stage 1 accepted 411 sessions and rejected 2 for insufficient native coverage / excessive gaps. Stage 4 correctly reconstructed only the accepted universe, so the frozen cluster counts could not match.

The 24-motif catalog is therefore retained as superseded descriptive evidence, not used for downstream analogue authority.

## Recertification contract

`run_observation_first_pattern_atlas_motif_recertification_v2.py`:

1. reads the pinned physical source directly from the shared Git-LFS object store;
2. verifies exact SHA-256 and byte size;
3. reconstructs the corrected causal index representation in memory;
4. applies the existing Stage-1 native-cadence quality gates;
5. retains only trajectory-accepted sessions;
6. runs the existing outcome-blind motif algorithm unchanged;
7. preserves chronological observation / replication / unopened separation;
8. never scores unopened sessions;
9. writes a new schema-v2 motif catalog and a before/after horizon-count comparison;
10. does not open outcomes, direction, P&L, broker calls, live/paper authority, or post-CAS validation.

## Downstream authority

`run_observation_first_pattern_atlas_analogues_v2.py` rejects legacy motif catalogs. It requires:

- `schema_version = 2`;
- `trajectory_quality_accepted_sessions_only = true`;
- `rejected_sessions_excluded = true`;
- stage authority `trajectory_accepted_native_cadence_motif_recertification_v2`.

The recertified motif count is not required to remain 24. Any change is evidence, not a failure by itself.

## Current status

Implementation and governance tests are committed. Physical recertification is required before matched geometric analogue execution resumes.
