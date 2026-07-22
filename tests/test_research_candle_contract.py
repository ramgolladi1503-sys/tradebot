from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from core.research_backtest_integrity import (
    RESEARCH_CANDLE,
    RESEARCH_NON_CANDLE_QUOTE,
    classify_research_parquet_columns,
    load_research_candle_parquet,
    normalize_research_candle_frame,
    resolve_research_candle_symbol,
)


def _candle_frame(symbol: str = "BSE_INDEX|SENSEX") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": ["2026-01-05 09:16:00", "2026-01-05 09:15:00"],
            "symbol": [symbol, symbol],
            "open": [101.0, 100.0],
            "high": [102.0, 101.0],
            "low": [100.0, 99.0],
            "close": [101.5, 100.5],
            "volume": [1000.0, 900.0],
        }
    )


def test_candle_frame_is_normalized_and_symbol_with_underscores_is_preserved(tmp_path):
    path = tmp_path / "BSE_INDEX|SENSEX_20260105.parquet"
    _candle_frame().to_parquet(path)
    classification, frame, symbol = load_research_candle_parquet(path)
    assert classification == RESEARCH_CANDLE
    assert symbol == "BSE_INDEX|SENSEX"
    assert frame is not None
    assert frame["timestamp"].tolist() == [
        pd.Timestamp("2026-01-05 09:15:00"),
        pd.Timestamp("2026-01-05 09:16:00"),
    ]


def test_known_quote_depth_parquet_is_explicitly_non_candle(tmp_path):
    path = tmp_path / "BANKNIFTY 56200 CE 28 JUL 26.parquet"
    pd.DataFrame(
        {
            "ts": [1783578300.0],
            "token": [12345],
            "symbol": ["BANKNIFTY 56200 CE 28 JUL 26"],
            "ltp": [100.0],
            "bid": [99.5],
            "ask": [100.5],
        }
    ).to_parquet(path)
    classification, frame, symbol = load_research_candle_parquet(path)
    assert classification == RESEARCH_NON_CANDLE_QUOTE
    assert frame is None
    assert symbol is None


def test_partial_ohlc_schema_fails_closed():
    with pytest.raises(ValueError, match="partial candle schema"):
        classify_research_parquet_columns(["timestamp", "open", "high", "close"])


def test_unknown_schema_fails_closed():
    with pytest.raises(ValueError, match="unrecognized research parquet schema"):
        classify_research_parquet_columns(["ts", "value"])


def test_duplicate_candle_timestamps_fail_closed():
    frame = _candle_frame()
    frame.loc[1, "timestamp"] = frame.loc[0, "timestamp"]
    with pytest.raises(ValueError, match="timestamps contain duplicates"):
        normalize_research_candle_frame(frame, source="duplicate.parquet")


def test_filename_fallback_uses_rightmost_date_separator():
    frame = _candle_frame().drop(columns=["symbol"])
    assert resolve_research_candle_symbol(
        frame,
        source=Path("BSE_INDEX|SENSEX_20260105.parquet"),
    ) == "BSE_INDEX|SENSEX"
