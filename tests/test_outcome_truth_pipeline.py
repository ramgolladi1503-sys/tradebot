from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import config as cfg
from core.outcome_truth_pipeline import assess_outcome_truth, run_outcome_truth_pipeline


def _iso(ts_epoch: float) -> str:
    return datetime.fromtimestamp(float(ts_epoch), tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _seed_db(db_path: Path, now_epoch: float) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT,
                timestamp_epoch REAL,
                timestamp_iso TEXT,
                realized_pnl REAL,
                r_multiple_realized REAL,
                outcome_label TEXT,
                outcome_grade TEXT,
                exit_time TEXT,
                exit_price REAL,
                exit_reason TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_events (
                trade_id TEXT PRIMARY KEY,
                timestamp_epoch REAL,
                ts TEXT,
                symbol TEXT,
                champion_proba REAL,
                challenger_proba REAL,
                pnl_horizon_15m REAL,
                realized_pnl REAL
            )
            """
        )
        conn.execute("DELETE FROM trades")
        conn.execute("DELETE FROM decision_events")
        trade_ts = now_epoch - 300.0
        conn.execute(
            """
            INSERT INTO trades (
                trade_id,
                timestamp_epoch,
                timestamp_iso,
                realized_pnl,
                r_multiple_realized,
                outcome_label,
                outcome_grade,
                exit_time,
                exit_price,
                exit_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "T-1",
                trade_ts,
                _iso(trade_ts),
                120.0,
                1.2,
                "WIN",
                "A",
                _iso(trade_ts + 60.0),
                101.5,
                "target",
            ),
        )
        conn.execute(
            """
            INSERT INTO decision_events (
                trade_id,
                timestamp_epoch,
                ts,
                symbol,
                champion_proba,
                challenger_proba,
                pnl_horizon_15m,
                realized_pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "T-1",
                trade_ts,
                _iso(trade_ts),
                "NIFTY",
                0.62,
                0.58,
                None,
                None,
            ),
        )
        conn.commit()


def test_outcome_truth_pipeline_reconciles_and_builds_truth(monkeypatch, tmp_path):
    now_epoch = 1_800_000_000.0
    db_path = tmp_path / "trades.db"
    truth_path = tmp_path / "truth_dataset.parquet"
    _seed_db(db_path, now_epoch)
    decision_jsonl = tmp_path / "decision_events.jsonl"
    decision_jsonl.write_text("", encoding="utf-8")

    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "TRUTH_DATASET_PATH", str(truth_path), raising=False)
    monkeypatch.setattr(cfg, "DECISION_LOG_PATH", str(decision_jsonl), raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_WINDOW_DAYS", 30, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_OUTCOME_ROWS", 1, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_SHADOW_ROWS", 1, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_DECISION_ROWS_FOR_LINK_RATE", 1, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_OUTCOME_LINK_RATE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "OUTCOME_RECONCILE_ENABLE", True, raising=False)

    payload = run_outcome_truth_pipeline(
        strict=True,
        now_epoch=now_epoch,
        db_path=db_path,
        truth_path=truth_path,
        refresh=True,
        write_status=False,
    )

    assert payload["status"] == "PASS"
    assert int(payload["metrics"]["outcome_rows"]) >= 1
    assert int(payload["metrics"]["shadow_rows"]) >= 1
    assert payload["reconcile"]["upserted"] >= 1

    with sqlite3.connect(str(db_path)) as conn:
        cur = conn.execute("SELECT COUNT(1) FROM outcomes")
        assert int(cur.fetchone()[0] or 0) >= 1
        cur = conn.execute("SELECT realized_pnl, pnl_horizon_15m FROM decision_events WHERE trade_id='T-1'")
        row = cur.fetchone()
        assert row is not None
        assert row[0] is not None
        assert row[1] is not None


def test_assess_outcome_truth_reports_insufficient_rows(monkeypatch, tmp_path):
    now_epoch = 1_800_000_000.0
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS outcomes (trade_id TEXT, timestamp_epoch REAL, r_multiple REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS decision_events (trade_id TEXT, timestamp_epoch REAL)")
        conn.commit()
    truth_path = tmp_path / "truth_dataset.parquet"

    monkeypatch.setattr(cfg, "ACCEPTANCE_WINDOW_DAYS", 30, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_OUTCOME_ROWS", 2, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_SHADOW_ROWS", 2, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_DECISION_ROWS_FOR_LINK_RATE", 1, raising=False)
    monkeypatch.setattr(cfg, "ACCEPTANCE_MIN_OUTCOME_LINK_RATE", 0.8, raising=False)

    payload = assess_outcome_truth(
        strict=False,
        now_epoch=now_epoch,
        db_path=db_path,
        truth_path=truth_path,
    )
    assert payload["status"] == "DEGRADED"
    assert "OUTCOME_ROWS_INSUFFICIENT" in payload["blockers"]
    assert "SHADOW_ROWS_INSUFFICIENT" in payload["blockers"]

