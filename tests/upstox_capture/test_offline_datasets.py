import sys
import json
import pytest
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path

from scripts.upstox_capture.generate_offline_datasets import generate_datasets, validate_partitions
from core.upstox_capture.schemas import NORMALIZED_TICK_SCHEMA

def test_missing_data_fail_closed(tmp_path, capsys):
    normalized_dir = tmp_path / "normalized"
    output_dir = tmp_path / "offline_datasets"
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir(parents=True)
    normalized_dir.mkdir(parents=True)

    with open(ref_dir / "nifty50_membership_20260804.json", "w") as f:
        json.dump({"constituents": {"RELIANCE": {}}}, f)

    with pytest.raises(SystemExit) as exc_info:
        generate_datasets(normalized_dir, output_dir, "20260804")

    assert exc_info.value.code != 0
    captured = capsys.readouterr()
    assert "NO_REAL_NORMALIZED_DATA" in captured.err
    assert "OFFLINE_DATASET_GENERATION_SKIPPED" in captured.err

def test_offline_datasets_generation_and_leakage(tmp_path):
    normalized_dir = tmp_path / "normalized" / "asset_class=equity" / "trade_date=2026-08-04" / "provider=upstox" / "instrument_family=NIFTY" / "hour=09"
    output_dir = tmp_path / "offline_datasets"
    ref_dir = tmp_path / "reference"

    normalized_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    ref_dir.mkdir(parents=True)

    with open(ref_dir / "nifty50_membership_20260804.json", "w") as f:
        json.dump({"constituents": {"RELIANCE": {}}}, f)

    # Write dummy ticks
    records = [
        {
            "schema_version": "1.0",
            "capture_run_id": "run_test",
            "provider": "upstox",
            "feed_version": "v3",
            "connection_id": "conn_a",
            "subscription_lane": "critical",
            "subscription_mode": "full",
            "instrument_key": "NSE_INDEX|Nifty 50",
            "tradingsymbol": "NIFTY 50",
            "exchange_token": "100",
            "exchange": "NSE",
            "segment": "NSE_INDEX",
            "instrument_type": "INDEX",
            "underlying_symbol": "NIFTY",
            "ltp": 24500.0,
            "close_price": 24450.0,
            "open": 24400.0,
            "high": 24510.0,
            "low": 24390.0,
            "volume": 10000,
            "average_traded_price": 24480.0,
            "market_status": "OPEN",
            "source_exchange_ts": 1785834900000, # 09:15:00 UTC
            "provider_current_ts": 1785834900050,
            "provider_last_trade_ts": 1785834900000,
            "receive_wall_ts_utc": "2026-08-04T09:15:00Z",
            "receive_monotonic_ns": 1000000,
            "local_sequence": 1,
            "reconnect_generation": 0,
        },
        {
            "schema_version": "1.0",
            "capture_run_id": "run_test",
            "provider": "upstox",
            "feed_version": "v3",
            "connection_id": "conn_a",
            "subscription_lane": "critical",
            "subscription_mode": "full",
            "instrument_key": "NSE_FO|FUT1",
            "tradingsymbol": "NIFTY 27 AUG FUT",
            "exchange_token": "101",
            "exchange": "NSE",
            "segment": "NSE_FO",
            "instrument_type": "FUT",
            "underlying_symbol": "NIFTY",
            "expiry": "2026-08-27",
            "lot_size": 65,
            "tick_size": 0.05,
            "ltp": 24520.0,
            "last_traded_quantity": 65,
            "close_price": 24470.0,
            "open": 24420.0,
            "high": 24530.0,
            "low": 24410.0,
            "volume": 5000,
            "average_traded_price": 24500.0,
            "open_interest": 100000,
            "previous_open_interest": 98000,
            "total_buy_quantity": 2000,
            "total_sell_quantity": 1800,
            "market_status": "OPEN",
            "source_exchange_ts": 1785834900000,
            "provider_current_ts": 1785834900050,
            "provider_last_trade_ts": 1785834900000,
            "receive_wall_ts_utc": "2026-08-04T09:15:00Z",
            "receive_monotonic_ns": 1000001,
            "local_sequence": 2,
            "reconnect_generation": 0,
        }
    ]

    df = pd.DataFrame(records)
    for field in NORMALIZED_TICK_SCHEMA:
        if field.name not in df.columns:
            df[field.name] = None
    df = df[NORMALIZED_TICK_SCHEMA.names]

    table = pa.Table.from_pandas(df, schema=NORMALIZED_TICK_SCHEMA)
    pq.write_table(table, normalized_dir / "ticks_test_1.parquet")

    generate_datasets(tmp_path / "normalized", output_dir, "20260804")

    precursor_file = output_dir / "precursors_20260804.parquet"
    futures_file = output_dir / "futures_outcomes_20260804.parquet"
    options_file = output_dir / "option_outcomes_20260804.parquet"
    join_file = output_dir / "join_map_20260804.parquet"
    checksums_file = output_dir / "dataset_checksums_20260804.json"

    assert precursor_file.exists()
    assert futures_file.exists()
    assert options_file.exists()
    assert join_file.exists()
    assert checksums_file.exists()

    df_pre = pq.read_table(precursor_file).to_pandas()
    assert not df_pre.empty

    # Future Leakage Verification
    forbidden_outcome_keywords = ["return_5s", "return_15s", "return_30s", "return_60s", "mfe_60s", "mae_60s"]
    for col in df_pre.columns:
        for kw in forbidden_outcome_keywords:
            assert kw not in col, f"Future leakage found in precursor table column: {col}"
