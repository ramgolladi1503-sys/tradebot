# Replay context source artifact gap

## Verdict

`BLOCKED_UPSTREAM_CONTEXT_PARTIAL`

The source export boundary does not invent missing replay context. It preserves the fields that already exist upstream in the export flow and explicitly marks the remaining replay-context fields as unavailable.

## Source artifact examined

- `runtime/strategy_validation/resolved_option_ticks_20260702.parquet`

Observed columns in the exported parquet:

- `local_ts`
- `exchange_timestamp`
- `symbol`
- `instrument_token`
- `last_price`
- `best_bid`
- `best_ask`
- `volume`
- `depth_json`

## Fields preserved from upstream

The export script can preserve these fields without inventing anything:

- `source_timestamp` from `exchange_timestamp` when present
- `option_type` from instrument master metadata
- `strike` from instrument master metadata
- `expiry` from instrument master metadata

## Fields that remain unavailable upstream

The following replay-context fields are not present in the source parquet or the instrument master metadata used by the export path:

- `feature_cutoff_ts`
- `earliest_entry_ts`
- `is_oos`
- `oos_label`
- `feed_truth_state`
- `feed_truth_reason_code`
- `quote_source`
- `quote_age_sec`

These are recorded as explicit blockers rather than guessed.

## Export boundary behavior

The replay artifact export now reports:

- `replay_context_ready=false`
- `replay_context_available_fields=[source_timestamp, option_type, strike, expiry]`
- `replay_context_missing_fields=[feature_cutoff_ts, earliest_entry_ts, is_oos, oos_label, feed_truth_state, feed_truth_reason_code, quote_source, quote_age_sec]`
- `replay_context_blockers` naming the missing upstream fields

## Conclusion

The source/export boundary is honest now:

- available context is preserved
- missing replay context is not invented
- remaining bundle blockers are upstream data gaps, not exporter omissions
