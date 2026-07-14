# Replay context runtime field mapping

## Purpose

Document which replay-context fields are already truthfully available in runtime recorder paths, which are derivable from real runtime fields, and which remain unavailable upstream.

This is a recorder-boundary report. It does not invent values and does not weaken replay gates.

## Field classification

### AVAILABLE_NOW

These fields are already present in runtime recorder inputs and can be preserved without guessing:

- `quote_source`
  - Source paths: `quote_source`, nested replay context / top executable snapshot payloads
  - Runtime provenance: `core.market_data`, `core.orchestrator`, `core.review_queue`, `core.runtime_snapshot_producer`
- `quote_age_sec`
  - Source paths: `quote_age_sec`
  - Runtime provenance: `core.market_data`, `core.orchestrator`, `core.review_queue`, `core.runtime_snapshot_producer`
- `feed_truth_state`
  - Source paths: `feed_truth_state`, `feed_health_state`
  - Runtime provenance: `core.feed_runtime`, `core.runtime_truth_integrity`, `core.feed_recovery_runtime`, `core.orchestrator`
- `feed_truth_reason_code`
  - Source paths: `feed_truth_reason_code`, `feed_health_reason_code`
  - Runtime provenance: `core.feed_runtime`, `core.runtime_truth_integrity`, `core.feed_recovery_runtime`, `core.orchestrator`
- `option_type`
  - Source paths: `option_type`, `type`
  - Runtime provenance: candidate/runtime handoff payloads, instrument metadata, candidate journal rows
- `strike`
  - Source paths: `strike`
  - Runtime provenance: candidate/runtime handoff payloads, instrument metadata, candidate journal rows
- `expiry`
  - Source paths: `expiry`, `expiry_date`
  - Runtime provenance: candidate/runtime handoff payloads, instrument metadata, candidate journal rows

### DERIVABLE_FROM_REAL_RUNTIME_FIELD

These are valid only when a real upstream runtime field exists:

- `feature_cutoff_ts`
  - Derived from `snapshot_ts_epoch`/`snapshot_epoch` when an explicit snapshot cutoff timestamp is not already present.
  - Must not be guessed from decision/write time.
- `signal_ts`
  - May be derived from explicit decision/create/generated runtime timestamps.
  - Source paths: `signal_ts`, `decision_ts_utc`, `decision_ts_iso`, `created_ts_utc`, `created_at`, `generated_epoch`
- `earliest_entry_ts`
  - Must come from an explicit eligible-entry timestamp if present.
  - Source paths: `earliest_entry_ts`, `entry_ts`, `execution_ts`, `entry_timestamp`, `entry_time`

### NOT_AVAILABLE_YET

These are still missing in the current replay source artifact boundary and must remain blocked when absent:

- `is_oos`
- `oos_label`

Current runtime paths do not reliably carry an explicit OOS partition/context value for the replay source row used by the source-artifact export boundary. If future runtime records carry this field, the recorder may preserve it; otherwise the field must remain null with a blocker.

## Recorder guarantees

- Missing values are recorded as null and produce blockers.
- `feature_cutoff_ts` is never guessed from `created_at` or other write-time fields.
- `earliest_entry_ts` is never guessed when no explicit eligible-entry timestamp exists.
- `is_oos` and `oos_label` are never fabricated from unrelated runtime state.
- Feed and quote metadata are preserved only when present in the runtime payload.

## Conclusion

The recorder boundary is now strict enough to preserve all currently available replay-context fields and to fail closed on the remaining upstream gaps.
