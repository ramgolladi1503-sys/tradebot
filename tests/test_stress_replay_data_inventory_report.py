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

    # Fake instrument master
    master_file = data_dir / "kite_instruments.json"
    with open(master_file, "w") as f:
        json.dump([
            {"instrument_token": 123, "expiry": "2026-07-30", "strike": 24000, "instrument_type": "CE", "segment": "NFO-OPT", "tradingsymbol": "NIFTY26JUL24000CE"}
        ], f)

    monkeypatch.setattr(rep_mod, "Path", lambda p_str: tmp_path / p_str if p_str in ["runtime", ".runtime", "data", "configs", "reports", "."] else (tmp_path / p_str if p_str == "runtime/strategy_validation" else Path(p_str)))

    rep_mod.create_report()
    
    out_json = tmp_path / "runtime/strategy_validation/stress_replay_data_inventory_report.json"
    with open(out_json) as f:
        report = json.load(f)
        
    classifications = {Path(r["path"]).name: r for r in report}
    
    # 1. A file with instrument_token but no instrument master must classify as STRESS_REPLAY_CANDIDATE_METADATA_BLOCKED, not STRESS_REPLAY_CAPABLE.
    # We added unresolved_file which has token 999.
    r_unres = classifications["index_ticks_unresolved.parquet"]
    assert r_unres["classification"] == "STRESS_REPLAY_CANDIDATE_METADATA_BLOCKED"
    assert "DATA_BLOCKED_INSTRUMENT_TOKEN_UNRESOLVED" in r_unres["metadata_blockers"]

    # 2. A file with last_price, best_bid, best_ask, depth_json, timestamp, and token still cannot be stress-capable without verified metadata.
    assert r_unres["instrument_metadata_verified"] is False
    
    # 3. A valid instrument master resolving token to expiry/strike/CE/PE allows STRESS_REPLAY_CAPABLE.
    r_cap = classifications["index_ticks.parquet"]
    assert r_cap["classification"] == "STRESS_REPLAY_CAPABLE"
    assert r_cap["instrument_metadata_verified"] is True
    assert r_cap["resolved_option_contracts_count"] == 1
    
    # 4. Option LTP without bid/ask/depth is not stress replay capable
    r_opt = classifications["option_candles.parquet"]
    assert r_opt["classification"] == "OPTION_CANDLE_ONLY"
    
    # 5. Underlying only
    r_und = classifications["underlying.parquet"]
    assert r_und["classification"] == "UNDERLYING_ONLY"
    
    # 6. Synthetic/mock/proxy/fallback filename/source remains non-certifiable
    r_syn = classifications["synthetic_options.parquet"]
    assert r_syn["classification"] == "NON_CERTIFIABLE_SYNTHETIC_OR_PROXY"
