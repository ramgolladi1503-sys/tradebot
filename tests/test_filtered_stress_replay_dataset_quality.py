import pytest
import pandas as pd
from pathlib import Path
import json

def test_filtered_stress_replay_dataset_quality(tmp_path, monkeypatch):
    import scripts.validate_filtered_stress_replay_dataset as val_mod
    
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    # Generate some timestamp data (valid session IST)
    # 2026-07-02 09:15 IST is 2026-07-02 03:45 UTC = 1782963900000000000 ns
    valid_ts_1 = 1782963900000000000
    valid_ts_2 = 1782963901000000000
    
    valid_file = data_dir / "resolved_option_ticks_20260702.parquet"
    pd.DataFrame({
        "last_price": [100.0, 100.0],
        "best_bid": [99.0, 99.0],
        "best_ask": [101.0, 101.0],
        "depth_json": ["{\"bids\": []}", "{\"bids\": []}"],
        "local_ts": [valid_ts_1, valid_ts_2],
        "instrument_token": [123, 123],
        "symbol": ["NIFTY26JUL24000CE", "NIFTY26JUL24000CE"]
    }).to_parquet(valid_file)
    
    # 2. Date mismatch (20260702 filename but 2024 timestamp)
    mismatch_file = data_dir / "resolved_option_ticks_20260702_mismatch.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{\"bids\": []}"],
        "local_ts": [1719889500000000000], # 2024-07-02
        "instrument_token": [123],
        "symbol": ["NIFTY26JUL24000CE"]
    }).to_parquet(mismatch_file)
    
    # 4. Outliers
    outlier_file = data_dir / "resolved_option_ticks_20260702_outlier.parquet"
    pd.DataFrame({
        "last_price": [100.0, 100.0],
        "best_bid": [99.0, 20.0], 
        "best_ask": [101.0, 120.0],
        "depth_json": ["{\"bids\": []}", "{\"bids\": []}"],
        "local_ts": [valid_ts_1, valid_ts_2],
        "instrument_token": [123, 123],
        "symbol": ["NIFTY26JUL24000CE", "NIFTY26JUL24000CE"]
    }).to_parquet(outlier_file)
    
    token_index = data_dir / "index.json"
    with open(token_index, "w") as f:
        json.dump({
            "resolved_option_tokens": [
                {"instrument_token": "123"}
            ]
        }, f)
        
    master_file = data_dir / "kite_instruments_20260702.json"
    with open(master_file, "w") as f:
        f.write("{}")
        
    monkeypatch.setattr(val_mod, "Path", lambda p_str: tmp_path / p_str if p_str in ["runtime/strategy_validation", "runtime", ".runtime", "data", "configs", "reports", "."] else (tmp_path / p_str if p_str == "runtime/strategy_validation" else Path(p_str)))
    
    # 1. Valid dataset but no instrument master date
    val_mod.validate_dataset(str(valid_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_INSTRUMENT_MASTER_DATE_UNKNOWN" in rep["lineage_blockers"]
    
    # 2. Valid dataset with correct instrument master date
    val_mod.validate_dataset(str(valid_file), str(token_index), instrument_master_date_arg="2026-07-02")
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_VALID"
    assert rep["date_alignment_ok"] is True
    assert rep["instrument_master_date_alignment_ok"] is True
    assert rep["metadata_temporally_valid"] is True
    
    # 3. Valid dataset with wrong instrument master date
    val_mod.validate_dataset(str(valid_file), str(token_index), instrument_master_date_arg="2024-07-02")
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_INSTRUMENT_MASTER_DATE_MISMATCH" in rep["lineage_blockers"]
    
    # 4. Extract date from instrument master filename
    val_mod.validate_dataset(str(valid_file), str(token_index), instrument_master_path=str(master_file))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_VALID"
    assert rep["instrument_master_date"] == "2026-07-02"

    # 5. Date Mismatch (filename says 2026 but ts is 2024)
    val_mod.validate_dataset(str(mismatch_file), str(token_index), instrument_master_date_arg="2024-07-02")
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_DATE_MISMATCH" in rep["blockers"]
    
    # 6. Outliers still block even if date aligns
    val_mod.validate_dataset(str(outlier_file), str(token_index), instrument_master_date_arg="2026-07-02")
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_SPREAD_OUTLIER_RATE_TOO_HIGH" in rep["blockers"]

