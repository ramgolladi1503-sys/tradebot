from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from config import config as cfg
from core.reject_telemetry import (
    append_reject_telemetry,
    clear_reject_telemetry_memory,
    evaluate_reject_shadow_once,
)
from core.tick_store import init_ticks, insert_tick


def _fetch_shadow_row(db_path: Path, candidate_key: str) -> dict:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT candidate_key, snapshot_id, status, end_price, hypothetical_pnl, rejection_reasons_json
            FROM reject_shadow
            WHERE candidate_key = ?
            """,
            (candidate_key,),
        ).fetchone()
    assert row is not None
    return dict(row)


def test_reject_shadow_hypothetical_pnl_is_deterministic(monkeypatch, tmp_path):
    db_path = tmp_path / "DEFAULT.sqlite"
    reject_log_dir = tmp_path / "logs" / "reject_telemetry"
    shadow_jsonl = tmp_path / "logs" / "reject_shadow.jsonl"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "REJECT_TELEMETRY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "REJECT_TELEMETRY_LOG_DIR", str(reject_log_dir), raising=False)
    monkeypatch.setattr(cfg, "REJECT_SHADOW_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "REJECT_SHADOW_TABLE", "reject_shadow", raising=False)
    monkeypatch.setattr(cfg, "REJECT_SHADOW_HORIZON_MIN", 1, raising=False)
    # Keep append-time background evaluator idle; this test controls evaluation time explicitly.
    monkeypatch.setattr(cfg, "REJECT_SHADOW_EVAL_INTERVAL_SEC", 10_000_000_000.0, raising=False)
    monkeypatch.setattr(cfg, "REJECT_SHADOW_EVAL_BATCH_SIZE", 200, raising=False)
    monkeypatch.setattr(cfg, "REJECT_SHADOW_JSONL_PATH", str(shadow_jsonl), raising=False)
    clear_reject_telemetry_memory()

    base = 1_770_000_000.0
    init_ticks()
    insert_tick(ts=base + 10, token=111, last_price=109.0, volume=10, oi=5)
    insert_tick(ts=base + 50, token=111, last_price=120.0, volume=12, oi=5)
    insert_tick(ts=base + 10, token=222, last_price=95.0, volume=10, oi=5)
    insert_tick(ts=base + 55, token=222, last_price=80.0, volume=12, oi=5)

    append_reject_telemetry(
        {
            "candidate_key": "cand_buy_1",
            "snapshot_id": "snap_buy",
            "timestamp_epoch_ms": int(base * 1000.0),
            "symbol": "NIFTY",
            "trade_side": "BUY",
            "entry_price": 100.0,
            "instrument_token": 111,
            "reject_reason": "stale_option_quote",
            "rejection_reasons": ["stale_option_quote", "spread_pct"],
            "horizon_minutes": 1,
        }
    )
    append_reject_telemetry(
        {
            "candidate_key": "cand_sell_1",
            "snapshot_id": "snap_sell",
            "timestamp_epoch_ms": int(base * 1000.0),
            "symbol": "BANKNIFTY",
            "trade_side": "SELL",
            "entry_price": 100.0,
            "instrument_token": 222,
            "reject_reason": "spread_pct",
            "rejection_reasons": ["spread_pct"],
            "horizon_minutes": 1,
        }
    )

    first_eval = evaluate_reject_shadow_once(now_epoch=base + 70, force=True)
    assert first_eval["status"] == "ok"
    assert int(first_eval["evaluated"]) >= 2

    buy_row = _fetch_shadow_row(db_path, "cand_buy_1")
    sell_row = _fetch_shadow_row(db_path, "cand_sell_1")
    assert buy_row["status"] == "EVALUATED"
    assert sell_row["status"] == "EVALUATED"
    assert float(buy_row["end_price"]) == 120.0
    assert float(sell_row["end_price"]) == 80.0
    assert float(buy_row["hypothetical_pnl"]) == 20.0
    assert float(sell_row["hypothetical_pnl"]) == 20.0
    assert json.loads(buy_row["rejection_reasons_json"]) == ["stale_option_quote", "spread_pct"]
    assert json.loads(sell_row["rejection_reasons_json"]) == ["spread_pct"]

    second_eval = evaluate_reject_shadow_once(now_epoch=base + 90, force=True)
    assert second_eval["status"] == "ok"
    assert int(second_eval["processed"]) == 0

    buy_row_2 = _fetch_shadow_row(db_path, "cand_buy_1")
    sell_row_2 = _fetch_shadow_row(db_path, "cand_sell_1")
    assert float(buy_row_2["hypothetical_pnl"]) == 20.0
    assert float(sell_row_2["hypothetical_pnl"]) == 20.0

    assert shadow_jsonl.exists()
    text = shadow_jsonl.read_text(encoding="utf-8")
    assert "cand_buy_1" in text
    assert "cand_sell_1" in text
