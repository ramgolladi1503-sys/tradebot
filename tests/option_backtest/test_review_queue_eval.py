from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from core.option_backtest.review_queue_eval import evaluate_review_queue_snapshot


def test_review_queue_snapshot_eval_splits_execute_and_blocked(tmp_path: Path):
    db_path = tmp_path / "eval.sqlite"
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE ticks (
                timestamp TEXT,
                instrument_token INTEGER,
                last_price REAL,
                volume INTEGER,
                oi INTEGER,
                timestamp_epoch REAL,
                timestamp_iso TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE depth_snapshots (
                timestamp TEXT,
                instrument_token INTEGER,
                depth_json TEXT,
                timestamp_iso TEXT,
                timestamp_epoch REAL
            )
            """
        )
        conn.executemany(
            "INSERT INTO ticks VALUES (?,?,?,?,?,?,?)",
            [
                ("2026-04-30T07:35:00Z", 123, 100.0, 10, 100, 1777544100.0, "2026-04-30T07:35:00Z"),
                ("2026-04-30T07:36:00Z", 123, 111.0, 12, 100, 1777544160.0, "2026-04-30T07:36:00Z"),
                ("2026-04-30T07:35:00Z", 456, 50.0, 10, 100, 1777544100.0, "2026-04-30T07:35:00Z"),
                ("2026-04-30T07:36:00Z", 456, 39.0, 12, 100, 1777544160.0, "2026-04-30T07:36:00Z"),
            ],
        )
        conn.commit()

    review_queue_path = tmp_path / "review_queue.json"
    review_queue_path.write_text(
        json.dumps(
            [
                {
                    "tradingsymbol": "NIFTYEXEC",
                    "instrument_token": 123,
                    "final_action": "EXECUTE",
                    "execution_status": "executable",
                    "side": "BUY",
                    "entry": 100.0,
                    "target": 110.0,
                    "stop": 95.0,
                    "snapshot_ts_epoch": 1777544100.0,
                    "confidence_final": 0.8,
                },
                {
                    "tradingsymbol": "NIFTYBLOCK",
                    "instrument_token": 456,
                    "final_action": "QUEUE_ONLY",
                    "execution_status": "queue_only",
                    "side": "BUY",
                    "entry": 50.0,
                    "target": 55.0,
                    "stop": 40.0,
                    "snapshot_ts_epoch": 1777544100.0,
                    "confidence_final": 0.4,
                },
            ]
        ),
        encoding="utf-8",
    )

    payload = evaluate_review_queue_snapshot(
        review_queue_path=review_queue_path,
        db_path=db_path,
        symbol_prefix="NIFTY",
    )

    assert payload["summary"]["execute_intent"]["target_hit"] == 1
    assert payload["summary"]["blocked"]["stop_hit"] == 1
