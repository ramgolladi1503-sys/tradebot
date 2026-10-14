import json
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.upstox_daily_live_capture_and_stitch import execute_post_market_stitching


def test_stitching_creates_master_and_prunes_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock_token")

    data_dir = tmp_path / "2026-09-28"
    chunks_dir = data_dir / "chunks"
    chunks_dir.mkdir(parents=True)

    # Create two test chunks
    chunk1_data = {
        "ts": [1790566150.0, 1790566151.0],
        "token": ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"],
        "symbol": ["NIFTY 50", "BANKNIFTY"],
        "ltp": [23140.0, 55000.0],
        "bid": [23139.0, 54995.0],
        "ask": [23141.0, 55005.0],
        "vol": [100.0, 200.0],
        "oi": [1000.0, 2000.0],
        "depth": ["{}", "{}"],
    }
    chunk2_data = {
        "ts": [1790566152.0],
        "token": ["BSE_INDEX|SENSEX"],
        "symbol": ["SENSEX"],
        "ltp": [73000.0],
        "bid": [72990.0],
        "ask": [73010.0],
        "vol": [50.0],
        "oi": [500.0],
        "depth": ["{}"],
    }

    pq.write_table(pa.Table.from_pandas(pd.DataFrame(chunk1_data)), chunks_dir / "chunk_1.parquet")
    pq.write_table(pa.Table.from_pandas(pd.DataFrame(chunk2_data)), chunks_dir / "chunk_2.parquet")

    assert len(list(chunks_dir.glob("*.parquet"))) == 2

    # Execute stitching
    execute_post_market_stitching("2026-09-28", "20260928", data_dir)

    # Verify stitched master exists and matches content
    stitched_file = data_dir / "upstox_full_ticks_20260928_stitched.parquet"
    assert stitched_file.exists()
    assert stitched_file.stat().st_size > 0

    df_stitched = pq.read_table(stitched_file).to_pandas()
    assert len(df_stitched) == 3
    assert set(df_stitched["symbol"]) == {"NIFTY 50", "BANKNIFTY", "SENSEX"}
    assert df_stitched.isnull().sum().sum() == 0

    # Verify summary JSON exists
    summary_file = data_dir / "stitching_summary_20260928.json"
    assert summary_file.exists()
    with open(summary_file) as f:
        summary = json.load(f)
    assert summary["total_ticks"] == 3
    assert summary["valid_chunks"] == 2
    assert summary["skipped_chunks"] == 0

    # Verify chunks directory was cleanly pruned
    assert not chunks_dir.exists()


def test_stitching_preserves_chunks_if_no_valid_data(tmp_path):
    data_dir = tmp_path / "2026-09-28"
    chunks_dir = data_dir / "chunks"
    chunks_dir.mkdir(parents=True)

    # Empty chunk
    empty_df = pd.DataFrame(columns=["ts", "token", "symbol", "ltp", "bid", "ask", "vol", "oi", "depth"])
    pq.write_table(pa.Table.from_pandas(empty_df), chunks_dir / "chunk_empty.parquet")

    execute_post_market_stitching("2026-09-28", "20260928", data_dir)

    # If 0 ticks, chunks dir should be preserved
    assert chunks_dir.exists()


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

