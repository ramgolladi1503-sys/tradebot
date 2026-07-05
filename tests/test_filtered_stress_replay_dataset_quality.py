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
    
    # 3. Outside session rows
    # 03:00 IST is 1782941400000000000
    outside_file = data_dir / "resolved_option_ticks_20260702_outside.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{\"bids\": []}"],
        "local_ts": [1782941400000000000],
        "instrument_token": [123],
        "symbol": ["NIFTY26JUL24000CE"]
    }).to_parquet(outside_file)
    
    # 4. Outliers
    outlier_file = data_dir / "resolved_option_ticks_20260702_outlier.parquet"
    pd.DataFrame({
        "last_price": [100.0, 100.0],
        "best_bid": [99.0, 20.0], # Second spread is 100 (120-20), ltp 100 => ratio 1.0 (100%!)
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
        
    monkeypatch.setattr(val_mod, "Path", lambda p_str: tmp_path / p_str if p_str in ["runtime/strategy_validation", "runtime", ".runtime", "data", "configs", "reports", "."] else (tmp_path / p_str if p_str == "runtime/strategy_validation" else Path(p_str)))
    
    # 1. Valid dataset
    val_mod.validate_dataset(str(valid_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_VALID"
    assert rep["date_alignment_ok"] is True
    assert rep["expected_date_from_filename"] == "2026-07-02"
    assert rep["session_rows"] == 2
    assert rep["outside_session_rows"] == 0
    assert rep["spread_to_ltp_summary"]["median"] == 0.02 # 2/100
    
    # 2. Date Mismatch
    val_mod.validate_dataset(str(mismatch_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_DATE_MISMATCH" in rep["blockers"]
    
    # 3. Outside Session
    val_mod.validate_dataset(str(outside_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_SESSION_COVERAGE_INVALID" in rep["blockers"]
    
    # 4. Outliers
    val_mod.validate_dataset(str(outlier_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert rep["extreme_spread_rows_gt_50pct_ltp"] == 1
    assert "FILTERED_DATASET_EXTREME_SPREAD_OUTLIERS" in rep["warnings"]
    assert "FILTERED_DATASET_SPREAD_OUTLIER_RATE_TOO_HIGH" in rep["blockers"] # 1/2 > 5%

