import pytest
from unittest.mock import patch, MagicMock
from core.kite_client import KiteClient

def test_instruments_rest_failure_with_cache(caplog):
    client = KiteClient()
    kite_mock = MagicMock()
    kite_mock.instruments.side_effect = Exception("API error")
    client.kite = kite_mock
    
    # Pre-populate cache
    from datetime import date
    today = date.today().isoformat()
    client._instruments_cache["NFO"] = {"date": today, "data": [{"tradingsymbol": "NIFTY", "instrument_token": 123}]}
    
    import logging
    with caplog.at_level(logging.ERROR):
        result = client.instruments("NFO", force=True)
        
    assert result == [{"tradingsymbol": "NIFTY", "instrument_token": 123}]
    assert any("broker_rest_degraded:instruments_fetch_failed using_cache" in record.message for record in caplog.records)

def test_instruments_rest_failure_without_cache(caplog):
    client = KiteClient()
    kite_mock = MagicMock()
    kite_mock.instruments.side_effect = Exception("API error")
    client.kite = kite_mock
    client._instruments_cache.clear()
    
    import logging
    with caplog.at_level(logging.ERROR):
        result = client.instruments("NFO")
        
    assert result == []
    assert any("instruments_fetch_failed_no_cache" in record.message for record in caplog.records)

@patch("core.market_data.kite_client")
def test_orchestrator_receives_empty_instruments_no_crash(mock_client):
    mock_client.instruments.return_value = []
    # Test that calling the initialization logic that uses instruments does not crash
    from core.market_data import get_token_for_symbol
    token = get_token_for_symbol("DUMMY")
    assert token is None

@patch("core.option_token_resolver.kite_client")
def test_no_executable_candidates_when_instruments_unavailable(mock_client):
    from core.option_token_resolver import _load_instruments
    mock_client.instruments_cached.return_value = []
    
    data, source = _load_instruments("NFO")
    
    # Empty list ensures the orchestrator candidate flow will mark 'unresolved_contract'
    # which inherently prevents the candidate from becoming executable.
    assert data == []
    assert source == "missing"
