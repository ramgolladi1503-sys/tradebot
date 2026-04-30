from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from core.option_backtest.loader import load_option_symbol_csv


def test_loader_filters_symbol_and_date_range(tmp_path: Path):
    data_path = tmp_path / "option.csv"
    pd.DataFrame(
        [
            {"timestamp": "2026-04-01 09:15:00", "symbol": "A", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 100, "oi": 200, "bid": 10.4, "ask": 10.6},
            {"timestamp": "2026-04-02 09:15:00", "symbol": "A", "open": 11, "high": 12, "low": 10, "close": 11.5, "volume": 120, "oi": 220, "bid": 11.4, "ask": 11.6},
            {"timestamp": "2026-04-02 09:15:00", "symbol": "B", "open": 21, "high": 22, "low": 20, "close": 21.5, "volume": 150, "oi": 230, "bid": 21.4, "ask": 21.6},
        ]
    ).to_csv(data_path, index=False)

    df = load_option_symbol_csv(
        data_path=data_path,
        symbol="A",
        date_from="2026-04-02",
        date_to="2026-04-02",
        timezone="Asia/Kolkata",
    )

    assert len(df) == 1
    assert str(df.iloc[0]["symbol"]) == "A"
    assert bool(df.iloc[0]["has_bid_ask"]) is True


def test_loader_rejects_missing_required_columns(tmp_path: Path):
    data_path = tmp_path / "bad.csv"
    pd.DataFrame([{"timestamp": "2026-04-01 09:15:00", "close": 10}]).to_csv(data_path, index=False)

    with pytest.raises(ValueError, match="missing_required_columns"):
        load_option_symbol_csv(
            data_path=data_path,
            symbol="A",
            date_from=None,
            date_to=None,
            timezone="Asia/Kolkata",
        )
