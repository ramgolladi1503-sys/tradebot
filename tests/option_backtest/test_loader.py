from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from core.option_backtest.loader import load_option_symbol_csv
from core.option_backtest.models import OptionBacktestConfig, ResearchMode


def _base_row(**overrides):
    row = {
        "timestamp": "2026-04-01 09:15:00",
        "symbol": "NIFTY24APR25500CE",
        "open": 100.0,
        "high": 101.0,
        "low": 99.5,
        "close": 100.5,
        "volume": 500,
        "oi": 900,
        "bid": 100.0,
        "ask": 100.5,
        "bid_qty": 50,
        "ask_qty": 50,
        "underlying": "NIFTY",
        "option_type": "CE",
        "strike": 25500,
        "expiry": "2026-04-30",
        "provider": "upstox",
        "dataset_hash": "hash-1",
        "bar_interval": "1m",
        "quote_timestamp": "2026-04-01 09:14:40",
    }
    row.update(overrides)
    return row


def _strict_cfg(path: Path) -> OptionBacktestConfig:
    return OptionBacktestConfig(
        symbol="NIFTY24APR25500CE",
        data_path=path,
        research_mode=ResearchMode.REAL_EXECUTABLE_RESEARCH,
        allow_derived_levels=False,
    )


def test_loader_filters_symbol_and_date_range(tmp_path: Path):
    data_path = tmp_path / "option.csv"
    pd.DataFrame(
        [
            _base_row(),
            _base_row(timestamp="2026-04-02 09:15:00"),
            _base_row(symbol="BANKNIFTY24APR25500CE", timestamp="2026-04-02 09:15:00"),
        ]
    ).to_csv(data_path, index=False)

    df = load_option_symbol_csv(
        data_path=data_path,
        symbol="NIFTY24APR25500CE",
        date_from="2026-04-02",
        date_to="2026-04-02",
        timezone="Asia/Kolkata",
    )

    assert len(df) == 1
    assert str(df.iloc[0]["symbol"]) == "NIFTY24APR25500CE"
    assert bool(df.iloc[0]["has_bid_ask"]) is True


def test_loader_rejects_missing_required_columns(tmp_path: Path):
    data_path = tmp_path / "bad.csv"
    pd.DataFrame([{"timestamp": "2026-04-01 09:15:00", "close": 10}]).to_csv(data_path, index=False)
    with pytest.raises(ValueError, match="missing_required_columns"):
        load_option_symbol_csv(data_path=data_path, symbol="A", date_from=None, date_to=None, timezone="Asia/Kolkata")


def test_loader_strict_rejects_duplicate_timestamps(tmp_path: Path):
    data_path = tmp_path / "dupes.csv"
    pd.DataFrame([_base_row(), _base_row()]).to_csv(data_path, index=False)
    with pytest.raises(ValueError, match="duplicate_timestamps"):
        load_option_symbol_csv(data_path=data_path, symbol="NIFTY24APR25500CE", date_from=None, date_to=None, timezone="Asia/Kolkata", config=_strict_cfg(data_path))


def test_loader_strict_rejects_invalid_ohlc_geometry(tmp_path: Path):
    data_path = tmp_path / "geometry.csv"
    pd.DataFrame([_base_row(low=101.5)]).to_csv(data_path, index=False)
    with pytest.raises(ValueError, match="invalid_ohlc_geometry"):
        load_option_symbol_csv(data_path=data_path, symbol="NIFTY24APR25500CE", date_from=None, date_to=None, timezone="Asia/Kolkata", config=_strict_cfg(data_path))


def test_loader_strict_rejects_missing_required_bid_ask_rows(tmp_path: Path):
    data_path = tmp_path / "quotes.csv"
    pd.DataFrame([_base_row(bid="", ask="")]).to_csv(data_path, index=False)
    with pytest.raises(ValueError, match="missing_required_bid_ask_rows"):
        load_option_symbol_csv(data_path=data_path, symbol="NIFTY24APR25500CE", date_from=None, date_to=None, timezone="Asia/Kolkata", config=_strict_cfg(data_path))


def test_loader_strict_rejects_stale_quote_rows(tmp_path: Path):
    data_path = tmp_path / "stale.csv"
    pd.DataFrame([_base_row(quote_timestamp="2026-04-01 09:10:00")]).to_csv(data_path, index=False)
    with pytest.raises(ValueError, match="stale_quote_rows"):
        load_option_symbol_csv(data_path=data_path, symbol="NIFTY24APR25500CE", date_from=None, date_to=None, timezone="Asia/Kolkata", config=_strict_cfg(data_path))


def test_loader_strict_rejects_post_expiry_rows(tmp_path: Path):
    data_path = tmp_path / "expiry.csv"
    pd.DataFrame([_base_row(timestamp="2026-05-01 09:15:00", quote_timestamp="2026-05-01 09:14:40")]).to_csv(data_path, index=False)
    with pytest.raises(ValueError, match="post_expiry_rows"):
        load_option_symbol_csv(data_path=data_path, symbol="NIFTY24APR25500CE", date_from=None, date_to=None, timezone="Asia/Kolkata", config=_strict_cfg(data_path))


def test_loader_strict_rejects_interval_gaps(tmp_path: Path):
    data_path = tmp_path / "gaps.csv"
    pd.DataFrame([_base_row(), _base_row(timestamp="2026-04-01 09:17:00")]).to_csv(data_path, index=False)
    with pytest.raises(ValueError, match="interval_gaps_detected"):
        load_option_symbol_csv(data_path=data_path, symbol="NIFTY24APR25500CE", date_from=None, date_to=None, timezone="Asia/Kolkata", config=_strict_cfg(data_path))
