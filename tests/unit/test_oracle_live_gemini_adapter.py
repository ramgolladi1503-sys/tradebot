import pytest
from unittest.mock import MagicMock
from core.oracle_live_gemini_adapter import OracleGeminiLiveAdapter, OracleAdviceSchema, OracleActivePosition

def test_oracle_schema_validation():
    advice = OracleAdviceSchema(
        action="BUY_PE",
        strike="NIFTY 23200 PE",
        entry_limit_price=38.00,
        stop_loss_price=30.00,
        breakeven_trigger_price=50.00,
        target_price=68.00,
        spot_reference=23215.5,
        rationale="NIFTY touching lower reversal boundary with wick rejection."
    )
    assert advice.action == "BUY_PE"
    assert advice.entry_limit_price == 38.00
    assert advice.stop_loss_price == 30.00
    assert advice.target_price == 68.00

def test_oracle_active_position_lifecycle():
    pos = OracleActivePosition(
        strike="NIFTY 23200 PE",
        entry_price=38.00,
        current_ltp=38.00,
        stop_loss_price=30.00,
        breakeven_price=50.00,
        target_price=68.00,
        entry_time=1000.0,
    )
    assert pos.is_breakeven_locked is False
    pos.update_ltp(52.00)
    assert pos.current_ltp == 52.00
    # Simulate move to breakeven
    pos.stop_loss_price = pos.entry_price
    pos.is_breakeven_locked = True
    assert pos.stop_loss_price == 38.00
    assert pos.is_breakeven_locked is True

def test_oracle_state_machine_transition():
    adapter = OracleGeminiLiveAdapter(api_key="mock_key", poll_interval_sec=0.0, signal_cooldown_sec=10.0)
    adapter.client = MagicMock()
    
    mock_resp = MagicMock()
    mock_resp.parsed = OracleAdviceSchema(
        action="BUY_PE",
        strike="NIFTY 23200 PE",
        entry_limit_price=38.00,
        stop_loss_price=30.00,
        breakeven_trigger_price=50.00,
        target_price=68.00,
        spot_reference=23215.0,
        rationale="Test lower reversal touch."
    )
    adapter.client.models.generate_content.return_value = mock_resp

    # First evaluation -> enters trade
    advice = adapter.evaluate_market_snapshot(
        spot=23215.0,
        or_high=23317.0,
        or_low=23211.8,
        candidate_pe_symbol="NIFTY 23200 PE",
        candidate_pe_ltp=38.00,
    )
    assert advice is not None
    assert advice.action == "BUY_PE"
    assert adapter.active_position is not None
    assert adapter.active_position.strike == "NIFTY 23200 PE"
    assert adapter.active_position.entry_price == 38.00

    # Second evaluation immediately -> in cooldown so returns None (no flapping)
    advice_suppressed = adapter.evaluate_market_snapshot(
        spot=23215.0,
        or_high=23317.0,
        or_low=23211.8,
    )
    assert advice_suppressed is None
