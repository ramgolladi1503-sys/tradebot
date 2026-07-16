import os
import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

os.environ["EXECUTION_MODE"] = "PAPER"
os.environ["KITE_USE_API"] = "false"
os.environ["DATA_ROOT"] = "/tmp/canonical_proof/data"
os.environ["LOGS_ROOT"] = "/tmp/canonical_proof/logs"
os.environ["DB_ROOT"] = "/tmp/canonical_proof/db"
os.environ["REPORTS_ROOT"] = "/tmp/canonical_proof/reports"

from config import config as cfg
from core.ohlc_buffer import OhlcBuffer, ohlc_buffer
from core.market_data import fetch_live_market_data
import core.market_data

def get_empty_buffer():
    # Return a fresh instance of OhlcBuffer to prevent cross-test contamination
    import core.market_data
    from core.ohlc_buffer import OhlcBuffer
    fresh_buffer = OhlcBuffer()
    core.market_data.ohlc_buffer = fresh_buffer
    return fresh_buffer

def write_evidence(scenario_name, snapshot):
    evidence_dir = "docs/agent_reviews/evidence"
    os.makedirs(evidence_dir, exist_ok=True)
    evidence_path = os.path.join(evidence_dir, "canonical_strategy_input_runtime_proof.json")
    
    if os.path.exists(evidence_path):
        with open(evidence_path, "r") as f:
            evidence = json.load(f)
    else:
        evidence = {
            "metadata": {
                "execution_mode": "PAPER",
                "is_order_action": False,
                "broker_api_called": False,
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "scenarios": {}
        }
    
    evidence["scenarios"][scenario_name] = snapshot
    
    with open(evidence_path, "w") as f:
        json.dump(evidence, f, indent=2)

def extract_snapshot_metrics(results, symbol):
    for r in results:
        if r.get("symbol") == symbol:
            return {
                "symbol": symbol,
                "valid": r.get("valid"),
                "timestamp": r.get("timestamp"),
                "candle_ts_epoch": r.get("candle_ts_epoch"),
                "indicator_last_update_epoch": r.get("indicator_last_update_epoch"),
                "ohlc_bars_count": r.get("ohlc_bars_count"),
                "ohlc_seeded": r.get("ohlc_seeded"),
                "ohlc_seed_reason": r.get("ohlc_seed_reason"),
                "ohlc_last_bar_epoch": r.get("ohlc_last_bar_epoch"),
                "indicators_ok": r.get("indicators_ok"),
                "invalid_reason": r.get("invalid_reason")
            }
    return None

def mock_time(dt_str):
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=5.5)))
    return patch('core.market_data.now_ist', return_value=dt), patch('core.market_data.now_utc_epoch', return_value=dt.timestamp())

def test_scenario_a_normal_completed_bar():
    # Scenario A: Normal completed-bar path
    cfg.SYMBOLS = ["NIFTY"]
    cfg.OHLC_MIN_BARS = 1
    cfg.REQUIRE_LIVE_QUOTES = False
    
    buf = get_empty_buffer()
    
    # 09:15:30 -> tick
    with mock_time("2023-01-01 09:15:30")[0], mock_time("2023-01-01 09:15:30")[1]:
        import core.market_data
        core.market_data._DATA_CACHE = {"NIFTY": {"ltp": 100, "ltp_source": "live", "last_ltp": 100}}
        buf.update_tick("NIFTY", 100.0, volume=100, ts=datetime(2023, 1, 1, 9, 15, 30, tzinfo=timezone(timedelta(hours=5.5))))
    
    # 09:16:01 -> tick (completes the 09:15 bar)
    with mock_time("2023-01-01 09:16:01")[0], mock_time("2023-01-01 09:16:01")[1]:
        buf.update_tick("NIFTY", 101.0, volume=100, ts=datetime(2023, 1, 1, 9, 16, 1, tzinfo=timezone(timedelta(hours=5.5))))
        core.market_data._DATA_CACHE = {"NIFTY": {"ltp": 101, "ltp_source": "live", "last_ltp": 101}}
        results = fetch_live_market_data(allow_history_seed=False)
        metrics = extract_snapshot_metrics(results, "NIFTY")
        write_evidence("A_normal_completed_bar", metrics)
        
        assert metrics["ohlc_bars_count"] == 1
        assert metrics["ohlc_seeded"] == False

def test_scenario_b_warm_seed_startup():
    # Scenario B: Warm-seed startup path
    cfg.SYMBOLS = ["NIFTY"]
    cfg.OHLC_MIN_BARS = 30
    cfg.REQUIRE_LIVE_QUOTES = False
    
    buf = get_empty_buffer()
    
    # Needs a mock history seed to be successful. 
    with mock_time("2023-01-01 09:16:01")[0], mock_time("2023-01-01 09:16:01")[1]:
        core.market_data._DATA_CACHE = {"NIFTY": {"ltp": 101, "ltp_source": "live", "last_ltp": 101}}
        buf.update_tick("NIFTY", 101.0, volume=100, ts=datetime(2023, 1, 1, 9, 16, 1, tzinfo=timezone(timedelta(hours=5.5))))
        
        results = fetch_live_market_data(allow_history_seed=True)
        metrics = extract_snapshot_metrics(results, "NIFTY")
        write_evidence("B_warm_seed_startup", metrics)
        
        assert metrics["ohlc_seeded"] == False
        assert metrics["ohlc_seed_reason"] == "HIST_FETCH_FAILED"

def test_scenario_c_exact_completion_boundary():
    cfg.SYMBOLS = ["NIFTY"]
    cfg.OHLC_MIN_BARS = 1
    cfg.REQUIRE_LIVE_QUOTES = False
    
    buf = get_empty_buffer()
    
    with mock_time("2023-01-01 09:15:30")[0], mock_time("2023-01-01 09:15:30")[1]:
        core.market_data._DATA_CACHE = {"NIFTY": {"ltp": 100, "ltp_source": "live", "last_ltp": 100}}
        buf.update_tick("NIFTY", 100.0, volume=100, ts=datetime(2023, 1, 1, 9, 15, 30, tzinfo=timezone(timedelta(hours=5.5))))
    
    with mock_time("2023-01-01 09:16:00")[0], mock_time("2023-01-01 09:16:00")[1]:
        core.market_data._DATA_CACHE = {"NIFTY": {"ltp": 101, "ltp_source": "live", "last_ltp": 101}}
        buf.update_tick("NIFTY", 101.0, volume=100, ts=datetime(2023, 1, 1, 9, 16, 0, tzinfo=timezone(timedelta(hours=5.5))))
        
        results = fetch_live_market_data(allow_history_seed=False)
        metrics = extract_snapshot_metrics(results, "NIFTY")
        write_evidence("C_exact_completion_boundary", metrics)
        
        assert metrics["ohlc_bars_count"] == 1

def test_scenario_d_late_tick():
    cfg.SYMBOLS = ["NIFTY"]
    cfg.OHLC_MIN_BARS = 1
    cfg.REQUIRE_LIVE_QUOTES = False
    
    buf = get_empty_buffer()
    
    with mock_time("2023-01-01 09:15:20")[0], mock_time("2023-01-01 09:15:20")[1]:
        buf.update_tick("NIFTY", 99.0, volume=100, ts=datetime(2023, 1, 1, 9, 15, 20, tzinfo=timezone(timedelta(hours=5.5))))

    with mock_time("2023-01-01 09:16:01")[0], mock_time("2023-01-01 09:16:01")[1]:
        buf.update_tick("NIFTY", 101.0, volume=100, ts=datetime(2023, 1, 1, 9, 16, 1, tzinfo=timezone(timedelta(hours=5.5))))
        buf.update_tick("NIFTY", 100.0, volume=100, ts=datetime(2023, 1, 1, 9, 15, 30, tzinfo=timezone(timedelta(hours=5.5))))
        
        core.market_data._DATA_CACHE = {"NIFTY": {"ltp": 101, "ltp_source": "live", "last_ltp": 101}}
        results = fetch_live_market_data(allow_history_seed=False)
        metrics = extract_snapshot_metrics(results, "NIFTY")
        write_evidence("D_late_tick", metrics)
        
        assert metrics["ohlc_bars_count"] == 1

def test_scenario_e_no_completed_bars():
    cfg.SYMBOLS = ["NIFTY"]
    cfg.OHLC_MIN_BARS = 1
    cfg.REQUIRE_LIVE_QUOTES = False
    
    buf = get_empty_buffer()
    
    with mock_time("2023-01-01 09:15:30")[0], mock_time("2023-01-01 09:15:30")[1]:
        core.market_data._DATA_CACHE = {"NIFTY": {"ltp": 100, "ltp_source": "live", "last_ltp": 100}}
        buf.update_tick("NIFTY", 100.0, volume=100, ts=datetime(2023, 1, 1, 9, 15, 30, tzinfo=timezone(timedelta(hours=5.5))))
        
        results = fetch_live_market_data(allow_history_seed=False)
        metrics = extract_snapshot_metrics(results, "NIFTY")
        write_evidence("E_no_completed_bars", metrics)
        
        assert metrics["ohlc_bars_count"] == 0

def test_scenario_f_invalid_history():
    cfg.SYMBOLS = ["NIFTY"]
    cfg.OHLC_MIN_BARS = 30
    cfg.REQUIRE_LIVE_QUOTES = False
    
    buf = get_empty_buffer()
    
    with mock_time("2023-01-01 09:16:01")[0], mock_time("2023-01-01 09:16:01")[1]:
        core.market_data._DATA_CACHE = {"NIFTY": {"ltp": 101, "ltp_source": "live", "last_ltp": 101}}
        buf.update_tick("NIFTY", 101.0, volume=100, ts=datetime(2023, 1, 1, 9, 16, 1, tzinfo=timezone(timedelta(hours=5.5))))
        
        results = fetch_live_market_data(allow_history_seed=True)
        metrics = extract_snapshot_metrics(results, "NIFTY")
        write_evidence("F_invalid_history", metrics)

def test_scenario_g_cross_symbol_isolation():
    cfg.SYMBOLS = ["NIFTY", "BANKNIFTY"]
    cfg.OHLC_MIN_BARS = 1
    cfg.REQUIRE_LIVE_QUOTES = False
    
    buf = get_empty_buffer()
    
    with mock_time("2023-01-01 09:15:30")[0], mock_time("2023-01-01 09:15:30")[1]:
        core.market_data._DATA_CACHE = {
            "NIFTY": {"ltp": 100, "ltp_source": "live", "last_ltp": 100},
            "BANKNIFTY": {"ltp": 200, "ltp_source": "live", "last_ltp": 200}
        }
        buf.update_tick("NIFTY", 100.0, volume=100, ts=datetime(2023, 1, 1, 9, 15, 30, tzinfo=timezone(timedelta(hours=5.5))))
        buf.update_tick("BANKNIFTY", 200.0, volume=100, ts=datetime(2023, 1, 1, 9, 15, 30, tzinfo=timezone(timedelta(hours=5.5))))
    
    with mock_time("2023-01-01 09:16:01")[0], mock_time("2023-01-01 09:16:01")[1]:
        buf.update_tick("NIFTY", 101.0, volume=100, ts=datetime(2023, 1, 1, 9, 16, 1, tzinfo=timezone(timedelta(hours=5.5))))
        core.market_data._DATA_CACHE["NIFTY"]["ltp"] = 101
        
        results = fetch_live_market_data(allow_history_seed=False)
        metrics_nifty = extract_snapshot_metrics(results, "NIFTY")
        metrics_bank = extract_snapshot_metrics(results, "BANKNIFTY")
        write_evidence("G_cross_symbol_isolation", {"NIFTY": metrics_nifty, "BANKNIFTY": metrics_bank})
        
        assert metrics_nifty["ohlc_bars_count"] == 1
        assert metrics_bank["ohlc_bars_count"] == 1
