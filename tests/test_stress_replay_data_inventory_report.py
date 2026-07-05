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
        "local_ts": [1234567],
        "instrument_token": [123]
    }).to_parquet(synthetic_file)
    
    # 2. Option LTP without bid/ask
    ltp_only_file = data_dir / "option_candles.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "local_ts": [1234567],
        "instrument_token": [123]
    }).to_parquet(ltp_only_file)
    
    # 3. Real provenance stress capable
    capable_file = data_dir / "index_ticks.parquet"
    pd.DataFrame({
        "last_price": [100.0],
        "best_bid": [99.0],
        "best_ask": [101.0],
        "local_ts": [1234567],
        "instrument_token": [123]
    }).to_parquet(capable_file)
    
    # 4. Underlying only
    underlying_file = data_dir / "underlying.parquet"
    pd.DataFrame({
        "open": [100.0],
        "local_ts": [1234567]
    }).to_parquet(underlying_file)

    monkeypatch.setattr(rep_mod, "Path", lambda p_str: tmp_path / p_str if p_str in ["runtime", ".runtime", "data", "reports"] else (tmp_path / p_str if p_str == "runtime/strategy_validation" else Path(p_str)))

    rep_mod.create_report()
    
    out_json = tmp_path / "runtime/strategy_validation/stress_replay_data_inventory_report.json"
    with open(out_json) as f:
        report = json.load(f)
        
    classifications = {Path(r["path"]).name: r["classification"] for r in report}
    
    # 1. synthetic/proxy/mock/fallback source markers classify as non-certifiable
    assert classifications["synthetic_options.parquet"] == "NON_CERTIFIABLE_SYNTHETIC_OR_PROXY"
    
    # 2. option LTP without bid/ask/depth is not stress replay capable
    assert classifications["option_candles.parquet"] == "OPTION_CANDLE_ONLY"
    
    # 3. option LTP + bid/ask + real provenance can be classified as stress replay capable
    assert classifications["index_ticks.parquet"] == "STRESS_REPLAY_CAPABLE"
    
    # 4. report has stable machine-readable classification fields
    assert "underlying.parquet" in classifications
    assert classifications["underlying.parquet"] == "UNDERLYING_ONLY"

