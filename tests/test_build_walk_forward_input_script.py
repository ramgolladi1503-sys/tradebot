from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from scripts import build_walk_forward_input as wf_input
from scripts import run_walk_forward_kite as wf_kite


def _sample_candles():
    return [
        {
            "date": "2026-02-20T09:15:00+00:00",
            "open": 25000,
            "high": 25010,
            "low": 24995,
            "close": 25005,
            "volume": 1000,
        },
        {
            "date": "2026-02-20T09:20:00+00:00",
            "open": 25005,
            "high": 25020,
            "low": 25000,
            "close": 25015,
            "volume": 1200,
        },
    ]


def test_build_walk_forward_input_writes_csv(monkeypatch, tmp_path):
    out = tmp_path / "nifty.csv"
    monkeypatch.setattr(wf_input.kite_client, "resolve_index_token", lambda symbol: 256265)
    monkeypatch.setattr(wf_input.kite_client, "historical_data", lambda token, frm, to, interval="5minute": _sample_candles())

    report = wf_input.build_walk_forward_input(
        symbol="NIFTY",
        interval="5minute",
        start_dt=datetime(2026, 2, 20, tzinfo=timezone.utc),
        end_dt=datetime(2026, 2, 21, tzinfo=timezone.utc),
        output_path=out,
        chunk_days=60,
    )
    assert report["rows"] == 2
    assert Path(report["output_path"]).exists()
    frame = pd.read_csv(out)
    assert list(frame.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(frame) == 2


def test_build_walk_forward_input_uses_config_token_fallback(monkeypatch, tmp_path):
    out = tmp_path / "fallback.csv"
    seen = {}
    monkeypatch.setattr(wf_input.kite_client, "resolve_index_token", lambda symbol: None)
    monkeypatch.setattr(wf_input.cfg, "INDEX_TOKEN_BY_SYMBOL", {"NIFTY": 256265}, raising=False)

    def _hist(token, frm, to, interval="5minute"):
        seen["token"] = token
        return _sample_candles()

    monkeypatch.setattr(wf_input.kite_client, "historical_data", _hist)
    report = wf_input.build_walk_forward_input(
        symbol="NIFTY",
        interval="5minute",
        start_dt=datetime(2026, 2, 20, tzinfo=timezone.utc),
        end_dt=datetime(2026, 2, 21, tzinfo=timezone.utc),
        output_path=out,
        chunk_days=60,
    )
    assert seen["token"] == 256265
    assert report["instrument_token"] == 256265


def test_build_walk_forward_input_raises_on_empty_history(monkeypatch, tmp_path):
    out = tmp_path / "empty.csv"
    monkeypatch.setattr(wf_input.kite_client, "resolve_index_token", lambda symbol: 256265)
    monkeypatch.setattr(wf_input.kite_client, "historical_data", lambda token, frm, to, interval="5minute": [])

    with pytest.raises(RuntimeError):
        wf_input.build_walk_forward_input(
            symbol="NIFTY",
            interval="5minute",
            start_dt=datetime(2026, 2, 20, tzinfo=timezone.utc),
            end_dt=datetime(2026, 2, 21, tzinfo=timezone.utc),
            output_path=out,
            chunk_days=60,
        )


def test_run_walk_forward_kite_delegates_build_and_run(monkeypatch, tmp_path):
    input_csv = tmp_path / "wf_input.csv"
    pd.DataFrame(
        [
            {
                "timestamp": "2026-02-20T09:15:00+00:00",
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
                "volume": 1,
            }
        ]
    ).to_csv(input_csv, index=False)

    monkeypatch.setattr(
        wf_kite,
        "build_walk_forward_input",
        lambda **kwargs: {"output_path": str(input_csv), "rows": 1, "symbol": "NIFTY", "interval": "5minute", "instrument_token": 256265},
    )
    monkeypatch.setattr(
        wf_kite,
        "run_walk_forward",
        lambda **kwargs: {
            "config": {"window_count": 1},
            "aggregate": {"avg_return": 0.0, "total_trades": 0},
            "artifacts": {"json": "a.json", "csv": "a.csv"},
        },
    )

    result = wf_kite.main(
        [
            "--symbol",
            "NIFTY",
            "--lookback-days",
            "10",
            "--train-window-days",
            "2",
            "--test-window-days",
            "1",
            "--step-days",
            "1",
        ]
    )
    assert result["build_report"]["output_path"] == str(input_csv)
    assert result["summary"]["config"]["window_count"] == 1
