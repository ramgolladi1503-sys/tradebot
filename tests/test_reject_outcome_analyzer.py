from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import config as cfg
import core.reject_outcome_analyzer as analyzer


def _base_reject() -> dict:
    return {
        "reject_id": "rej_unit_1",
        "source": "decision_telemetry",
        "symbol": "NIFTY",
        "strike": 25000.0,
        "option_type": "CE",
        "side": "BUY_CALL",
        "reject_ts_epoch_ms": 1_000_000,
        "intended_entry": 100.0,
        "target": 105.0,
        "stop": 95.0,
        "reject_reason": "spread_pct",
        "expiry": "2026-03-05",
        "tradingsymbol": "NIFTY26MAR25000CE",
        "instrument_token": 123456,
    }


def _candles(rows: list[tuple[int, float, float, float, float]]) -> pd.DataFrame:
    payload = []
    for ts_ms, open_px, high_px, low_px, close_px in rows:
        payload.append(
            {
                "time_ms": ts_ms,
                "open": open_px,
                "high": high_px,
                "low": low_px,
                "close": close_px,
                "volume": 1000.0,
            }
        )
    return pd.DataFrame(payload)


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            rows.append(json.loads(raw))
    return rows


def _run(monkeypatch, tmp_path, candles_df: pd.DataFrame) -> tuple[dict, list[dict], dict]:
    out_path = tmp_path / "rejected_trade_outcomes.jsonl"
    summary_path = tmp_path / "rejected_trade_outcomes_summary.json"
    monkeypatch.setattr(cfg, "REJECT_OUTCOMES_LOG_PATH", str(out_path), raising=False)
    monkeypatch.setattr(cfg, "REJECT_OUTCOMES_SUMMARY_PATH", str(summary_path), raising=False)
    monkeypatch.setattr(cfg, "REJECT_OUTCOME_ALLOW_MARKET_HOURS", True, raising=False)
    monkeypatch.setattr(cfg, "REJECT_OUTCOME_CANDLE_SOURCE", "kite", raising=False)
    monkeypatch.setattr(cfg, "REJECT_OUTCOME_CANDLE_INTERVAL", "minute", raising=False)
    monkeypatch.setattr(analyzer, "is_market_open_ist", lambda: False)
    monkeypatch.setattr(
        analyzer,
        "_load_rejected_trades_for_date",
        lambda _day: [_base_reject()],
    )
    monkeypatch.setattr(
        analyzer,
        "_fetch_trade_candles",
        lambda *args, **kwargs: candles_df.copy(),
    )
    result = analyzer.analyze_rejected_trades("2026-02-27", lookahead_minutes=30)
    rows = _read_jsonl(out_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return result, rows, summary


def test_reject_outcome_target_hit_first(monkeypatch, tmp_path):
    candles_df = _candles(
        [
            (1_000_000, 100.0, 102.0, 99.0, 101.0),
            (1_060_000, 101.0, 106.0, 100.0, 105.5),  # target first
            (1_120_000, 105.0, 105.2, 94.0, 95.5),
        ]
    )
    result, rows, summary = _run(monkeypatch, tmp_path, candles_df)
    assert result["status"] == "OK"
    assert result["analyzed"] == 1
    assert rows[-1]["outcome"] == "HIT_TARGET"
    assert rows[-1]["outcome_reason"] == "TARGET_FIRST"
    assert rows[-1]["mfe_points"] > 0
    assert summary["summary_by_reject_reason"]["spread_pct"]["hit_rate"] == 1.0


def test_reject_outcome_stop_hit_first(monkeypatch, tmp_path):
    candles_df = _candles(
        [
            (1_000_000, 100.0, 101.0, 99.8, 100.2),
            (1_060_000, 100.0, 103.0, 94.5, 95.0),  # stop first
            (1_120_000, 95.0, 106.5, 95.0, 105.0),
        ]
    )
    _result, rows, summary = _run(monkeypatch, tmp_path, candles_df)
    assert rows[-1]["outcome"] == "HIT_SL"
    assert rows[-1]["outcome_reason"] == "SL_FIRST"
    assert rows[-1]["mae_points"] < 0
    assert summary["summary_by_reject_reason"]["spread_pct"]["hit_rate"] == 0.0


def test_reject_outcome_neither_hit(monkeypatch, tmp_path):
    candles_df = _candles(
        [
            (1_000_000, 100.0, 102.0, 98.0, 101.0),
            (1_060_000, 101.0, 104.0, 97.2, 102.5),
            (1_120_000, 102.0, 104.5, 96.2, 103.0),
        ]
    )
    _result, rows, summary = _run(monkeypatch, tmp_path, candles_df)
    assert rows[-1]["outcome"] == "NO_HIT"
    assert rows[-1]["outcome_reason"] == "WINDOW_EXPIRED"
    stats = summary["summary_by_reject_reason"]["spread_pct"]
    assert stats["count"] == 1
    assert stats["hit_rate"] == 0.0
