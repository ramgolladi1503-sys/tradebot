# Filtered Stress Replay Dataset Quality Report
- **Dataset Path:** runtime/strategy_validation/resolved_option_ticks_20260702.parquet
- **Token Index Path:** runtime/strategy_validation/stress_replay_resolved_option_token_index.json
- **Classification:** FILTERED_STRESS_REPLAY_DATASET_BLOCKED
- **Total Rows:** 876127
- **Unique Tokens:** 62
- **Unresolved Tokens Present:** []
- **Missing Columns:** []
- **Blockers:** ['FILTERED_DATASET_INVALID_DEPTH', 'FILTERED_DATASET_INSTRUMENT_MASTER_DATE_UNKNOWN']
- **Warnings:** []
## Date & Time Alignment
- Expected Date from Filename: 2026-07-02
- Actual UTC Start/End: 2026-07-02 05:22:41.003950119+00:00 -> 2026-07-02 15:40:10.860882998+00:00
- Actual IST Start/End: 2026-07-02 10:52:41.003950119+05:30 -> 2026-07-02 21:10:10.860882998+05:30
- Actual Trading Dates (IST): ['2026-07-02']
- Date Alignment OK: True
## Token Index Lineage
- Token Index Lineage Present: True
- Token Index Lineage Verdict: TOKEN_INDEX_LINEAGE_BLOCKED
- Token Index Instrument Master Date: None
- Token Index Instrument Master Date Source: unknown
- Token Index Lineage Blockers: ['TOKEN_INDEX_INSTRUMENT_MASTER_DATE_UNKNOWN']
- Metadata Temporally Valid: False
- Lineage Blockers: ['FILTERED_DATASET_INSTRUMENT_MASTER_DATE_UNKNOWN']
## Session Coverage
- Session Rows (09:15-15:30 IST): 872193
- Outside Session Rows: 3934
- Coverage Ratio: 0.996
## Validation Metrics
- Invalid LTP Rows: 0
- Invalid Bid/Ask Rows: 0
- Invalid Spread Rows: 0
- Invalid Depth Rows: 52
## Spread Summary
- Min: 0.049999999999954525
- Median: 0.6000000000000227
- P95: 4.25
- Max: 21.850000000000136
## Spread-to-LTP Ratio
- Median: 0.0026
- P95: 0.0041
- P99: 0.0062
- Max: 0.0238
- Rows > 20% LTP: 0
- Rows > 50% LTP: 0
## Rows Per Token
- Min: 29
- Median: 15877
- Max: 23356
## Safety Flags
- paper_live_allowed: False
- live_allowed: False
- broker_order_allowed: False
- execution_allowed: False