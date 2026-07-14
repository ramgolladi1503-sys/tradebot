# Replay context bundle OOS rerun audit

## Verdict

`BLOCKED_NO_CANDIDATE`

Explicit OOS context is now preserved through the replay-context bundle path, but the real replay row still does not naturally emit a candidate.

## Replay command used

```bash
python scripts/run_replay_candidate_handoff.py \
  --source /tmp/replay_context_bundle_oos_rerun_input.jsonl \
  --output-root /tmp/replay_candidate_handoff_oos_rerun \
  --run-id oos-rerun-001 \
  --strategy-id vwap_reclaim_rejection_v1 \
  --is-oos false \
  --oos-label IS \
  --oos-source explicit_replay_run_context \
  --partition-id replay-context-proof \
  --split-name in_sample_replay_probe
```

## Real input used

- Source artifact: `runtime/strategy_validation/resolved_option_ticks_20260702.parquet`
- Extracted isolated replay row: `/tmp/replay_context_bundle_oos_rerun_input.jsonl`

## Bundle output

- Bundle artifact: `/tmp/replay_context_bundles/oos-rerun-001/replay_context_bundle_0.json`
- Latest bundle artifact: `/tmp/replay_context_bundles/oos-rerun-001/replay_context_bundle_latest.json`

## Stage evidence

| Stage | Proven | Notes |
|---|---:|---|
| Replay input | yes | real row extracted from runtime parquet |
| Normalized snapshot | yes | replay runner built snapshot |
| StrategyContext | yes | replay runner built strategy context |
| Bundle recorder | yes | bundle written in isolated output |
| Candidate emitted | no | `BLOCKED_NO_CANDIDATE` |
| Ranking | no | no ranked candidate existed to accept |
| Handoff persistence | no | no handoff artifact written because candidate emission failed |
| Journal persistence | no | no journal row written because candidate emission failed |

## Blocker comparison

### Old blockers

The earlier bundle audit showed OOS-related blockers:

- `missing_is_oos`
- `missing_oos_label`

### New blockers

The rerun bundle blockers are:

- `missing_earliest_entry_ts`
- `missing_expiry`
- `missing_feature_cutoff_ts`
- `miss-ing_feed_truth_reason_code`
- `missing_feed_truth_state`
- `missing_option_type`
- `missing_quote_age_sec`
- `missing_quote_source`
- `missing_strike`
- `missing_source_timestamp`

### Comparison result

The explicit OOS blockers are gone.

The remaining blockers are still the upstream context gaps that prevent a natural candidate from being emitted:

- `feature_cutoff_ts`
- `earliest_entry_ts`
- `feed_truth_state`
- `feed_truth_reason_code`
- `quote_source`
- `quote_age_sec`
- candidate emission itself

## Explicit OOS context recorded

The bundle now preserves the explicit replay context:

- `is_oos = false`
- `oos_label = IS`
- `oos_source = explicit_replay_run_context`
- `partition_id = replay-context-proof`
- `split_name = in_sample_replay_probe`

## Conclusion

Explicit OOS context is no longer a blocker, but it does not fix the underlying miss-ing replay context required for natural candidate emission.
