# Blocked Certification Datasets

## resolved_option_ticks_20260702
- Path: runtime/strategy_validation/resolved_option_ticks_20260702.parquet
- Status: BLOCKED_FOR_CERTIFICATION
- Allowed Use: RESEARCH_DEBUG_ONLY
- Reason: Token-index lineage is blocked because instrument-master date is unknown, and quote spread outlier rate is too high.
- Next Action: Capture a fresh date-aligned instrument master and option tick/depth dataset on the next market day.
### Blockers:
  * FILTERED_DATASET_INSTRUMENT_MASTER_DATE_UNKNOWN
  * FILTERED_DATASET_SPREAD_OUTLIER_RATE_TOO_HIGH

### Safety Flags:
- certification_allowed: False
- candidate_replay_allowed: False
- paper_live_allowed: False
- live_allowed: False
- broker_order_allowed: False
- execution_allowed: False
