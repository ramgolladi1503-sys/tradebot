# Replay context remaining blockers

## Verdict

`PARTIALLY_DERIVABLE_NOW`

The replay runner can now preserve honest quote provenance from the replay source row and file identity. The remaining blockers are a mix of explicit policy gaps and missing runtime truth artifacts.

## Blocker classification

- `missing_quote_source` → `HONESTLY_DERIVABLE_NOW`
- `missing_quote_age_sec` → `HONESTLY_DERIVABLE_NOW`
- `missing_feature_cutoff_ts` → `REQUIRES_EXPLICIT_REPLAY_POLICY`
- `missing_earliest_entry_ts` → `REQUIRES_EXPLICIT_REPLAY_POLICY`
- `missing_feed_truth_state` → `REQUIRES_RUNTIME_FEED_TRUTH_ARTIFACT`
- `miss-ing_feed_truth_reason_code` → `REQUIRES_RUNTIME_FEED_TRUTH_ARTIFACT`
- `BLOCKED_NO_CANDIDATE` → `NOT_AVAILABLE`

## What is now preserved

For replay slices derived from `runtime/strategy_validation/resolved_option_ticks_20260702.parquet`, the runner now carries:

- `quote_source = replay_source:<source_file_name>`
- `quote_age_sec = 0.0` when both source and exchange timestamps are present on the replay row

These values are replay provenance, not a claim about live market quality.

## What remains intentionally blocked

### Feature cutoff

`feature_cutoff_ts` is not guessed from the source replay timestamp. It requires an explicit replay policy that defines which timestamp is the feature cutoff for the slice.

### Earliest entry

`earliest_entry_ts` requires an explicit replay execution policy. The runner does not infer it from the input row or from candidate creation time.

### Feed truth

`feed_truth_state` and `feed_truth_reason_code` require a real runtime feed-truth artifact that can be joined by timestamp/symbol. The current replay slice does not include that artifact.

### Candidate emission

`BLOCKED_NO_CANDIDATE` remains true because the replay row still does not naturally emit a candidate through the existing ranking path.

## Conclusion

The replay context boundary is closer, but not complete. Quote provenance can be preserved honestly now. The remaining blockers are real policy or artifact gaps and should stay blocked until those inputs exist.
