# Strict option replay export adapter

This adapter converts an existing candidate journal plus market tick parquet into a WFA-ready option replay CSV only when the source already contains the required fields or when a field can be derived from a real runtime field without inventing market data.

## Scope

- Source: `.runtime/candidates/candidate_journal.jsonl`
- Market data: `.runtime/market_data/ticks_20260703.parquet`
- Strict export script: `scripts/export_strict_option_replay_wfa.py`
- Export/audit module: `core/option_backtest/strict_export.py`

## Required export contract

The adapter emits the following fields:

- `timestamp`
- `symbol`
- `underlying`
- `option_type`
- `strike`
- `expiry`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `oi`
- `bid`
- `ask`
- `bid_qty`
- `ask_qty`
- `quote_timestamp`
- `quote_ts_epoch`
- `feature_cutoff_ts`
- `signal_ts`
- `earliest_entry_ts`
- `setup_id`
- `regime`
- `is_oos`
- `oos_label`
- `provider`
- `dataset_hash`

It also records:

- `source_file`
- `source_file_sha256`

## Derivation rules

The adapter is fail-closed:

- `feature_cutoff_ts` is preserved from `feature_cutoff_ts` when present, otherwise from a real source snapshot timestamp field already present in the journal row (`snapshot_ts_utc`, `snapshot_ts_iso`, `snapshot_ts`, `snapshot_ts_epoch`, `snapshot_epoch`).
- `signal_ts` is preserved from `signal_ts` when present, otherwise from a real runtime timestamp already present in the journal row (`decision_ts_utc`, `decision_ts_iso`, `created_ts_utc`, `created_at`, `generated_epoch`).
- `earliest_entry_ts` is preserved only from an explicit eligible-entry timestamp already present in the journal row (`earliest_entry_ts`, `entry_ts`, `execution_ts`, `entry_timestamp`, `entry_time`).
- `is_oos` / `oos_label` are preserved when the runtime already carries them. If runtime context is unknown, both remain null and the journal marks `oos_source="unknown_runtime_context"`.
- `quote_timestamp` may be derived from `quote_ts_epoch` or the market tick parquet when present.
- `quote_ts_epoch` may be derived from `quote_timestamp` or the market tick parquet when present.
- `provider` may be set to file-provenance text if the input record does not already provide a value.
- `dataset_hash` may be computed from the source file SHA-256 when the record does not already provide a value.
- OHLCV/OI and executable bid/ask fields are taken from the tick parquet when a minute-aligned market row exists for the candidate symbol.

The adapter does not invent:

- timing provenance
- OOS labels
- bid/ask values
- contract metadata
- OHLC values

## Current readiness interpretation

This adapter is intentionally strict. If the real candidate journal is missing any required field, the export is blocked and the audit report lists the exact missing fields.

That means the adapter can prove readiness only when the source artifacts already contain all strict fields.

Current real-source audit status:

- `.runtime/candidates/candidate_journal.jsonl` remains blocked for strict WFA export until the runtime journal is regenerated with explicit timing provenance and OOS fields on each candidate row.
- The adapter does not invent those fields, so the export remains fail-closed for any existing runtime artifact that still lacks them.
- New journal rows written through `core/candidate_journal.py` now preserve the strict-replay fields when they already exist on the payload and explicitly mark readiness/blockers when they do not.
