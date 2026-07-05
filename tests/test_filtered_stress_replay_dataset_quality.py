import pytest
import pandas as pd
from pathlib import Path
import json

def test_filtered_stress_replay_dataset_quality(tmp_path, monkeypatch):
    import scripts.validate_filtered_stress_replay_dataset as val_mod
    
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
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
    
    mismatch_file = data_dir / "resolved_option_ticks_20260702_mismatch.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{\"bids\": []}"],
        "local_ts": [1719889500000000000],
        "instrument_token": [123],
        "symbol": ["NIFTY26JUL24000CE"]
    }).to_parquet(mismatch_file)
    
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
    
    # 1. Valid dataset but NO lineage -> missing
    val_mod.validate_dataset(str(valid_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_TOKEN_INDEX_LINEAGE_MISSING" in rep["lineage_blockers"]
    
    # 2. Add full lineage, matching
    with open(token_index, "w") as f:
        json.dump({
            "resolved_option_tokens": [{"instrument_token": "123"}],
            "lineage_verdict": "TOKEN_INDEX_LINEAGE_VALID",
            "instrument_master_date": "2026-07-02",
            "instrument_master_date_source": "cli_arg",
            "lineage_blockers": []
        }, f)
    val_mod.validate_dataset(str(valid_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_VALID"
    assert rep["metadata_temporally_valid"] is True
    
    # 3. Add full lineage, wrong date
    with open(token_index, "w") as f:
        json.dump({
            "resolved_option_tokens": [{"instrument_token": "123"}],
            "lineage_verdict": "TOKEN_INDEX_LINEAGE_VALID",
            "instrument_master_date": "2024-07-02",
            "instrument_master_date_source": "cli_arg",
            "lineage_blockers": []
        }, f)
    val_mod.validate_dataset(str(valid_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_INSTRUMENT_MASTER_DATE_MISMATCH" in rep["lineage_blockers"]
    
    # 4. Unknown date
    with open(token_index, "w") as f:
        json.dump({
            "resolved_option_tokens": [{"instrument_token": "123"}],
            "lineage_verdict": "TOKEN_INDEX_LINEAGE_BLOCKED",
            "instrument_master_date": None,
            "instrument_master_date_source": "unknown",
            "lineage_blockers": ["TOKEN_INDEX_INSTRUMENT_MASTER_DATE_UNKNOWN"]
        }, f)
    val_mod.validate_dataset(str(valid_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_INSTRUMENT_MASTER_DATE_UNKNOWN" in rep["lineage_blockers"]

    # 5. Date Mismatch (filename says 2026 but ts is 2024)
    with open(token_index, "w") as f:
        json.dump({
            "resolved_option_tokens": [{"instrument_token": "123"}],
            "lineage_verdict": "TOKEN_INDEX_LINEAGE_VALID",
            "instrument_master_date": "2024-07-02",
            "instrument_master_date_source": "cli_arg",
            "lineage_blockers": []
        }, f)
    val_mod.validate_dataset(str(mismatch_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_DATE_MISMATCH" in rep["blockers"]
    
    # 6. Outliers still block even if date aligns
    with open(token_index, "w") as f:
        json.dump({
            "resolved_option_tokens": [{"instrument_token": "123"}],
            "lineage_verdict": "TOKEN_INDEX_LINEAGE_VALID",
            "instrument_master_date": "2026-07-02",
            "instrument_master_date_source": "cli_arg",
            "lineage_blockers": []
        }, f)
    val_mod.validate_dataset(str(outlier_file), str(token_index))
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_SPREAD_OUTLIER_RATE_TOO_HIGH" in rep["blockers"]
    
    # 7. CLI date arg contradicts token index
    with open(token_index, "w") as f:
        json.dump({
            "resolved_option_tokens": [{"instrument_token": "123"}],
            "lineage_verdict": "TOKEN_INDEX_LINEAGE_VALID",
            "instrument_master_date": "2026-07-02",
            "instrument_master_date_source": "cli_arg",
            "lineage_blockers": []
        }, f)
    val_mod.validate_dataset(str(valid_file), str(token_index), instrument_master_date_arg="2025-01-01")
    with open(tmp_path / "runtime/strategy_validation/filtered_stress_replay_dataset_quality_report.json") as f:
        rep = json.load(f)
    assert rep["classification"] == "FILTERED_STRESS_REPLAY_DATASET_BLOCKED"
    assert "FILTERED_DATASET_CLI_DATE_NOT_BACKED_BY_TOKEN_INDEX" in rep["lineage_blockers"]

