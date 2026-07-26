from __future__ import annotations

import pandas as pd

from research.option_e2e_recertification_v4.ce_pe_dataset_preflight_v1.build_preflight import (
    _inspect_dataframe,
)


def test_underlying_data_cannot_pass_as_option_data(tmp_path) -> None:
    path = tmp_path / "nifty_1m.parquet"
    pd.DataFrame(
        {
            "timestamp": ["2026-07-14 09:15:00"],
            "open": [1.0],
            "high": [1.0],
            "low": [1.0],
            "close": [1.0],
        }
    ).to_parquet(path)

    result = _inspect_dataframe(path, {})

    assert result["strict_loader_acceptance"] is False
    assert "missing_ce_coverage" in result["rejection_reasons"]
    assert "missing_pe_coverage" in result["rejection_reasons"]


def test_ltp_without_bid_ask_cannot_pass(tmp_path) -> None:
    path = tmp_path / "option_ticks.parquet"
    pd.DataFrame(
        {
            "ts": [1784006404.0],
            "instrument_key": ["NSE_FO|1"],
            "ltp": [10.0],
            "instrument_type": ["CE"],
            "strike_price": [25000.0],
            "expiry": ["2026-07-30"],
            "provider": ["test"],
            "dataset_hash": ["abc"],
            "bar_interval": ["1m"],
        }
    ).to_parquet(path)

    result = _inspect_dataframe(path, {})

    assert result["strict_loader_acceptance"] is False
    assert "missing_bid_ask_columns" in result["rejection_reasons"]


def test_ce_only_reports_missing_pe(tmp_path) -> None:
    path = tmp_path / "option_ticks.parquet"
    pd.DataFrame(
        {
            "ts": [1784006404.0],
            "instrument_key": ["NSE_FO|1"],
            "bid": [9.9],
            "ask": [10.1],
            "instrument_type": ["CE"],
            "strike_price": [25000.0],
            "expiry": ["2026-07-30"],
            "provider": ["test"],
            "dataset_hash": ["abc"],
            "bar_interval": ["1m"],
        }
    ).to_parquet(path)

    result = _inspect_dataframe(path, {})

    assert result["strict_loader_acceptance"] is False
    assert "missing_pe_coverage" in result["rejection_reasons"]
