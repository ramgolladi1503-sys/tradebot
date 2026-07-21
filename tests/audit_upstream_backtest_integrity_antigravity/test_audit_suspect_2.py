import json
import math
import subprocess
import pandas as pd
from pathlib import Path
import pytest
import shutil

def setup_ledger_fixture(base_dir: Path, end_of_bucket_close: float):
    replay_dir = base_dir / "runtime/upstox_candidate_replay/20230101/underlying"
    replay_dir.mkdir(parents=True, exist_ok=True)
    
    # We need 15 completed 15-minute buckets to get a finite 15-period SMA.
    # 15 buckets * 15 mins = 225 minutes. 
    # 09:15 to 13:00 is 3 hours 45 mins = 225 mins (15 buckets).
    # Then we add the 16th bucket: 13:00 to 13:14.
    
    times = pd.date_range("2023-01-01 09:15", "2023-01-01 13:14", freq="1min")
    df = pd.DataFrame(index=times)
    df["timestamp"] = times
    df["open"] = 100.0
    df["high"] = 100.0
    df["low"] = 100.0
    df["close"] = 100.0
    df["volume"] = 100
    
    # 16th bucket starts at 13:00
    # At 13:05, we create a FAILED_BREAKOUT_SHORT signal.
    # We need a high > or_high and close < or_high.
    # The OR high is from 09:15 to 09:25.
    
    # Set OR high
    df.loc["2023-01-01 09:15":"2023-01-01 09:25", "high"] = 105.0
    df.loc["2023-01-01 09:15":"2023-01-01 09:25", "low"] = 95.0
    
    # At 13:05, create the signal:
    df.loc["2023-01-01 13:05", "high"] = 110.0
    df.loc["2023-01-01 13:05", "close"] = 100.0 # close < or_high (105)
    df.loc["2023-01-01 13:05", "open"] = 100.0
    df.loc["2023-01-01 13:05", "low"] = 90.0
    
    # The signal at 13:05 will check if htf is BULLISH.
    # It is BULLISH if htf_sma < close. 
    # htf_sma at 13:05 is the ffill of the 13:14 bucket close (due to the bug).
    # We have 15 prior buckets with close=100.
    # For df1, end of bucket (13:14) close = 100. SMA = 100. htf_sma (100) is NOT < close (100) -> NEUTRAL/BEARISH -> Not blocked.
    # For df2, end of bucket (13:14) close = -1000. (So the 15-period SMA drops < 100). 
    # Let's make end of bucket close = -500. SMA = (14*100 - 500) / 15 = 60.
    # 60 < 100. So htf_sma < close -> BULLISH -> HTF_BLOCKED!
    
    df.loc["2023-01-01 13:14", "close"] = end_of_bucket_close
    
    df.to_parquet(replay_dir / "NIFTY_test.parquet")
    
    # Write audit valid file so it runs
    audit_dir = base_dir / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION"
    audit_dir.mkdir(parents=True, exist_ok=True)
    with open(audit_dir / "upstox_candle_file_audit.json", "w") as f:
        json.dump({"classification": "UPSTOX_CANDLE_FILES_VALID"}, f)
        
    # Write risk contract
    config_dir = base_dir / "configs/strategy_risk_contracts"
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_dir / "MEAN_REVERSION_EXTENSION.json", "w") as f:
        json.dump({}, f)
        
    return base_dir


def test_reproduces_current_behavior_suspect_2(tmp_path):
    """
    Layer A: Current-behavior reproducer.
    Invokes the actual production `generate_mean_reversion_trade_ledger.py` via subprocess.
    """
    # Create two isolated temp directories
    dir1 = tmp_path / "run1"
    dir2 = tmp_path / "run2"
    
    setup_ledger_fixture(dir1, end_of_bucket_close=100.0)
    setup_ledger_fixture(dir2, end_of_bucket_close=-500.0)
    
    # Run the monolithic script for both
    script_path = Path("scripts/generate_mean_reversion_trade_ledger.py").absolute()
    
    subprocess.run(["python3", str(script_path), "--start-date", "20230101", "--end-date", "20230101"], cwd=dir1, check=True)
    subprocess.run(["python3", str(script_path), "--start-date", "20230101", "--end-date", "20230101"], cwd=dir2, check=True)
    
    # Read the candidates
    cand_file1 = dir1 / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_candidates.jsonl"
    cand_file2 = dir2 / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_candidates.jsonl"
    
    assert cand_file1.exists()
    assert cand_file2.exists()
    
    with open(cand_file1) as f: cands1 = [json.loads(line) for line in f]
    with open(cand_file2) as f: cands2 = [json.loads(line) for line in f]
    
    # At 13:05, in run1 (end_of_bucket_close=100), SMA=100, close=100. htf is "NEUTRAL/BEARISH".
    # In run2 (end_of_bucket_close=-500), SMA=60, close=100. htf is "BULLISH".
    
    sig1 = [c for c in cands1 if c["source_timestamp"] == "2023-01-01T13:05:00"][0]
    sig2 = [c for c in cands2 if c["source_timestamp"] == "2023-01-01T13:05:00"][0]
    
    assert sig1["htf_regime"] == "NEUTRAL/BEARISH"
    assert sig2["htf_regime"] == "BULLISH"
    assert sig2.get("reject_reason") == "HTF_BLOCKED"
    
    # Save artifacts for reporting
    artifact_data = {
        "actual_a_htf_regime": sig1["htf_regime"],
        "actual_b_htf_regime": sig2["htf_regime"]
    }
    art_path = Path("runtime/research/upstream_backtest_integrity_antigravity/evidence_repair")
    art_path.mkdir(parents=True, exist_ok=True)
    with open(art_path / "suspect2_reproducer.json", "w") as f:
        json.dump(artifact_data, f)

@pytest.mark.xfail(strict=True, reason="confirmed current defect: resample lookahead changes past signal behavior")
def test_intended_contract_suspect_2(tmp_path):
    """
    Layer B: Intended-contract test.
    The contract is that a signal generated at 13:05 cannot be causally affected
    by the price at 13:14.
    """
    dir1 = tmp_path / "run3"
    dir2 = tmp_path / "run4"
    
    setup_ledger_fixture(dir1, end_of_bucket_close=100.0)
    setup_ledger_fixture(dir2, end_of_bucket_close=-500.0)
    
    script_path = Path("scripts/generate_mean_reversion_trade_ledger.py").absolute()
    
    subprocess.run(["python3", str(script_path), "--start-date", "20230101", "--end-date", "20230101"], cwd=dir1, check=True)
    subprocess.run(["python3", str(script_path), "--start-date", "20230101", "--end-date", "20230101"], cwd=dir2, check=True)
    
    cand_file1 = dir1 / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_candidates.jsonl"
    cand_file2 = dir2 / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_candidates.jsonl"
    
    with open(cand_file1) as f: cands1 = [json.loads(line) for line in f]
    with open(cand_file2) as f: cands2 = [json.loads(line) for line in f]
    
    sig1 = [c for c in cands1 if c["source_timestamp"] == "2023-01-01T13:05:00"][0]
    sig2 = [c for c in cands2 if c["source_timestamp"] == "2023-01-01T13:05:00"][0]
    
    # We must assert that the oracle feature values are identical up to 13:05, 
    # but the actual implementations diverged due to the bug.
    
    actual_a = sig1["htf_regime"]
    actual_b = sig2["htf_regime"]
    
    # We can also compute the actual numeric values that *should* be the oracle
    # The oracle SMA at 13:05 should only include completed 15-min buckets up to 13:00.
    oracle_sma = 100.0 # 15 periods of 100.0
    oracle_a = oracle_sma
    oracle_b = oracle_sma
    
    assert math.isfinite(oracle_a)
    assert math.isfinite(oracle_b)
    
    # The test must fail here against current production code because actual_a != actual_b
    assert actual_a == actual_b
