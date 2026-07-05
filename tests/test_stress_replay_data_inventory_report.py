import pytest
import pandas as pd
from pathlib import Path
import json

def test_inventory_report_logic(tmp_path, monkeypatch):
    import scripts.report_stress_replay_data_inventory as rep_mod
    
    # create fake data dir
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    # 1. Synthetic marker
    synthetic_file = data_dir / "synthetic_options.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{}"],
        "local_ts": [1234567],
        "instrument_token": [123]
    }).to_parquet(synthetic_file)
    
    # 2. Option LTP without bid/ask (option candle)
    ltp_only_file = data_dir / "option_candles.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "local_ts": [1234567],
        "instrument_token": [123]
    }).to_parquet(ltp_only_file)
    
    # 3. Real provenance capable with token
    capable_file = data_dir / "index_ticks.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{}"],
        "local_ts": [1234567],
        "instrument_token": [123]
    }).to_parquet(capable_file)

    # 4. Same file but no master mapping
    unresolved_file = data_dir / "index_ticks_unresolved.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "depth_json": ["{}"],
        "local_ts": [1234567],
        "instrument_token": [999]
    }).to_parquet(unresolved_file)
    
    # 5. Underlying only (no token)
    underlying_file = data_dir / "underlying.parquet"
    pd.DataFrame({
        "open": [100.0],
        "local_ts": [1234567]
    }).to_parquet(underlying_file)

    # 6. Partially capable file (some tokens resolve, some do not)
    partial_file = data_dir / "partial_ticks_20260702.parquet"
    pd.DataFrame({
        "last_price": [100.0, 100.0],
        "best_bid": [99.0, 99.0],
        "best_ask": [101.0, 101.0],
        "depth_json": ["{}", "{}"],
        "local_ts": [1234567, 1234568],
        "instrument_token": [123, 999]
    }).to_parquet(partial_file)

    # Fake instrument master
    master_file = data_dir / "kite_instruments.json"
    with open(master_file, "w") as f:
        json.dump([
            {"instrument_token": 123, "expiry": "2026-07-30", "strike": 24000, "instrument_type": "CE", "segment": "NFO-OPT", "tradingsymbol": "NIFTY26JUL24000CE"}
        ], f)

    monkeypatch.setattr(rep_mod, "Path", lambda p_str: tmp_path / p_str if p_str in ["runtime", ".runtime", "data", "configs", "reports", "."] else (tmp_path / p_str if p_str == "runtime/strategy_validation" else Path(p_str)))

    rep_mod.create_report(str(master_file))
    
    out_json = tmp_path / "runtime/strategy_validation/stress_replay_data_inventory_report.json"
    with open(out_json) as f:
        report = json.load(f)
        
    classifications = {Path(r["path"]).name: r for r in report}
    
    # Check partial file logic
    r_part = classifications["partial_ticks_20260702.parquet"]
    assert r_part["classification"] == "PARTIAL_STRESS_REPLAY_CAPABLE"
    assert r_part["stress_replay_capable"] is False
    assert r_part["partial_stress_replay_capable"] is True
    assert r_part["requires_token_filter"] is True
    assert r_part["resolved_option_contracts_count"] == 1
    
    # Check generated index
    idx_path = tmp_path / "runtime/strategy_validation/stress_replay_resolved_option_token_index.json"
    with open(idx_path) as f:
        idx = json.load(f)
        
    assert "source_path" in idx
    assert "instrument_master_path" in idx
    assert "instrument_master_date" in idx
    assert "lineage_verdict" in idx
    
    assert idx["instrument_master_date"] is None
    assert idx["instrument_master_date_source"] == "unknown"
    assert idx["lineage_verdict"] == "TOKEN_INDEX_LINEAGE_BLOCKED"
    assert "TOKEN_INDEX_INSTRUMENT_MASTER_DATE_UNKNOWN" in idx["lineage_blockers"]

    # Now rerun with CLI date
    rep_mod.create_report(str(master_file), instrument_master_date_arg="2026-07-02")
    with open(idx_path) as f:
        idx = json.load(f)
        
    assert idx["instrument_master_date"] == "2026-07-02"
    assert idx["instrument_master_date_source"] == "cli_arg"
    assert idx["lineage_verdict"] == "TOKEN_INDEX_LINEAGE_VALID"
