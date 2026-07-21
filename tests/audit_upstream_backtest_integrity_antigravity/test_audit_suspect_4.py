import json
import subprocess
import pandas as pd
from pathlib import Path
import pytest
import shutil

def setup_ledger_fixture_suspect4(base_dir: Path):
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
    
    # OR high
    df.loc["2023-01-01 09:15":"2023-01-01 09:25", "high"] = 105.0
    df.loc["2023-01-01 09:15":"2023-01-01 09:25", "low"] = 95.0
    
    # Signal at 13:05 (SHORT)
    df.loc["2023-01-01 13:05", "high"] = 110.0
    df.loc["2023-01-01 13:05", "close"] = 100.0
    df.loc["2023-01-01 13:05", "low"] = 90.0
    
    # Entry at 13:06
    df.loc["2023-01-01 13:06", "open"] = 100.0
    df.loc["2023-01-01 13:06", "high"] = 100.0
    
    # Exit at 13:10 (Stop loss hit)
    df.loc["2023-01-01 13:10", "high"] = 150.0
    
    df.to_parquet(replay_dir / "NIFTY_test.parquet")
    
    audit_dir = base_dir / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION"
    audit_dir.mkdir(parents=True, exist_ok=True)
    with open(audit_dir / "upstox_candle_file_audit.json", "w") as f:
        json.dump({"classification": "UPSTOX_CANDLE_FILES_VALID"}, f)
        
    config_dir = base_dir / "configs/strategy_risk_contracts"
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_dir / "MEAN_REVERSION_EXTENSION.json", "w") as f:
        json.dump({
            "cost_model": {
                "proxy_option_execution_cost": 2.0,
                "proxy_delta": 0.5
            }
        }, f)
        
    return base_dir

def test_reproduces_current_behavior_suspect_4(tmp_path):
    """
    Layer A: Current-behavior reproducer.
    Invokes the production `generate_mean_reversion_trade_ledger.py`.
    Asserts the ledger double deducts and mixes units for costs.
    """
    base_dir = setup_ledger_fixture_suspect4(tmp_path / "run")
    
    script_path = Path("scripts/generate_mean_reversion_trade_ledger.py").absolute()
    subprocess.run(["python3", str(script_path), "--start-date", "20230101", "--end-date", "20230101"], cwd=base_dir, check=True)
    
    ledger_file = base_dir / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger.jsonl"
    with open(ledger_file) as f: trades = [json.loads(line) for line in f]
    
    assert len(trades) == 1
    trade = trades[0]
    
    gross_pnl = trade["gross_pnl"]
    costs = trade["costs"]
    net_pnl = trade["net_pnl"]
    
    # proxy_exec_cost = 2.0
    # proxy_delta = 0.5
    # underlying_cost = 2.0 / 0.5 = 4.0
    # Script does: net_pnl = gross - (underlying_cost + proxy_exec_cost) = gross - (4.0 + 2.0) = gross - 6.0
    # Wait, in the production script:
    # proxy_exec_cost = get_cfg("cost_model.proxy_option_execution_cost", 1.5)
    # The config structure we wrote is what? 
    # Let's see if our config is read correctly.
    
    artifact_data = {
        "gross_pnl": gross_pnl,
        "costs": costs,
        "net_pnl": net_pnl,
        "underlying_execution_cost": trade["underlying_execution_cost"],
        "proxy_option_execution_cost": trade["proxy_option_execution_cost"]
    }
    
    art_path = Path("runtime/research/upstream_backtest_integrity_antigravity/evidence_repair")
    art_path.mkdir(parents=True, exist_ok=True)
    with open(art_path / "suspect4_reproducer.json", "w") as f:
        json.dump(artifact_data, f)
        
    # The bug is that costs = underlying_cost + proxy_exec_cost
    assert net_pnl == gross_pnl - (trade["underlying_execution_cost"] + trade["proxy_option_execution_cost"])
    
@pytest.mark.xfail(strict=True, reason="confirmed current defect: cost unit mixing and double deduction")
def test_intended_contract_suspect_4(tmp_path):
    """
    Layer B: Intended-contract test.
    The oracle PnL must correctly deduct only the underlying cost from the gross underlying PnL.
    """
    base_dir = setup_ledger_fixture_suspect4(tmp_path / "run2")
    
    script_path = Path("scripts/generate_mean_reversion_trade_ledger.py").absolute()
    subprocess.run(["python3", str(script_path), "--start-date", "20230101", "--end-date", "20230101"], cwd=base_dir, check=True)
    
    ledger_file = base_dir / "runtime/strategy_validation/MEAN_REVERSION_EXTENSION/phase_4_trade_ledger.jsonl"
    with open(ledger_file) as f: trades = [json.loads(line) for line in f]
    
    trade = trades[0]
    gross_pnl = trade["gross_pnl"]
    net_pnl = trade["net_pnl"]
    
    # Oracle calculation:
    # The gross_pnl is in underlying points.
    # We should only subtract the underlying_cost to get underlying net pnl.
    underlying_cost = trade["underlying_execution_cost"]
    oracle_net_pnl = gross_pnl - underlying_cost
    
    # Asserting oracle is equal to actual will fail, confirming the bug
    assert net_pnl == oracle_net_pnl
