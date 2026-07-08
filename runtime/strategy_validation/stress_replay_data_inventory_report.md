# Stress Replay Data Inventory Report

## .runtime/market_data/ticks_20260703.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## .runtime/market_data/ticks_20260701.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## .runtime/logs/execution_entry_trace.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## .runtime/logs/runtime_startup_lifecycle.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## .runtime/logs/advisory_row_corruption.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## .runtime/logs/rejected_candidates.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## .runtime/logs/advisory_schema_errors.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## .runtime/logs/desks/DEFAULT/blocked_candidates.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## .runtime/logs/desks/DEFAULT/gate_status.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## .runtime/truth_dataset.parquet
- Classification: INSUFFICIENT_SCHEMA
- Rows: 71638
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: ['option_ltp', 'bid_ask', 'depth']
- Blockers: ['DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED', 'DATA_BLOCKED_BID_ASK_MISSING', 'DATA_BLOCKED_DEPTH_MISSING']

## data/ticks/20260702/index_ticks.jsonl
- Classification: TOO_LARGE_NOT_INSPECTED
- Rows: 0
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_TOO_LARGE']

## data/tick_data_20260629.parquet
- Classification: UNDERLYING_ONLY
- Rows: 1500
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: ['option_ltp', 'bid_ask', 'depth']
- Blockers: ['DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED', 'DATA_BLOCKED_BID_ASK_MISSING', 'DATA_BLOCKED_DEPTH_MISSING']

## data/tick_data_20260629.parquet/instrument=NIFTY/567c793fb09242258816bcd4f9e9b07e-0.parquet
- Classification: UNDERLYING_ONLY
- Rows: 375
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: ['option_ltp', 'bid_ask', 'depth']
- Blockers: ['DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED', 'DATA_BLOCKED_BID_ASK_MISSING', 'DATA_BLOCKED_DEPTH_MISSING']

## data/tick_data_20260629.parquet/instrument=SENSEX/567c793fb09242258816bcd4f9e9b07e-0.parquet
- Classification: UNDERLYING_ONLY
- Rows: 375
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: ['option_ltp', 'bid_ask', 'depth']
- Blockers: ['DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED', 'DATA_BLOCKED_BID_ASK_MISSING', 'DATA_BLOCKED_DEPTH_MISSING']

## data/tick_data_20260629.parquet/instrument=BANKNIFTY/567c793fb09242258816bcd4f9e9b07e-0.parquet
- Classification: UNDERLYING_ONLY
- Rows: 375
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: ['option_ltp', 'bid_ask', 'depth']
- Blockers: ['DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED', 'DATA_BLOCKED_BID_ASK_MISSING', 'DATA_BLOCKED_DEPTH_MISSING']

## data/tick_data_20260629.parquet/instrument=INDIAVIX/567c793fb09242258816bcd4f9e9b07e-0.parquet
- Classification: UNDERLYING_ONLY
- Rows: 375
- Metadata Verified: False
- Option Contracts: 0
- Missing Fields: ['option_ltp', 'bid_ask', 'depth']
- Blockers: ['DATA_BLOCKED_INSTRUMENT_METADATA_NOT_VERIFIED', 'DATA_BLOCKED_BID_ASK_MISSING', 'DATA_BLOCKED_DEPTH_MISSING']

## data/ticks/20260702/index_ticks.parquet
- Classification: PARTIAL_STRESS_REPLAY_CAPABLE
- Rows: 1178496
- Metadata Verified: True
- Option Contracts: 62
- Missing Fields: []
- Blockers: ['DATA_BLOCKED_INSTRUMENT_TOKEN_UNRESOLVED']
