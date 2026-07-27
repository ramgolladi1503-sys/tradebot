import pytest
import pandas as pd
import shutil
import os
from pathlib import Path
from research.upstox_expired_options.semantic_hash import compute_semantic_hash

@pytest.fixture
def base_df():
    return pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01T10:00:00Z", "2024-01-01T10:01:00Z"]),
        "open": [100.0, 101.0],
        "high": [102.0, 103.0],
        "low": [99.0, 100.0],
        "close": [101.0, 102.0],
        "volume": [10, 20],
        "open_interest": [100, 200],
        "instrument_key": ["OPT1", "OPT1"],
        "expiry": ["2024-01-04", "2024-01-04"]
    })

def test_identical_copy_matches(tmp_path, base_df):
    dir_a = tmp_path / "A"
    dir_b = tmp_path / "B"
    dir_a.mkdir()
    dir_b.mkdir()
    
    base_df.to_parquet(dir_a / "test.parquet")
    base_df.to_parquet(dir_b / "test.parquet")
    
    hash_a = compute_semantic_hash(dir_a)
    hash_b = compute_semantic_hash(dir_b)
    
    assert hash_a["aggregate_hash"] == hash_b["aggregate_hash"]
    assert hash_a["aggregate_hash"] != "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"

def test_change_close_value(tmp_path, base_df):
    dir_a = tmp_path / "A"
    dir_b = tmp_path / "B"
    dir_a.mkdir()
    dir_b.mkdir()
    
    base_df.to_parquet(dir_a / "test.parquet")
    
    df_b = base_df.copy()
    df_b.loc[0, "close"] = 999.0
    df_b.to_parquet(dir_b / "test.parquet")
    
    hash_a = compute_semantic_hash(dir_a)
    hash_b = compute_semantic_hash(dir_b)
    
    assert hash_a["aggregate_hash"] != hash_b["aggregate_hash"]

def test_remove_row(tmp_path, base_df):
    dir_a = tmp_path / "A"
    dir_b = tmp_path / "B"
    dir_a.mkdir()
    dir_b.mkdir()
    
    base_df.to_parquet(dir_a / "test.parquet")
    base_df.iloc[[0]].to_parquet(dir_b / "test.parquet")
    
    hash_a = compute_semantic_hash(dir_a)
    hash_b = compute_semantic_hash(dir_b)
    
    assert hash_a["aggregate_hash"] != hash_b["aggregate_hash"]

def test_add_row(tmp_path, base_df):
    dir_a = tmp_path / "A"
    dir_b = tmp_path / "B"
    dir_a.mkdir()
    dir_b.mkdir()
    
    base_df.to_parquet(dir_a / "test.parquet")
    df_b = pd.concat([base_df, base_df.iloc[[0]]]).reset_index(drop=True)
    df_b.loc[2, "timestamp"] = pd.to_datetime("2024-01-01T10:02:00Z")
    df_b.to_parquet(dir_b / "test.parquet")
    
    hash_a = compute_semantic_hash(dir_a)
    hash_b = compute_semantic_hash(dir_b)
    
    assert hash_a["aggregate_hash"] != hash_b["aggregate_hash"]

def test_change_contract_identity(tmp_path, base_df):
    dir_a = tmp_path / "A"
    dir_b = tmp_path / "B"
    dir_a.mkdir()
    dir_b.mkdir()
    
    base_df.to_parquet(dir_a / "test.parquet")
    
    df_b = base_df.copy()
    df_b.loc[0, "instrument_key"] = "OPT2"
    df_b.to_parquet(dir_b / "test.parquet")
    
    hash_a = compute_semantic_hash(dir_a)
    hash_b = compute_semantic_hash(dir_b)
    
    assert hash_a["aggregate_hash"] != hash_b["aggregate_hash"]

def test_remove_file(tmp_path, base_df):
    dir_a = tmp_path / "A"
    dir_b = tmp_path / "B"
    dir_a.mkdir()
    dir_b.mkdir()
    
    base_df.to_parquet(dir_a / "test1.parquet")
    base_df.to_parquet(dir_a / "test2.parquet")
    
    base_df.to_parquet(dir_b / "test1.parquet")
    
    hash_a = compute_semantic_hash(dir_a)
    hash_b = compute_semantic_hash(dir_b)
    
    assert hash_a["aggregate_hash"] != hash_b["aggregate_hash"]

def test_empty_directory(tmp_path):
    dir_a = tmp_path / "A"
    dir_a.mkdir()
    with pytest.raises(ValueError, match="No Parquet files found"):
        compute_semantic_hash(dir_a)

def test_corrupt_parquet(tmp_path):
    dir_a = tmp_path / "A"
    dir_a.mkdir()
    (dir_a / "test.parquet").write_bytes(b"corrupted data")
    with pytest.raises(Exception):
        compute_semantic_hash(dir_a)

def test_row_reordering_same_hash(tmp_path, base_df):
    dir_a = tmp_path / "A"
    dir_b = tmp_path / "B"
    dir_a.mkdir()
    dir_b.mkdir()
    
    base_df.to_parquet(dir_a / "test.parquet")
    base_df.iloc[::-1].to_parquet(dir_b / "test.parquet")
    
    hash_a = compute_semantic_hash(dir_a)
    hash_b = compute_semantic_hash(dir_b)
    
    assert hash_a["aggregate_hash"] == hash_b["aggregate_hash"]

def test_empty_dataframe(tmp_path):
    dir_a = tmp_path / "A"
    dir_a.mkdir()
    df = pd.DataFrame()
    df.to_parquet(dir_a / "test.parquet")
    
    with pytest.raises(ValueError, match="has zero rows"):
        compute_semantic_hash(dir_a)
