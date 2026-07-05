import pytest
import pandas as pd
from pathlib import Path
import json

def test_filtered_stress_replay_dataset_quality(tmp_path, monkeypatch):
    import scripts.validate_filtered_stress_replay_dataset as val_mod
    
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    valid_file = data_dir / "valid_ticks.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{\"bids\": []}"],
        "local_ts": [1234567],
        "instrument_token": [123],
        "symbol": ["NIFTY26JUL24000CE"]
    }).to_parquet(valid_file)
    
    unresolved_file = data_dir / "unresolved_ticks.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{\"bids\": []}"],
        "local_ts": [1234567],
        "instrument_token": [999],
        "symbol": ["UNKNOWN"]
    }).to_parquet(unresolved_file)
    
    invalid_ltp_file = data_dir / "invalid_ltp.parquet"
    pd.DataFrame({
        "last_price": [0.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{\"bids\": []}"],
        "local_ts": [1234567],
        "instrument_token": [123],
        "symbol": ["NIFTY26JUL24000CE"]
    }).to_parquet(invalid_ltp_file)

    invalid_bid_file = data_dir / "invalid_bid.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [-1.0],
        "best_ask": [101.0],
        "depth_json": ["{\"bids\": []}"],
        "local_ts": [1234567],
        "instrument_token": [123],
        "symbol": ["NIFTY26JUL24000CE"]
    }).to_parquet(invalid_bid_file)
    
    invalid_spread_file = data_dir / "invalid_spread.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [102.0],
        "best_ask": [101.0],
        "depth_json": ["{\"bids\": []}"],
        "local_ts": [1234567],
        "instrument_token": [123],
        "symbol": ["NIFTY26JUL24000CE"]
    }).to_parquet(invalid_spread_file)
    
    invalid_depth_file = data_dir / "invalid_depth.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{}"],
        "local_ts": [1234567],
        "instrument_token": [123],
        "symbol": ["NIFTY26JUL24000CE"]
    }).to_parquet(invalid_depth_file)
    
    missing_col_file = data_dir / "missing_col.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "local_ts": [1234567],
        "instrument_token": [123],
        "symbol": ["NIFTY26JUL24000CE"]
    }).to_parquet(missing_col_file)
    
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
    assert rep["paper_live_allowed"] is False
    assert rep["live_allowed"] is False
    assert rep["execution_allowed"] is False
    assert rep["spread_summary"]["median"] == 2.0
    assert rep["timestamp_start"] == "1234567"
    
    # 2. Unresolved token
    val_mod.validate_dataset(str(unresolved_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_CONTAINS_UNRESOLVED_TOKENS" in rep["blockers"]
    
    # 3. Missing required column (depth_json)
    val_mod.validate_dataset(str(missing_col_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_MISSING_REQUIRED_COLUMNS" in rep["blockers"]
    
    # 4. Invalid LTP
    val_mod.validate_dataset(str(invalid_ltp_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_INVALID_LTP" in rep["blockers"]
    
    # 5. Invalid bid
    val_mod.validate_dataset(str(invalid_bid_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_INVALID_BID_ASK" in rep["blockers"]
    
    # 6. Invalid spread
    val_mod.validate_dataset(str(invalid_spread_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_INVALID_SPREAD" in rep["blockers"]
    
    # 7. Invalid depth
    val_mod.validate_dataset(str(invalid_depth_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_INVALID_DEPTH" in rep["blockers"]

