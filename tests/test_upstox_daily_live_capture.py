import json
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

    assert parsed["bids"][0]["price"] == 23500.5
    assert parsed["bids"][0]["quantity"] == 150
    assert parsed["bids"][0]["orders"] == 3
    assert parsed["asks"][0]["price"] == 23501.0
    assert parsed["asks"][0]["quantity"] == 225
    assert parsed["asks"][0]["orders"] == 4
    assert parsed["bids"][1]["price"] == 23500.0
    assert parsed["asks"][1]["price"] == 23501.5


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

    assert subs.get("NSE_INDEX|Nifty 50") == "NIFTY 50"
    assert subs.get("NSE_INDEX|Nifty Bank") == "NIFTY BANK"
    assert subs.get("BSE_INDEX|SENSEX") == "SENSEX"
    assert subs.get("NSE_FO|101") == "NIFTY 24000 CE"
    assert subs.get("NSE_FO|102") == "NIFTY 24000 PE"
    assert subs.get("NSE_FO|103") == "NIFTY 24050 CE"
    assert subs.get("NSE_FO|104") == "NIFTY 23950 PE"
    assert subs.get("NSE_FO|201") == "BANKNIFTY 50000 CE"
    assert subs.get("BSE_FO|301") == "SENSEX 78000 PE"


def test_execute_post_market_stitching_creates_master(tmp_path):
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

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

    assert stitched_file.is_file() == True
    assert summary_file.is_file() == True

    df_stitched = pd.read_parquet(stitched_file)
    assert int(df_stitched.shape[0]) == 3
    assert int(df_stitched.isnull().sum().sum()) == 0
    assert tuple(df_stitched.columns) == ("ts", "token", "symbol", "ltp", "bid", "ask", "vol", "oi", "depth")
    assert float(df_stitched["ltp"].iloc[0]) == 24000.0
    assert str(df_stitched["token"].iloc[0]) == "NSE_INDEX|Nifty 50"

    with open(summary_file) as f:
        summary_report = json.load(f)
        assert summary_report["total_chunks"] == 2
        assert summary_report["total_ticks"] == 3
        assert summary_report["duplicates_removed"] == 1
        assert summary_report["unique_tokens"] == 3
        assert summary_report["date"] == "2026-09-17"


def test_token_retrieval_fallback():
    token = get_access_token()
    assert isinstance(token, str) == True


def test_refresh_late_day_option_subscriptions():
    from core.upstox_capture.late_day_option_refresh import refresh_late_day_option_subscriptions

    class MockStreamer:
        def __init__(self):
            self.subscribed_keys = []

        def subscribe(self, keys, mode="full"):
            self.subscribed_keys.extend(keys)

    today_ms = int(datetime.now().timestamp() * 1000)
    mock_data = [
        # Existing morning subscriptions around 23500
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 23500.0, "expiry": today_ms, "instrument_key": "NSE_FO|101", "trading_symbol": "NIFTY 23500 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 23500.0, "expiry": today_ms, "instrument_key": "NSE_FO|102", "trading_symbol": "NIFTY 23500 PE"},
        # New strikes around 23200 (after 300 pt drop)
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 23200.0, "expiry": today_ms, "instrument_key": "NSE_FO|201", "trading_symbol": "NIFTY 23200 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 23200.0, "expiry": today_ms, "instrument_key": "NSE_FO|202", "trading_symbol": "NIFTY 23200 PE"},
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 23150.0, "expiry": today_ms, "instrument_key": "NSE_FO|203", "trading_symbol": "NIFTY 23150 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 23150.0, "expiry": today_ms, "instrument_key": "NSE_FO|204", "trading_symbol": "NIFTY 23150 PE"},
    ]
    df_inst = pd.DataFrame(mock_data)
    streamer = MockStreamer()
    subscriptions = {
        "NSE_FO|101": "NIFTY 23500 CE",
        "NSE_FO|102": "NIFTY 23500 PE",
    }

    # Spot price drops to 23172.0 (ATM 23150 or 23200)
    new_count = refresh_late_day_option_subscriptions(
        streamer=streamer,
        subscriptions=subscriptions,
        df_inst=df_inst,
        current_spot_price=23172.0
    )

    # Must subscribe 23200 and 23150 strikes which were missing
    assert new_count == 4
    assert "NSE_FO|201" in subscriptions
    assert "NSE_FO|202" in subscriptions
    assert "NSE_FO|203" in subscriptions
    assert "NSE_FO|204" in subscriptions
    assert len(streamer.subscribed_keys) == 4
    # Existing morning subscriptions must remain intact
    assert "NSE_FO|101" in subscriptions
    assert "NSE_FO|102" in subscriptions

