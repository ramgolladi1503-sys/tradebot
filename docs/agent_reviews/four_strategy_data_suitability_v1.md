# Four Strategy Data Suitability v1

## Purpose

This phase implements a deterministic, read-only historical data suitability pipeline for the frozen four-strategy contract bundle:

- `opening_range_retest_v1`
- `compression_breakout_v1`
- `trend_pullback_v1`
- `vwap_reclaim_rejection_v1`

It discovers local datasets, hashes them, inspects schema and session integrity, classifies required-field coverage, preserves provenance, and writes an immutable JSON manifest plus SHA-256 sidecar. It fails closed on unreadable or unverifiable inputs.

## Implementation scope

### Files changed

- `research/strategy_validation/__init__.py`
- `research/strategy_validation/data_suitability.py`
- `scripts/build_four_strategy_dataset_manifest.py`
- `tests/test_four_strategy_dataset_manifest.py`
- `docs/agent_reviews/four_strategy_dataset_manifest_v1.json`
- `docs/agent_reviews/four_strategy_dataset_manifest_v1.json.sha256`

### What changed

- Added a reusable `research.strategy_validation.data_suitability` module for:
  - dataset discovery
  - SHA-256 hashing
  - schema inspection
  - timestamp/session integrity inspection
  - field coverage classification
  - strategy-level suitability classification
  - immutable manifest emission
  - explicit error-row recording for unreadable files
- Added a command-line wrapper at `scripts/build_four_strategy_dataset_manifest.py`.
- Added focused tests that prove:
  - the frozen bundle loads and matches its sidecar
  - real candle files are complete but still fail for exact VWAP truth
  - real tick files have volume truth but lack completed-bar history
  - manifest discovery is deterministic and excludes `manifests/`
  - malformed parquet-named files are recorded as unverifiable instead of crashing
- Generated an immutable manifest and SHA-256 sidecar.

## Data roots used

The manifest was built from explicit local roots:

- `/Users/madhuram/tradebot/runtime/upstox_candidate_replay`
- `/Users/madhuram/tradebot/.runtime/market_data`

The isolated worktree itself did not contain the runtime corpus; the data lives in the shared checkout and was referenced read-only.

## Corpus summary

### Top-level manifest facts

- `schema_version`: `1`
- `code_commit`: `4206d9ba13ec8e5c24b5160f399dd780df21b0a7`
- `architecture_decision`: `KEEP_CANONICAL_AND_LIVE_PHASE2_SEPARATE`
- `bundle_sha256`: `71b01ae3e32044c119692411be1f4d748f03ba50a800ce4d97baca3b853793e9`
- `dataset_count`: `1213`
- `corpus_status`: `INVALID_DUE_TO_DATA`
- `corpus_blockers`: `atr_long`, `atr_short`, `completed_bar_history`, `range_width_pct`, `spot_ltp`, `vwap`

### Dataset kinds discovered

- `CANDLE_OHLCV`: `1021`
- `TICK_WITH_DEPTH`: `132`
- `TICK_QUOTE`: `50`
- `INVALID_OR_UNVERIFIABLE`: `8`
- `UNKNOWN`: `2`

### Suitability outcomes

- `INVALID_DUE_TO_DATA`: `1205`
- `INVALID_OR_UNVERIFIABLE`: `8`

## Strategy-level suitability

All four frozen strategies were classified as `INVALID_DUE_TO_DATA` across the corpus.

### `opening_range_retest_v1`

- status: `INVALID_DUE_TO_DATA`
- suitable datasets: `0`
- partial datasets: `1213`
- blocking fields: `completed_bar_history`, `spot_ltp`, `vwap`
- reason: completed 1m history exists in candle files, but exact VWAP truth is unavailable and the candle corpus carries zero volume

### `compression_breakout_v1`

- status: `INVALID_DUE_TO_DATA`
- suitable datasets: `0`
- partial datasets: `1213`
- blocking fields: `atr_long`, `atr_short`, `range_width_pct`, `spot_ltp`, `vwap`
- reason: candle files provide range and ATR history, but they carry zero volume and do not provide exact VWAP truth

### `trend_pullback_v1`

- status: `INVALID_DUE_TO_DATA`
- suitable datasets: `0`
- partial datasets: `1213`
- blocking fields: `completed_bar_history`, `spot_ltp`, `vwap`
- reason: completed 1m history exists in candle files, but exact VWAP truth is unavailable and the candle corpus carries zero volume

### `vwap_reclaim_rejection_v1`

- status: `INVALID_DUE_TO_DATA`
- suitable datasets: `0`
- partial datasets: `1213`
- blocking fields: `completed_bar_history`, `spot_ltp`, `vwap`
- reason: tick files provide real volume on some sessions, but they do not provide completed 1m bar history

## Exact corpus observations

### Candle files

The primary candle corpus contains completed 1-minute sessions with ordered timestamps, but it does not provide exact VWAP truth because the volume column is zero throughout the examined candle files.

Representative file:

- `/Users/madhuram/tradebot/runtime/upstox_candidate_replay/20260709/underlying/NSE_INDEX|Nifty 50_20260709.parquet`

Observed properties:

- `row_count`: `375`
- `timestamp_range`: `2026-07-09T09:15:00` to `2026-07-09T15:29:00`
- `interval`: `1minute`
- `session_integrity.status`: `COMPLETE`
- `volume_truth_status`: `ZERO_VOLUME`
- `data_kind`: `CANDLE_OHLCV`

### Tick files

The local tick corpus contains volume truth, but it does not satisfy the completed-bar-history contract required by the ORB-style and trend-style strategies.

Representative file:

- `/Users/madhuram/tradebot/.runtime/market_data/ticks_20260707_132935.parquet`

Observed properties:

- `data_kind`: `TICK_QUOTE`
- `volume_truth_status`: `HAS_VOLUME`
- `completed_bar_history`: `UNAVAILABLE`
- `vwap`: `DERIVABLE`

## Failure handling

The pipeline does not abort on malformed or unreadable parquet-named files. Instead, it records them as explicit unverifiable rows.

Observed `inspection_error` examples were `ArrowInvalid` read failures, including:

- `Parquet magic bytes not found in footer`
- `Parquet file size is 4 bytes, smaller than the minimum file footer (8 bytes)`

These files were classified as:

- `suitability_status`: `INVALID_OR_UNVERIFIABLE`
- `exclusion_reason`: `read_error:<exception repr>`

## Manifest immutability

The manifest is written as canonical JSON with sorted keys and a trailing newline, then sealed by a SHA-256 sidecar in the format:

```text
<sha256>  <filename>
```

This was verified for:

- `docs/agent_reviews/four_strategy_dataset_manifest_v1.json`
- `docs/agent_reviews/four_strategy_dataset_manifest_v1.json.sha256`

## Tests and validation

### Focused test result

- `python -m pytest -q tests/test_four_strategy_dataset_manifest.py`
- result: `5 passed`

### Static checks

- `python -m py_compile research/strategy_validation/__init__.py research/strategy_validation/data_suitability.py scripts/build_four_strategy_dataset_manifest.py tests/test_four_strategy_dataset_manifest.py`
- result: passed

### Full suite

Not rerun for this documentation update.

## Explicit non-claims

This work does **not** claim:

- backtest edge
- profitability
- WFA validity
- execution readiness
- live readiness
- production certification

It only establishes deterministic historical data suitability and fail-closed corpus classification for the frozen four-strategy contract bundle.
