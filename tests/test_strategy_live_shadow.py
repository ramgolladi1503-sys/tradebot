import json
import subprocess
from pathlib import Path
import pytest

def test_shadow_missing_option_chain_contract(tmp_path):
    candles_path = tmp_path / "candles.jsonl"
    quotes_path = tmp_path / "quotes.jsonl"
    chain_path = tmp_path / "chain.jsonl"
    out_path = tmp_path / "out.jsonl"
    
    with open(candles_path, "w") as f:
        f.write(json.dumps({"timestamp": "2026-07-01T09:16:00Z", "open": 100, "high": 120, "low": 90, "close": 110}) + "\n")
        f.write(json.dumps({"timestamp": "2026-07-01T09:40:00Z", "open": 110, "high": 150, "low": 100, "close": 130}) + "\n")
        
    with open(chain_path, "w") as f:
        f.write("") # empty chain
        
    with open(quotes_path, "w") as f:
        f.write("")
        
    cmd = [
        "python", "scripts/run_strategy_live_shadow.py",
        "--strategy-id", "SIMPLE_ORB",
        "--current-day-candles-path", str(candles_path),
        "--live-option-quotes-path", str(quotes_path),
        "--option-chain-snapshot-path", str(chain_path),
        "--output-path", str(out_path)
    ]
    subprocess.run(cmd, check=True)
    
    with open(out_path, "r") as f:
        row = json.loads(f.readline())
        
    assert row["rejection_reason"] == "MISSING_OPTION_CONTRACT"
    assert row["real_order_sent"] is False

def test_shadow_missing_quote(tmp_path):
    candles_path = tmp_path / "candles.jsonl"
    quotes_path = tmp_path / "quotes.jsonl"
    chain_path = tmp_path / "chain.jsonl"
    out_path = tmp_path / "out.jsonl"
    
    with open(candles_path, "w") as f:
        f.write(json.dumps({"timestamp": "2026-07-01T09:16:00Z", "open": 100, "high": 120, "low": 90, "close": 110}) + "\n")
        f.write(json.dumps({"timestamp": "2026-07-01T09:40:00Z", "open": 110, "high": 150, "low": 100, "close": 130}) + "\n")
        
    with open(chain_path, "w") as f:
        f.write(json.dumps({"strike": 100, "direction": "CE", "symbol": "TEST", "instrument_key": "TEST_KEY"}) + "\n")
        
    with open(quotes_path, "w") as f:
        f.write("") # missing quotes entirely
        
    cmd = [
        "python", "scripts/run_strategy_live_shadow.py",
        "--strategy-id", "SIMPLE_ORB",
        "--current-day-candles-path", str(candles_path),
        "--live-option-quotes-path", str(quotes_path),
        "--option-chain-snapshot-path", str(chain_path),
        "--output-path", str(out_path)
    ]
    subprocess.run(cmd, check=True)
    
    with open(out_path, "r") as f:
        row = json.loads(f.readline())
        
    assert row["rejection_reason"] == "MISSING_QUOTE"

def test_shadow_stale_quote(tmp_path):
    candles_path = tmp_path / "candles.jsonl"
    quotes_path = tmp_path / "quotes.jsonl"
    chain_path = tmp_path / "chain.jsonl"
    out_path = tmp_path / "out.jsonl"
    
    with open(candles_path, "w") as f:
        f.write(json.dumps({"timestamp": "2026-07-01T09:16:00Z", "open": 100, "high": 120, "low": 90, "close": 110}) + "\n")
        f.write(json.dumps({"timestamp": "2026-07-01T09:40:00Z", "open": 110, "high": 150, "low": 100, "close": 130}) + "\n")
        
    with open(chain_path, "w") as f:
        f.write(json.dumps({"strike": 100, "direction": "CE", "symbol": "TEST", "instrument_key": "TEST_KEY"}) + "\n")
        
    with open(quotes_path, "w") as f:
        # Quote is 1 minute old (stale > 5 sec default limit)
        f.write(json.dumps({"instrument_key": "TEST_KEY", "quote_ts": "2026-07-01T09:39:00Z", "bid": 10, "ask": 11}) + "\n")
        
    cmd = [
        "python", "scripts/run_strategy_live_shadow.py",
        "--strategy-id", "SIMPLE_ORB",
        "--current-day-candles-path", str(candles_path),
        "--live-option-quotes-path", str(quotes_path),
        "--option-chain-snapshot-path", str(chain_path),
        "--output-path", str(out_path)
    ]
    subprocess.run(cmd, check=True)
    
    with open(out_path, "r") as f:
        row = json.loads(f.readline())
        
    assert row["rejection_reason"] == "STALE_QUOTE"

def test_shadow_wide_spread(tmp_path):
    candles_path = tmp_path / "candles.jsonl"
    quotes_path = tmp_path / "quotes.jsonl"
    chain_path = tmp_path / "chain.jsonl"
    out_path = tmp_path / "out.jsonl"
    
    with open(candles_path, "w") as f:
        f.write(json.dumps({"timestamp": "2026-07-01T09:16:00Z", "open": 100, "high": 120, "low": 90, "close": 110}) + "\n")
        f.write(json.dumps({"timestamp": "2026-07-01T09:40:00Z", "open": 110, "high": 150, "low": 100, "close": 130}) + "\n")
        
    with open(chain_path, "w") as f:
        f.write(json.dumps({"strike": 100, "direction": "CE", "symbol": "TEST", "instrument_key": "TEST_KEY"}) + "\n")
        
    with open(quotes_path, "w") as f:
        # Quote is fresh but spread is massive (bid 10, ask 20 => mid 15 => spread is 10/15 = 66% > 1%)
        f.write(json.dumps({"instrument_key": "TEST_KEY", "quote_ts": "2026-07-01T09:40:00Z", "bid": 10, "ask": 20}) + "\n")
        
    cmd = [
        "python", "scripts/run_strategy_live_shadow.py",
        "--strategy-id", "SIMPLE_ORB",
        "--current-day-candles-path", str(candles_path),
        "--live-option-quotes-path", str(quotes_path),
        "--option-chain-snapshot-path", str(chain_path),
        "--output-path", str(out_path)
    ]
    subprocess.run(cmd, check=True)
    
    with open(out_path, "r") as f:
        row = json.loads(f.readline())
        
    assert row["rejection_reason"] == "WIDE_SPREAD"

def test_shadow_bad_quote(tmp_path):
    candles_path = tmp_path / "candles.jsonl"
    quotes_path = tmp_path / "quotes.jsonl"
    chain_path = tmp_path / "chain.jsonl"
    out_path = tmp_path / "out.jsonl"
    
    with open(candles_path, "w") as f:
        f.write(json.dumps({"timestamp": "2026-07-01T09:16:00Z", "open": 100, "high": 120, "low": 90, "close": 110}) + "\n")
        f.write(json.dumps({"timestamp": "2026-07-01T09:40:00Z", "open": 110, "high": 150, "low": 100, "close": 130}) + "\n")
        
    with open(chain_path, "w") as f:
        f.write(json.dumps({"strike": 100, "direction": "CE", "symbol": "TEST", "instrument_key": "TEST_KEY"}) + "\n")
        
    with open(quotes_path, "w") as f:
        # Quote is fresh but bid is 0
        f.write(json.dumps({"instrument_key": "TEST_KEY", "quote_ts": "2026-07-01T09:40:00Z", "bid": 0, "ask": 20}) + "\n")
        
    cmd = [
        "python", "scripts/run_strategy_live_shadow.py",
        "--strategy-id", "SIMPLE_ORB",
        "--current-day-candles-path", str(candles_path),
        "--live-option-quotes-path", str(quotes_path),
        "--option-chain-snapshot-path", str(chain_path),
        "--output-path", str(out_path)
    ]
    subprocess.run(cmd, check=True)
    
    with open(out_path, "r") as f:
        row = json.loads(f.readline())
        
    assert row["rejection_reason"] == "BAD_QUOTE"

def test_fixture_mode_still_rejected_by_analyzer(tmp_path):
    out_path = tmp_path / "out.jsonl"
    report_path = tmp_path / "report.json"
    
    cmd = [
        "python", "scripts/run_strategy_live_shadow.py",
        "--strategy-id", "SIMPLE_ORB",
        "--fixture-mode",
        "--output-path", str(out_path)
    ]
    subprocess.run(cmd, check=True)
    
    cmd2 = [
        "python", "scripts/analyze_strategy_live_shadow.py",
        "--strategy-id", "SIMPLE_ORB",
        "--shadow-trades-path", str(out_path),
        "--output-path", str(report_path)
    ]
    subprocess.run(cmd2, check=True)
    
    with open(report_path, "r") as f:
        report = json.load(f)
        
    assert report["passed"] is False
    assert "FIXTURE_EVIDENCE_NOT_ALLOWED" in report["violations"]

def test_shadow_valid_execution(tmp_path):
    candles_path = tmp_path / "candles.jsonl"
    quotes_path = tmp_path / "quotes.jsonl"
    chain_path = tmp_path / "chain.jsonl"
    out_path = tmp_path / "out.jsonl"
    
    with open(candles_path, "w") as f:
        f.write(json.dumps({"timestamp": "2026-07-01T09:16:00Z", "open": 100, "high": 120, "low": 90, "close": 110}) + "\n")
        f.write(json.dumps({"timestamp": "2026-07-01T09:40:00Z", "open": 110, "high": 150, "low": 100, "close": 130}) + "\n")
        
    with open(chain_path, "w") as f:
        f.write(json.dumps({"strike": 100, "direction": "CE", "symbol": "TEST", "instrument_key": "TEST_KEY"}) + "\n")
        
    with open(quotes_path, "w") as f:
        # Valid fresh tight quote
        f.write(json.dumps({"instrument_key": "TEST_KEY", "quote_ts": "2026-07-01T09:40:00Z", "bid": 10.0, "ask": 10.05}) + "\n")
        
    cmd = [
        "python", "scripts/run_strategy_live_shadow.py",
        "--strategy-id", "SIMPLE_ORB",
        "--current-day-candles-path", str(candles_path),
        "--live-option-quotes-path", str(quotes_path),
        "--option-chain-snapshot-path", str(chain_path),
        "--output-path", str(out_path)
    ]
    subprocess.run(cmd, check=True)
    
    with open(out_path, "r") as f:
        row = json.loads(f.readline())
        
    assert row["rejection_reason"] is None
    assert row["real_order_sent"] is False
    assert row["evidence_mode"] == "live_capture"
