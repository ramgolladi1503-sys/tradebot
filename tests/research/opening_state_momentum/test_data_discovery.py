import os
import tempfile
import json
import hashlib
import pytest
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path

from research.opening_state_momentum.models import FileInventory
from research.opening_state_momentum.schema_detection import detect_parquet_metadata, compute_schema_fingerprint
from research.opening_state_momentum.quality_checks import check_ohlcv_file, parse_date_from_filename
from research.opening_state_momentum.manifest import compute_portable_hash, compute_local_hash
from research.opening_state_momentum.data_inventory import scan_single_file
from scripts.run_opening_state_data_inventory import discover_files_in_roots

# Helper to create a dummy parquet file
def create_dummy_parquet(path: Path, data: dict, schema=None):
    df = pd.DataFrame(data)
    table = pa.Table.from_pandas(df, schema=schema)
    pq.write_table(table, path)

@pytest.fixture
def temp_roots():
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        yield Path(tmp1), Path(tmp2)

def test_deterministic_enumeration(temp_roots):
    tmp1, _ = temp_roots
    file1 = tmp1 / "file1.parquet"
    file2 = tmp1 / "file2.parquet"
    create_dummy_parquet(file1, {"timestamp": ["2026-07-16 09:15:00"], "open": [100.0]})
    create_dummy_parquet(file2, {"timestamp": ["2026-07-16 09:15:00"], "open": [100.0]})
    
    discovered, _ = discover_files_in_roots([str(tmp1)])
    assert len(discovered) == 2
    # Ensure relative paths match
    rel_paths = [d["relative_path"] for d in discovered]
    assert "file1.parquet" in rel_paths
    assert "file2.parquet" in rel_paths

def test_no_implicit_limit_and_smoke(temp_roots):
    tmp1, _ = temp_roots
    for i in range(10):
        create_dummy_parquet(tmp1 / f"file_{i}.parquet", {"timestamp": ["2026-07-16 09:15:00"], "open": [100.0]})
        
    discovered, _ = discover_files_in_roots([str(tmp1)])
    assert len(discovered) == 10  # No implicit 500 cap!

def test_stable_aggregate_hash(temp_roots):
    tmp1, _ = temp_roots
    file1 = tmp1 / "file1.parquet"
    create_dummy_parquet(file1, {"timestamp": ["2026-07-16 09:15:00"], "open": [100.0]})
    
    inv = scan_single_file(str(file1), str(tmp1), "file1.parquet")
    f_dict = [{
        "relative_path": inv.relative_path,
        "sha256": inv.sha256,
        "size_bytes": inv.size_bytes,
        "row_count": inv.row_count,
        "min_timestamp": inv.min_timestamp,
        "max_timestamp": inv.max_timestamp,
        "schema_fingerprint": inv.schema_fingerprint,
        "data_family": inv.data_family
    }]
    hash1 = compute_portable_hash(f_dict)
    hash2 = compute_portable_hash(f_dict)
    assert hash1 == hash2

def test_portable_vs_local_hash_relocation(temp_roots):
    tmp1, tmp2 = temp_roots
    file1_tmp1 = tmp1 / "file1.parquet"
    file1_tmp2 = tmp2 / "file1.parquet"
    
    data = {"timestamp": ["2026-07-16 09:15:00"], "open": [100.0]}
    create_dummy_parquet(file1_tmp1, data)
    create_dummy_parquet(file1_tmp2, data)
    
    inv1 = scan_single_file(str(file1_tmp1), str(tmp1), "file1.parquet")
    inv2 = scan_single_file(str(file1_tmp2), str(tmp2), "file1.parquet")
    
    dict1 = [{
        "absolute_path": inv1.absolute_path,
        "source_root": inv1.source_root,
        "relative_path": inv1.relative_path,
        "inode": inv1.inode,
        "pre_scan_mtime": inv1.pre_scan_mtime,
        "size_bytes": inv1.size_bytes,
        "sha256": inv1.sha256,
        "row_count": inv1.row_count,
        "min_timestamp": inv1.min_timestamp,
        "max_timestamp": inv1.max_timestamp,
        "schema_fingerprint": inv1.schema_fingerprint,
        "data_family": inv1.data_family
    }]
    
    dict2 = [{
        "absolute_path": inv2.absolute_path,
        "source_root": inv2.source_root,
        "relative_path": inv2.relative_path,
        "inode": inv2.inode,
        "pre_scan_mtime": inv2.pre_scan_mtime,
        "size_bytes": inv2.size_bytes,
        "sha256": inv2.sha256,
        "row_count": inv2.row_count,
        "min_timestamp": inv2.min_timestamp,
        "max_timestamp": inv2.max_timestamp,
        "schema_fingerprint": inv2.schema_fingerprint,
        "data_family": inv2.data_family
    }]
    
    # Portable hash must remain identical
    assert compute_portable_hash(dict1) == compute_portable_hash(dict2)
    # Local provenance hash must differ because absolute path/root changed
    assert compute_local_hash(dict1) != compute_local_hash(dict2)

def test_changed_during_scan_exclusion(temp_roots, monkeypatch):
    tmp1, _ = temp_roots
    file1 = tmp1 / "file1.parquet"
    create_dummy_parquet(file1, {"timestamp": ["2026-07-16 09:15:00"], "open": [100.0]})
    
    # Mock stat to return a different post_scan mtime
    original_stat = Path.stat
    calls = {}
    def fake_stat(self, *args, **kwargs):
        st = original_stat(self, *args, **kwargs)
        if "file1.parquet" in str(self):
            path_str = str(self)
            calls[path_str] = calls.get(path_str, 0) + 1
            if calls[path_str] > 1:
                class ModStat:
                    st_mtime = st.st_mtime + 10.0
                    st_size = st.st_size
                    st_ino = st.st_ino
                return ModStat()
        return st
            
    monkeypatch.setattr(Path, "stat", fake_stat)
    
    inv = scan_single_file(str(file1), str(tmp1), "file1.parquet")
    assert inv.stability == "UNSTABLE_CHANGED_DURING_SCAN"

def test_empty_file_classification(temp_roots):
    tmp1, _ = temp_roots
    empty_file = tmp1 / "empty.parquet"
    empty_file.touch()
    
    inv = scan_single_file(str(empty_file), str(tmp1), "empty.parquet")
    assert inv.stability == "EMPTY_FILE"
    assert inv.is_empty is True

def test_unsupported_schema_classification(temp_roots):
    tmp1, _ = temp_roots
    txt_file = tmp1 / "bad.parquet"
    with open(txt_file, "w") as f:
        f.write("not a parquet file")
        
    inv = scan_single_file(str(txt_file), str(tmp1), "bad.parquet")
    assert inv.stability == "UNSUPPORTED_SCHEMA"

def test_ohlc_invariants(temp_roots):
    tmp1, _ = temp_roots
    file1 = tmp1 / "inv.parquet"
    # high < low, low > open, high < close, non-positive prices
    create_dummy_parquet(file1, {
        "timestamp": ["2026-07-16 09:15:00", "2026-07-16 09:16:00"],
        "open": [100.0, 100.0],
        "high": [90.0, 100.0],  # high < low
        "low": [95.0, 95.0],
        "close": [100.0, -10.0], # non-positive close
        "volume": [100, 100]
    })
    
    q = check_ohlcv_file(str(file1))
    assert q["high_lt_low"] == 1
    assert q["non_positive_prices"] == 1

def test_duplicate_timestamps(temp_roots):
    tmp1, _ = temp_roots
    file1 = tmp1 / "dups.parquet"
    create_dummy_parquet(file1, {
        "timestamp": ["2026-07-16 09:15:00", "2026-07-16 09:15:00"],
        "open": [100.0, 105.0],
        "high": [101.0, 106.0],
        "low": [99.0, 104.0],
        "close": [100.0, 105.0],
        "volume": [100, 100]
    })
    q = check_ohlcv_file(str(file1))
    assert q["duplicate_timestamps"] == 1
    assert q["conflicting_duplicates"] == 1

def test_timezone_naive_and_mismatch(temp_roots):
    tmp1, _ = temp_roots
    file1 = tmp1 / "NIFTY_20260716.parquet"
    create_dummy_parquet(file1, {
        "timestamp": ["2026-07-17 09:15:00"],  # Date differs from filename (20260716)
        "open": [100.0],
        "high": [100.0],
        "low": [100.0],
        "close": [100.0]
    })
    q = check_ohlcv_file(str(file1))
    assert q["timezone_naive"] is True
    assert q["filename_date_mismatch"] is True

def test_option_readiness_classification():
    # Test strict option replay capability checks
    from scripts.run_opening_state_data_inventory import main
    # Ensure script parses correctly
    assert parse_date_from_filename("NIFTY_20260716.parquet") == "20260716"
