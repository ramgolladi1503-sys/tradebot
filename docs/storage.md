# Storage Subsystem

## Purpose
This subsystem stores only decision-critical telemetry to keep disk usage bounded while preserving replay value.

## What Is Stored
- Events (`~/.trading_bot/data/events/events_YYYY-MM-DD.jsonl.gz`)
- Snapshots (`~/.trading_bot/data/snapshots/snapshots_YYYY-MM-DD.jsonl.gz`)

### Event types
- `candidate_created`
- `gate_rejected`
- `trade_accepted`
- `trade_exited`
- `sla_violation`
- `disk_critical`

Each event includes:
- `event_id`, `ts_utc`, `desk`, `mode`, `symbols`, `event_type`
- decision fields (`gate_name`, `reason_code`, `confidence`, `config_version`)
- compact `features_summary` (flattened + capped)
- source metadata (`data_source`, `latency_ms`, `missing_fields`)

### Snapshot shape
Each snapshot includes:
- `snapshot_id`, `ts_utc`
- `instrument` (`symbol`, optional `instrument_id`, optional `instrument_token`)
- `ltp`, `bid`, `ask`, `spread_pct`
- `depth_summary` (top-level only)
- optional `oi`, `volume`, `iv`
- `capture_reason` (`around_event` or `periodic`)

## What Is NOT Stored
- Access tokens or API keys
- Secrets/passwords
- Full depth ladder payloads
- Account identifiers

## Directory Structure
- `~/.trading_bot/data/events/`
- `~/.trading_bot/data/snapshots/`

Directories are created with `0700` permissions; files are written with `0600` where possible.

## Snapshot Policy
Snapshots are captured around meaningful events:
- default: `gate_rejected`, `trade_accepted`, `trade_exited`
- optional: `candidate_created` (`STORAGE_SNAPSHOTS_FOR_CANDIDATE_CREATED=true`)

Window defaults:
- `STORAGE_SNAPSHOT_N_BEFORE=2`
- `STORAGE_SNAPSHOT_N_AFTER=2`
- `STORAGE_SNAPSHOT_INTERVAL_MS=500`

## Disk Guardrails
- If free disk `< STORAGE_MIN_FREE_PCT` (default `10`): snapshots disabled; events continue.
- If free disk `< STORAGE_CRITICAL_FREE_PCT` (default `5`): only minimal events are stored, and one `disk_critical` event is emitted.

Storage never throws into bot runtime; it degrades safely.

## Retention and Compaction
Defaults:
- Keep full events + snapshots for last `7` days.
- Keep events-only up to `30` days.
- Delete snapshots older than `7` days.
- Compress uncompressed daily JSONL files.
- Remove temp fragments (`.tmp`, `.part`, `.fragment`).

Run retention:
```bash
python -m core.storage.retention --dry-run
python -m core.storage.retention --run
```

## Notes for Future Export
Parquet export is not implemented here. For future ETL:
1. Read daily `.jsonl.gz` files.
2. Normalize nested fields (`instrument`, `capture_reason`, `metadata`).
3. Write partitioned Parquet by `date` and `event_type`.
