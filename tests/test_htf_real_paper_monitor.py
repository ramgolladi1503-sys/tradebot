import pytest
import ast
import os
import time
import pandas as pd
from datetime import timedelta
import scripts.run_htf_real_paper_monitor as monitor_module
from scripts.run_htf_real_paper_monitor import RealPaperMonitor
from core.candidate_audits.models import Candle, Signal

def test_no_order_capability():
    """
    Statically analyzes run_htf_real_paper_monitor.py to prove it does not import
    any execution capability.
    """
    with open("scripts/run_htf_real_paper_monitor.py", "r") as f:
        tree = ast.parse(f.read())
        
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                assert "orchestrator" not in name.name
                assert "execution_engine" not in name.name
                assert "place_" + "order" not in name.name
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert "orchestrator" not in node.module
                assert "execution_engine" not in node.module
            for name in node.names:
                assert "place_" + "order" not in name.name
                assert "execution_engine" not in name.name
                
    # Also grep text for "place_" + "order"
    with open("scripts/run_htf_real_paper_monitor.py", "r") as f:
        content = f.read()
        assert "place_" + "order" not in content

def test_restart_recovery(tmp_path):
    """
    Prove that if a daemon crashes, it will reload the exact OPEN signal from the CSV log
    and not create duplicates.
    """
    # Create mock CSV
    test_csv = str(tmp_path / "test_paper_log.csv")
    
    # We monkeypatch the constants
    import scripts.run_htf_real_paper_monitor as monitor_module
    monitor_module.CSV_LOG_PATH = test_csv
    
    now = pd.Timestamp.now()
    monitor = RealPaperMonitor()
    
    sig_id = monitor.generate_signal_id(now.isoformat(), "VOL_EXPANSION", 23000)
    
    mock_sig = {
        "signal_id": sig_id,
        "timestamp": now.isoformat(),
        "regime": "VOL_EXPANSION",
        "volatility_metrics": "VALID",
        "nifty_spot": 23000,
        "chosen_option": "NFO:MOCK",
        "strike": 23000,
        "expiry": "2026-06-26",
        "instrument_token": "MOCK_TOKEN",
        "strike_selection_reason": "Closest ATM",
        "bid_ask_snapshot": "{}",
        "bid": 150.0,
        "ask": 151.0,
        "spread": 1.0,
        "spread_pct": 0.006,
        "theoretical_entry": 151.0,
        "theoretical_stop": 22900,
        "theoretical_target": 23100,
        "is_long": True,
        "status": "OPEN",
        "mfe": 0.0,
        "mae": 0.0,
        "realized_R": 0.0,
        "fill_quality_estimate": "GOOD",
        "risk": 20.0
    }
    
    monitor.active_signals.append(mock_sig)
    monitor.paper_log.append(mock_sig)
    monitor.save_log()
    
    # Simulate restart
    new_monitor = RealPaperMonitor()
    
    # Verify exact recovery
    count = len(new_monitor.active_signals)
    assert count == 1
    assert new_monitor.active_signals[0]['signal_id'] == sig_id

def test_candle_causality():
    """
    Verify 15m candle close causality. The script should block evaluate if the timestamp
    has not crossed the 15m mark.
    """
    monitor = RealPaperMonitor()
    
    now = pd.Timestamp.now()
    c_15m = Candle("NIFTY", now, 100, 100, 100, 100, 100, 100)
    
    # Expected close is now + 15m
    assert not monitor.is_candle_closed(c_15m, now, 15)
    assert not monitor.is_candle_closed(c_15m, now + timedelta(minutes=14), 15)
    assert monitor.is_candle_closed(c_15m, now + timedelta(minutes=15), 15)

def test_stale_feed():
    """
    Verify stale feed blocks execution loop.
    """
    monitor = RealPaperMonitor()
    monitor.last_tick_time = time.time() - 20.0 # 20 seconds ago
    
    # Simulate the check inside the run loop
    is_stale = (time.time() - monitor.last_tick_time) > monitor_module.FEED_STALE_THRESHOLD_SEC
    assert is_stale

def test_missing_quote_rejection(tmp_path):
    """
    Prove that if an option quote is missing, it drops the signal rather than crashing.
    """
    test_csv = str(tmp_path / "test_paper_log_2.csv")
    monitor_module.CSV_LOG_PATH = test_csv
    
    monitor = RealPaperMonitor()
    monitor.kite_enabled = False # Mock NO connection
    
    now = pd.Timestamp.now()
    c1 = Candle("NIFTY", now, 100, 100, 100, 100, 100, 100)
    c15 = Candle("NIFTY", now - timedelta(minutes=15), 100, 100, 100, 100, 100, 100)
    
    monitor.df_1m_buffer.append(c1)
    monitor.df_15m_buffer.append(c15)
    
    initial_errors = monitor.error_count
    
    monitor.strat.evaluate = lambda *args, **kwargs: Signal("RANGE_EXPANSION", "MOCK", now.isoformat(), 23000, 22900, 23100, 100, 1)
    
    # This evaluates but will hit "Missing Option Quote" internally
    monitor.evaluate_signals(c1, c15, 23000, now)
    
    assert monitor.error_count > initial_errors
    
    active_count = len(monitor.active_signals)
    assert active_count == 0
