import json
import subprocess
import pandas as pd
from pathlib import Path
import pytest
import shutil

def setup_ledger_fixture_suspect3(base_dir: Path):
    replay_dir = base_dir / "runtime/upstox_candidate_replay/20230101/underlying"
    replay_dir.mkdir(parents=True, exist_ok=True)
    
    times = pd.date_range("2023-01-01 09:15", "2023-01-01 14:00", freq="1min")
    df = pd.DataFrame(index=times)
    df["timestamp"] = times
    df["open"] = 100.0
    df["high"] = 100.0
    df["low"] = 100.0
    df["close"] = 100.0
    df["volume"] = 100
    
    # 1. OR definition (09:15 - 09:25)
    df.loc["2023-01-01 09:15":"2023-01-01 09:25", "high"] = 105.0
    df.loc["2023-01-01 09:15":"2023-01-01 09:25", "low"] = 95.0
    
    # 2. Signal A is created at 13:05 (FAILED_BREAKOUT_SHORT)
    df.loc["2023-01-01 13:05", "high"] = 110.0
    df.loc["2023-01-01 13:05", "close"] = 100.0
    df.loc["2023-01-01 13:05", "low"] = 90.0
    
    # 3. Next-bar entry for A at 13:06.
    # At 13:06, Signal A executes. 
    # Can Signal B be created ON THE SAME BAR? 
    # Yes, if we make 13:06 also a signal bar!
    df.loc["2023-01-01 13:06", "high"] = 110.0
    df.loc["2023-01-01 13:06", "close"] = 100.0
    df.loc["2023-01-01 13:06", "low"] = 90.0
    
    # 4. Extended active period for A.
    # A is SHORT. Entry is 100. Stop is 110. Target is ~75.
    # We keep price at 100 until 14:00.
    
    # 5. Exit of A at 14:00.
    # We hit the target for A by dropping to 70 at 14:00.
    df.loc["2023-01-01 14:00", "low"] = 70.0
    
    # 6. Later bar where stale B could execute.
    # The exit happens at 14:00. The loop uses `continue`, so B does not execute at 14:00.
    # At 14:01, `active_trade` is None. `pending_signal` is still holding Signal B!
    
    # Extend dataframe to 14:30
    times_ext = pd.date_range("2023-01-01 14:01", "2023-01-01 14:30", freq="1min")
    df_ext = pd.DataFrame(index=times_ext)
    df_ext["timestamp"] = times_ext
    df_ext["open"] = 71.0 # So B executes at 71.0 at 14:01
    df_ext["high"] = 71.0
    df_ext["low"] = 71.0
    df_ext["close"] = 71.0
    df_ext["volume"] = 100
    df = pd.concat([df, df_ext])
    
    df.to_parquet(replay_dir / "NIFTY_test.parquet")
    
    audit_dir = base_dir / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION"
    audit_dir.mkdir(parents=True, exist_ok=True)
    with open(audit_dir / "upstox_candle_file_audit.json", "w") as f:
        json.dump({"classification": "UPSTOX_CANDLE_FILES_VALID"}, f)
        
    config_dir = base_dir / "configs/strategy_risk_contracts"
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_dir / "MEAN_REVERSION_EXTENSION.json", "w") as f:
        json.dump({}, f)
        
    return base_dir

def test_reproduces_current_behavior_suspect_3(tmp_path):
    """
    Layer A: Current-behavior reproducer.
    Invokes the actual production `generate_mean_reversion_trade_ledger.py`.
    Proves that a pending signal can sit stale in memory while another trade is active.
    """
    base_dir = setup_ledger_fixture_suspect3(tmp_path / "run")
    
    script_path = Path("scripts/generate_mean_reversion_trade_ledger.py").absolute()
    subprocess.run(["python3", str(script_path), "--start-date", "20230101", "--end-date", "20230101"], cwd=base_dir, check=True)
    
    ledger_file = base_dir / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger.jsonl"
    
    with open(ledger_file) as f: trades = [json.loads(line) for line in f]
    
    # We should have exactly 2 trades.
    assert len(trades) == 2, f"Expected 2 trades, got {len(trades)}"
    
    trade_a = trades[0]
    trade_b = trades[1]
    
    assert trade_a["signal_time"] == "2023-01-01T13:05:00"
    assert trade_a["entry_time"] == "2023-01-01T13:06:00"
    
    assert trade_b["signal_time"] == "2023-01-01T13:06:00"
    
    # B executes later when A exits, proving it was stale
    actual_entry_time = pd.to_datetime(trade_b["entry_time"])
    signal_time = pd.to_datetime(trade_b["signal_time"])
    actual_delay_minutes = (actual_entry_time - signal_time).total_seconds() / 60
    assert actual_delay_minutes > 1.0, f"Expected B to be delayed > 1 min, but executed at {actual_entry_time}"
    
    # And critically, the ledger falsely claims 1 bar of delay!
    assert trade_b["entry_delay_bars"] == 1
    
    artifact_data = {
        "signal_a_time": trade_a["signal_time"],
        "entry_a_time": trade_a["entry_time"],
        "signal_b_time": trade_b["signal_time"],
        "entry_b_time": trade_b["entry_time"],
        "entry_b_claimed_delay": trade_b["entry_delay_bars"],
        "actual_delay_minutes": actual_delay_minutes
    }
    
    art_path = Path("runtime/research/upstream_backtest_integrity_antigravity/evidence_repair")
    art_path.mkdir(parents=True, exist_ok=True)
    with open(art_path / "suspect3_reproducer.json", "w") as f:
        json.dump(artifact_data, f)

@pytest.mark.xfail(strict=True, reason="confirmed current defect: stale signals persist and execute hours later")
def test_intended_contract_suspect_3(tmp_path):
    """
    Layer B: Intended-contract test.
    The contract is that a signal must expire if it cannot be executed on the immediate next bar.
    """
    base_dir = setup_ledger_fixture_suspect3(tmp_path / "run2")
    
    script_path = Path("scripts/generate_mean_reversion_trade_ledger.py").absolute()
    subprocess.run(["python3", str(script_path), "--start-date", "20230101", "--end-date", "20230101"], cwd=base_dir, check=True)
    
    ledger_file = base_dir / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger.jsonl"
    with open(ledger_file) as f: trades = [json.loads(line) for line in f]
    
    # The oracle contract: Trade B should NEVER have executed.
    # It was blocked at 10:07 because a trade was active, so it should have been discarded.
    assert len(trades) == 1
