import json
import pytest
from pathlib import Path
from datetime import datetime
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.upstox_daily_live_capture_and_stitch import (
    format_depth,
    get_options_subscriptions,
    execute_post_market_stitching,
    get_access_token,
)


def test_format_depth_valid_quotes():
    market_level = {
        "bidAskQuote": [
            {"bidP": 23500.5, "bidQ": 150, "bqo": 3, "askP": 23501.0, "askQ": 225, "aqo": 4},
            {"bidP": 23500.0, "bidQ": 300, "bqo": 5, "askP": 23501.5, "askQ": 100, "aqo": 2},
        ]
    }
    res_str = format_depth(market_level)
    parsed = json.loads(res_str)
    
    assert "bids" in parsed
    assert "asks" in parsed
    assert len(parsed["bids"]) == 2
    assert parsed["bids"][0]["price"] == 23500.5
    assert parsed["bids"][0]["quantity"] == 150
    assert parsed["bids"][0]["orders"] == 3
    assert parsed["asks"][0]["price"] == 23501.0
    assert parsed["asks"][0]["quantity"] == 225


def test_format_depth_empty_quotes():
    market_level = {}
    res_str = format_depth(market_level)
    parsed = json.loads(res_str)
    assert parsed == {"bids": [], "asks": []}


def test_get_options_subscriptions_resolution():
    today_ms = int(datetime.now().timestamp() * 1000)
    
    mock_data = [
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 24000.0, "expiry": today_ms, "instrument_key": "NSE_FO|101", "trading_symbol": "NIFTY 24000 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 24000.0, "expiry": today_ms, "instrument_key": "NSE_FO|102", "trading_symbol": "NIFTY 24000 PE"},
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 24050.0, "expiry": today_ms, "instrument_key": "NSE_FO|103", "trading_symbol": "NIFTY 24050 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 23950.0, "expiry": today_ms, "instrument_key": "NSE_FO|104", "trading_symbol": "NIFTY 23950 PE"},
        {"name": "BANKNIFTY", "instrument_type": "CE", "strike_price": 50000.0, "expiry": today_ms, "instrument_key": "NSE_FO|201", "trading_symbol": "BANKNIFTY 50000 CE"},
        {"name": "SENSEX", "instrument_type": "PE", "strike_price": 78000.0, "expiry": today_ms, "instrument_key": "BSE_FO|301", "trading_symbol": "SENSEX 78000 PE"},
    ]
    df_inst = pd.DataFrame(mock_data)
    prices = {"NIFTY": 24010.0, "BANKNIFTY": 50020.0, "SENSEX": 78040.0}
    
    subs = get_options_subscriptions(df_inst, prices)
    
    assert "NSE_INDEX|Nifty 50" in subs
    assert "NSE_INDEX|Nifty Bank" in subs
    assert "BSE_INDEX|SENSEX" in subs
    assert "NSE_FO|101" in subs
    assert "NSE_FO|102" in subs
    assert "NSE_FO|103" in subs
    assert "NSE_FO|104" in subs
    assert "NSE_FO|201" in subs
    assert "BSE_FO|301" in subs


def test_execute_post_market_stitching_creates_master(tmp_path):
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate 2 sample parquet chunks
    schema = pa.schema([
        ("ts", pa.float64()),
        ("token", pa.string()),
        ("symbol", pa.string()),
        ("ltp", pa.float64()),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("vol", pa.float64()),
        ("oi", pa.float64()),
        ("depth", pa.string())
    ])
    
    chunk1_data = {
        "ts": [1789500000.0, 1789500001.0],
        "token": ["NSE_INDEX|Nifty 50", "NSE_FO|101"],
        "symbol": ["NIFTY 50", "NIFTY 24000 CE"],
        "ltp": [24000.0, 150.0],
        "bid": [0.0, 149.5],
        "ask": [0.0, 150.5],
        "vol": [0.0, 5000.0],
        "oi": [0.0, 10000.0],
        "depth": ["{}", "{}"]
    }
    chunk2_data = {
        "ts": [1789500001.0, 1789500002.0],
        "token": ["NSE_FO|101", "NSE_INDEX|Nifty Bank"],
        "symbol": ["NIFTY 24000 CE", "NIFTY BANK"],
        "ltp": [150.0, 50000.0],
        "bid": [149.5, 0.0],
        "ask": [150.5, 0.0],
        "vol": [5000.0, 0.0],
        "oi": [10000.0, 0.0],
        "depth": ["{}", "{}"]
    }
    
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(chunk1_data), schema=schema), chunks_dir / "chunk_1.parquet")
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(chunk2_data), schema=schema), chunks_dir / "chunk_2.parquet")
    
    date_str = "2026-09-17"
    date_compact = "20260917"
    
    execute_post_market_stitching(date_str, date_compact, tmp_path)
    
    stitched_file = tmp_path / f"upstox_full_ticks_{date_compact}_stitched.parquet"
    summary_file = tmp_path / f"stitching_summary_{date_compact}.json"
    
    assert stitched_file.exists()
    assert summary_file.exists()
    
    df_stitched = pd.read_parquet(stitched_file)
    assert len(df_stitched) == 3
    assert df_stitched.isnull().sum().sum() == 0
    assert list(df_stitched.columns) == ["ts", "token", "symbol", "ltp", "bid", "ask", "vol", "oi", "depth"]
    
    with open(summary_file) as f:
        summary = json.load(f)
        assert summary["total_chunks"] == 2
        assert summary["total_ticks"] == 3
        assert summary["duplicates_removed"] == 1


def test_pipeline_safety_read_only():
    """Verify that live market capture code contains no order placement or modification logic."""
    import scripts.upstox_daily_live_capture_and_stitch as mod
    
    forbidden_terms = ["place_order", "modify_order", "cancel_order", "exit_order", "trade_account"]
    code_text = Path(mod.__file__).read_text()
    
    for term in forbidden_terms:
        assert term not in code_text.lower(), f"Forbidden order term '{term}' found in capture pipeline code"
