import pytest
import time
from unittest.mock import MagicMock, patch
from core.strategy_requirements import validate_strategy_requirements
from core.orchestrator_parts.decisions import log_decision_safe

def test_breakout_continuation_warmup_incomplete():
    snapshot = {"ts_epoch": time.time(), "option_chain_last_ts": time.time(), "ohlc_bars_count": 50}
    trade = MagicMock()
    valid, vetoes = validate_strategy_requirements("BREAKOUT_CONTINUATION", snapshot, trade, time.time())
    assert not valid
    assert "WARMUP_INCOMPLETE" in vetoes

def test_breakout_continuation_feed_stale():
    # 300 seconds ago
    old_time = time.time() - 300
    snapshot = {"ts_epoch": old_time, "option_chain_last_ts": old_time, "ohlc_bars_count": 100}
    trade = MagicMock()
    valid, vetoes = validate_strategy_requirements("BREAKOUT_CONTINUATION", snapshot, trade, time.time())
    assert not valid
    assert "STALE_UNDERLYING" in vetoes
    assert "STALE_OPTION_QUOTE" in vetoes

@patch("core.telegram_alerts.send_telegram_message")
def test_monitoring_degraded_alert_emitted_for_feed_stale(mock_send):
    orch = MagicMock()
    orch.fetch_open_positions_dict.return_value = {"NIFTY": {"qty": 50}}
    
    event = {
        "symbol": "NIFTY",
        "veto_reasons": ["FEED_STALE", "WARMUP_INCOMPLETE"]
    }
    
    def log_decision_fn(e):
        return "fake_id"
        
    log_decision_safe(orch, event, log_decision_fn=log_decision_fn)
    
    mock_send.assert_called_once()
    assert "MONITORING-DEGRADED" in mock_send.call_args[0][0]

@patch("core.telegram_alerts.send_telegram_message")
def test_monitoring_degraded_alert_not_emitted_if_no_open_positions(mock_send):
    orch = MagicMock()
    orch.fetch_open_positions_dict.return_value = {}
    
    event = {
        "symbol": "NIFTY",
        "veto_reasons": ["FEED_STALE"]
    }
    
    def log_decision_fn(e):
        return "fake_id"
        
    log_decision_safe(orch, event, log_decision_fn=log_decision_fn)
    
    mock_send.assert_not_called()
