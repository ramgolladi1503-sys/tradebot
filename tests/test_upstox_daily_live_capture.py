import json
import threading
from pathlib import Path
from datetime import datetime
import pytest
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.upstox_daily_live_capture_and_stitch import (
    format_depth,
    get_options_subscriptions,
    execute_post_market_stitching,
    get_access_token,
    get_today_data_dir,
    flush_buffer,
    DEFAULT_TICK_SCHEMA,
    PRIMARY_BASE_DIRS,
    FALLBACK_BASE_DIR,
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
    assert subs.get("NSE_INDEX|India VIX") == "INDIA VIX"
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


def test_refresh_late_day_option_subscriptions_multi_underlying_sensex():
    from core.upstox_capture.late_day_option_refresh import refresh_late_day_option_subscriptions

    class MockStreamer:
        def __init__(self):
            self.subscribed_keys = []

        def subscribe(self, keys, mode="full"):
            self.subscribed_keys.extend(keys)

    today_ms = int(datetime.now().timestamp() * 1000)
    mock_data = [
        # Morning SENSEX strikes around 73000
        {"name": "SENSEX", "instrument_type": "CE", "strike_price": 73000.0, "expiry": today_ms, "instrument_key": "BSE_FO|73000CE", "trading_symbol": "SENSEX 73000 CE"},
        {"name": "SENSEX", "instrument_type": "PE", "strike_price": 73000.0, "expiry": today_ms, "instrument_key": "BSE_FO|73000PE", "trading_symbol": "SENSEX 73000 PE"},
        # Afternoon SENSEX strikes around 74100 (after 1100 pt rally)
        {"name": "SENSEX", "instrument_type": "CE", "strike_price": 74100.0, "expiry": today_ms, "instrument_key": "BSE_FO|1115540", "trading_symbol": "SENSEX 74100 CE"},
        {"name": "SENSEX", "instrument_type": "PE", "strike_price": 74100.0, "expiry": today_ms, "instrument_key": "BSE_FO|1101701", "trading_symbol": "SENSEX 74100 PE"},
    ]
    df_inst = pd.DataFrame(mock_data)
    streamer = MockStreamer()
    subscriptions = {
        "BSE_FO|73000CE": "SENSEX 73000 CE",
        "BSE_FO|73000PE": "SENSEX 73000 PE",
    }

    # SENSEX spot rallies to 74,150.0 (ATM 74100 or 74200)
    new_count = refresh_late_day_option_subscriptions(
        streamer=streamer,
        subscriptions=subscriptions,
        df_inst=df_inst,
        current_spot_prices={"SENSEX": 74150.0}
    )

    # Must subscribe 74100 CE and PE which were missing
    assert new_count == 2
    assert "BSE_FO|1115540" in subscriptions
    assert "BSE_FO|1101701" in subscriptions
    assert "BSE_FO|1115540" in streamer.subscribed_keys
    assert subscriptions["BSE_FO|1115540"] == "SENSEX 74100 CE"
    assert subscriptions["BSE_FO|1101701"] == "SENSEX 74100 PE"


def test_stitching_merges_existing_master_without_deleting_it(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock_token")

    data_dir = tmp_path / "2026-09-28"
    chunks_dir = data_dir / "chunks"
    chunks_dir.mkdir(parents=True)

    # 1. Existing master file
    existing_master_data = {
        "ts": [1790566100.0],
        "token": ["NSE_INDEX|Nifty 50"],
        "symbol": ["NIFTY 50"],
        "ltp": [23100.0],
        "bid": [23099.0],
        "ask": [23101.0],
        "vol": [10.0],
        "oi": [100.0],
        "depth": ["{}"],
    }
    master_file = data_dir / "upstox_full_ticks_20260928_stitched.parquet"
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(existing_master_data)), master_file)
    assert master_file.exists()

    # 2. New chunk
    new_chunk_data = {
        "ts": [1790566200.0],
        "token": ["BSE_INDEX|SENSEX"],
        "symbol": ["SENSEX"],
        "ltp": [73500.0],
        "bid": [73490.0],
        "ask": [73510.0],
        "vol": [20.0],
        "oi": [200.0],
        "depth": ["{}"],
    }
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(new_chunk_data)), chunks_dir / "chunk_afternoon.parquet")

    # 3. Execute stitching
    execute_post_market_stitching("2026-09-28", "20260928", data_dir)

    # 4. Verify master file STILL exists (was NOT deleted during chunk pruning!)
    assert master_file.exists(), "Master stitched parquet was erroneously unlinked during chunk pruning!"
    assert master_file.stat().st_size > 0

    df_stitched = pq.read_table(master_file).to_pandas()
    assert len(df_stitched) == 2
    assert set(df_stitched["symbol"]) == {"NIFTY 50", "SENSEX"}

    # Chunks dir should be pruned
    assert not chunks_dir.exists()


def test_get_today_data_dir_fail_closed_when_mounts_missing(monkeypatch, tmp_path):
    # Simulate completely missing / disconnected external mounts
    missing_mounts = [tmp_path / "mount_missing_1", tmp_path / "mount_missing_2"]
    monkeypatch.setattr(
        "scripts.upstox_daily_live_capture_and_stitch.PRIMARY_BASE_DIRS",
        missing_mounts,
    )

    # 1. Default invocation must fail-closed raising RuntimeError
    with pytest.raises(RuntimeError, match="Fail-closed: None of PRIMARY_BASE_DIRS exist"):
        get_today_data_dir()

    # 2. Explicit allow_local_fallback=False must also fail-closed
    with pytest.raises(RuntimeError, match="Fail-closed: None of PRIMARY_BASE_DIRS exist"):
        get_today_data_dir(allow_local_fallback=False)


def test_get_today_data_dir_allows_local_fallback_when_explicit(monkeypatch, tmp_path):
    missing_mounts = [tmp_path / "mount_missing"]
    local_fallback = tmp_path / "custom_fallback"
    monkeypatch.setattr(
        "scripts.upstox_daily_live_capture_and_stitch.PRIMARY_BASE_DIRS",
        missing_mounts,
    )
    monkeypatch.setattr(
        "scripts.upstox_daily_live_capture_and_stitch.FALLBACK_BASE_DIR",
        local_fallback,
    )

    data_dir = get_today_data_dir(allow_local_fallback=True)
    today_str = datetime.now().strftime("%Y-%m-%d")

    assert data_dir.exists()
    assert data_dir == local_fallback / today_str


def test_get_today_data_dir_mount_present(monkeypatch, tmp_path):
    active_mount = tmp_path / "Volumes" / "TradeBotMount"
    active_mount.mkdir(parents=True)
    monkeypatch.setattr(
        "scripts.upstox_daily_live_capture_and_stitch.PRIMARY_BASE_DIRS",
        [tmp_path / "missing", active_mount],
    )

    data_dir = get_today_data_dir()
    today_str = datetime.now().strftime("%Y-%m-%d")

    assert data_dir.exists()
    assert data_dir == active_mount / today_str


def test_flush_buffer_preserves_tick_buffer_on_write_failure(monkeypatch, tmp_path):
    ticks = [
        {"ts": 100.0, "token": "NSE_FO|101", "symbol": "NIFTY 24000 CE", "ltp": 150.0, "bid": 149.0, "ask": 151.0, "vol": 100.0, "oi": 200.0, "depth": "{}"},
        {"ts": 101.0, "token": "NSE_FO|102", "symbol": "NIFTY 24000 PE", "ltp": 80.0, "bid": 79.0, "ask": 81.0, "vol": 50.0, "oi": 150.0, "depth": "{}"},
    ]
    tick_buffer = list(ticks)
    buffer_lock = threading.Lock()
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(parents=True)

    # Simulate disk failure / error in pq.write_table
    def failing_write_table(*args, **kwargs):
        raise OSError("Disk full / I/O error during parquet chunk write")

    monkeypatch.setattr(pq, "write_table", failing_write_table)

    # Calling flush_buffer must NOT drop ticks
    flush_buffer(tick_buffer, buffer_lock, chunks_dir, "20261015")

    # Both ticks must remain in tick_buffer for future retry
    assert len(tick_buffer) == 2
    assert tick_buffer[0]["token"] == "NSE_FO|101"
    assert tick_buffer[1]["token"] == "NSE_FO|102"
    # No parquet chunk should be created
    assert list(chunks_dir.glob("*.parquet")) == []


def test_flush_buffer_retry_successful_write(monkeypatch, tmp_path):
    ticks = [
        {"ts": 100.0, "token": "NSE_FO|101", "symbol": "NIFTY 24000 CE", "ltp": 150.0, "bid": 149.0, "ask": 151.0, "vol": 100.0, "oi": 200.0, "depth": "{}"},
    ]
    tick_buffer = list(ticks)
    buffer_lock = threading.Lock()
    chunks_dir = tmp_path / "chunks"
    chunks_dir.mkdir(parents=True)

    # 1. Attempt 1 fails
    original_write = pq.write_table
    fail_state = {"should_fail": True}

    def intermittent_write_table(*args, **kwargs):
        if fail_state["should_fail"]:
            raise IOError("Transient write error")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(pq, "write_table", intermittent_write_table)

    flush_buffer(tick_buffer, buffer_lock, chunks_dir, "20261015")
    assert len(tick_buffer) == 1

    # 2. While waiting for retry, a new tick arrives in tick_buffer
    with buffer_lock:
        tick_buffer.append(
            {"ts": 102.0, "token": "NSE_FO|102", "symbol": "NIFTY 24000 PE", "ltp": 85.0, "bid": 84.0, "ask": 86.0, "vol": 60.0, "oi": 160.0, "depth": "{}"}
        )

    assert len(tick_buffer) == 2

    # 3. Attempt 2 succeeds
    fail_state["should_fail"] = False
    flush_buffer(tick_buffer, buffer_lock, chunks_dir, "20261015")

    # Buffer should now be cleared
    assert len(tick_buffer) == 0

    # Parquet file should contain both ticks in order
    written_files = list(chunks_dir.glob("*.parquet"))
    assert len(written_files) == 1
    df = pd.read_parquet(written_files[0])
    assert len(df) == 2
    assert list(df["token"]) == ["NSE_FO|101", "NSE_FO|102"]


def test_refresh_late_day_option_subscriptions_with_lock():
    from core.upstox_capture.late_day_option_refresh import refresh_late_day_option_subscriptions

    class MockStreamer:
        def __init__(self):
            self.subscribed_keys = []

        def subscribe(self, keys, mode="full"):
            self.subscribed_keys.extend(keys)

    today_ms = int(datetime.now().timestamp() * 1000)
    mock_data = [
        {"name": "NIFTY", "instrument_type": "CE", "strike_price": 24000.0, "expiry": today_ms, "instrument_key": "NSE_FO|24000CE", "trading_symbol": "NIFTY 24000 CE"},
        {"name": "NIFTY", "instrument_type": "PE", "strike_price": 24000.0, "expiry": today_ms, "instrument_key": "NSE_FO|24000PE", "trading_symbol": "NIFTY 24000 PE"},
    ]
    df_inst = pd.DataFrame(mock_data)
    streamer = MockStreamer()
    subscriptions = {}
    subscriptions_lock = threading.Lock()

    # Call with subscriptions_lock
    new_count = refresh_late_day_option_subscriptions(
        streamer=streamer,
        subscriptions=subscriptions,
        df_inst=df_inst,
        current_spot_prices={"NIFTY": 24000.0},
        subscriptions_lock=subscriptions_lock,
    )

    assert new_count == 2
    assert "NSE_FO|24000CE" in subscriptions
    assert "NSE_FO|24000PE" in subscriptions
    assert subscriptions["NSE_FO|24000CE"] == "NIFTY 24000 CE"


