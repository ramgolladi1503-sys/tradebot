# Regenerated replay context artifact audit

## Verdict

`BLOCKED_NO_CANDIDATE`

The replay source artifact was regenerated into an isolated parquet file with the updated export fields preserved. The downstream isolated replay bundle proof still did not naturally emit a candidate, so the proof chain remains blocked at candidate generation rather than at source-artifact regeneration.

## Original generator path

The checked-in source artifact is produced by the stress replay inventory exporter:

```bash
python scripts/report_stress_replay_data_inventory.py   --instrument-master <instrument-master-path>   --instrument-master-date 2026-07-02
```

In this worktree, the checked-in token index records the source as:

- `data/ticks/20260702/index_ticks.parquet`
- instrument master path: `.runtime/kite_instruments.json`

That exact upstream raw source file is not present in this checkout, so the isolated regeneration below used the checked-in runtime replay artifact plus the resolved-token index as the available provenance boundary.

## Regenerated isolated artifact

- Input artifact: `runtime/strategy_validation/resolved_option_ticks_20260702.parquet`
- Token index: `runtime/strategy_validation/stress_replay_resolved_option_token_index.json`
- Regenerated parquet: `/tmp/resolved_option_ticks_20260702_regenerated.parquet`

## Regenerated columns

The regenerated parquet includes:

- `source_timestamp`
- `option_type`
- `strike`
- `expiry`
- `replay_context_available_fields`
- `replay_context_missing_fields`
- `replay_context_blockers`

## Replay bundle rerun

Explicit OOS context used:

- `--is-oos false`
- `--oos-label IS`
- `--oos-source explicit_replay_run_context`
- `--partition-id replay-context-proof`
- `--split-name in_sample_replay_probe`

Replay input:

- `/tmp/replay_context_bundle_regenerated_input.jsonl`

Replay command:

```bash
python scripts/run_replay_candidate_handoff.py   --source /tmp/replay_context_bundle_regenerated_input.jsonl   --output-root /tmp/replay_candidate_handoff_regenerated   --run-id regenerated-artifact-001   --strategy-id vwap_reclaim_rejection_v1   --is-oos false   --oos-label IS   --oos-source explicit_replay_run_context   --partition-id replay-context-proof   --split-name in_sample_replay_probe
```

## What changed compared with the old artifact

The old source-artifact blockers were removed from the replay bundle path:

- `missing_source_timestamp`
- `missing_option_type`
- `missing_strike`
- `missing_expiry`
- `missing_is_oos`
- `missing_oos_label`

The explicit OOS context was preserved in the audit payload and did not block the rerun.

## Remaining blockers

The isolated replay bundle still reported:

- `missing_feature_cutoff_ts`
- `missing_earliest_entry_ts`
- `missing_feed_truth_state`
- `missing_feed_truth_reason_code`
- `missing_quote_source`
- `missing_quote_age_sec`

The replay runner itself remained:

- `BLOCKED_NO_CANDIDATE`

## Conclusion

The regenerated artifact proves the updated export boundary now preserves the replay-context fields that were absent in the old parquet. The downstream replay proof is still not candidate-complete because the remaining runtime context fields are not present in this replay slice.
