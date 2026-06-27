# Existing Data Map for Replay Truth Engine

This document outlines the exact telemetry paths, database tables, and JSONL artifacts where the necessary outcome evidence data is currently logged by TradeBot.

## 1. Candidate Decisions
- **JSONL Path**: `runtime/logs/desks/<desk_id>/candidate_decisions.jsonl` (typically `DEFAULT` desk).
- **Snapshot Path**: `runtime/snapshots/advisory_latest.json`
- **Producer**: `core/runtime_snapshot_producer.py` creates snapshot rows from decisions.

## 2. Ranking Snapshots
- **JSONL Path**: `runtime/logs/ranking_snapshots.jsonl`
- **Database Path**: `runtime/db/trades.db` (Table: `ranking_snapshots`)
- **Producer**: `core/ranking_telemetry.py`

## 3. Option Price Traces
- **Database Path**: `runtime/db/trades.db` (Table: `ticks`)
- **JSONL Path**: `runtime/option_price_trace.jsonl`
- **Producer**: `core/tick_store.py` manages the SQLite ingestion and historical tick querying.

## 4. Quote Truth Snapshots
- **JSONL Path**: `runtime/feed_health_truth_latest.json`
- **Producer**: `core/quote_truth.py` and `core/runtime_snapshot_producer.py`

## 5. Execution Decisions & Blockers
- **JSONL Path**: `runtime/logs/decision_events.jsonl` and `runtime/logs/decision_event_errors.jsonl`
- **Database Path**: `runtime/db/trades.db` (Table: `decision_events`)
- **Producer**: `core/decision_logger.py` handles both JSONL write and SQLite schema. Blockers are captured in `veto_reasons` and `pilot_reasons`.
- **Note**: Blockers are also managed in `core/blocker_lifecycle.py`.

## 6. Regime Snapshots
- **JSONL Path**: `runtime/logs/regime_monitor.jsonl` and `runtime/logs/regime_monitor_status.json`

## 7. Metadata (Strategy ID, Target, Stop, Timestamps)
- Extensively logged in `decision_events` (SQLite) and `runtime/logs/decision_events.jsonl` under `strategy_id`, `instrument_id`, `timestamp_epoch`, and pricing/threshold targets.
- Core schemas defined in `core/trade_schema.py`.
