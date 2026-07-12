# Replay context field round-trip audit

## Verdict

`BLOCKED_SOURCE_ARTIFACT_OLD`

The current `runtime/strategy_validation/resolved_option_ticks_20260702.parquet` file does not contain the replay-context fields that were added to the source export boundary later. Because those fields are absent upstream, they cannot survive extraction into JSONL or be passed into the replay bundle without inventing them.

## Source artifact inspected

`runtime/strategy_validation/resolved_option_ticks_20260702.parquet`

Observed columns:

- `local_ts`
- `exchange_timestamp`
- `symbol`
- `instrument_token`
- `last_price`
- `best_bid`
- `best_ask`
- `volume`
- `depth_json`

The source parquet does not contain:

- `source_timestamp`
- `option_type`
- `strike`
- `expiry`
- `replay_context_available_fields`
- `replay_context_missing_fields`
- `replay_context_blockers`

## Round-trip result

### Parquet → extracted JSONL

The replay JSONL row extracted from this parquet can only contain the fields already present in the parquet. Therefore:

- `source_timestamp` is not present
- `option_type` is not present
- `strike` is not present
- `expiry` is not present

### Extracted JSONL → replay runner

Because the extracted JSONL row does not contain those fields, the replay runner cannot pass them into the normalized snapshot or replay bundle without guessing.

### Replay runner → replay bundle

The replay bundle still shows the same upstream gaps:

- `missing_source_timestamp`
- `missing_option_type`
- `missing_strike`
- `missing_expiry`
- `missing_feature_cutoff_ts`
- `missing_earliest_entry_ts`
- `missing_feed_truth_state`
- `missing_feed_truth_reason_code`
- `missing_quote_source`
- `missing_quote_age_sec`

## Where the fields are lost

The fields are not being lost in the runner mapping.

They are absent in the current source parquet itself.

That means:

- not present in parquet: yes
- present in parquet but lost in JSONL extraction: no
- present in JSONL but not passed into normalized snapshot: no
- present in snapshot but not passed into bundle: no

## Required next step

Regenerate `runtime/strategy_validation/resolved_option_ticks_20260702.parquet` from the updated exporter before expecting a round-trip proof.

Until the source artifact is regenerated, the replay-context field round-trip remains blocked honestly.
