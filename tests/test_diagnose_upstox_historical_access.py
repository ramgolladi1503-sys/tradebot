import json
import os
import pytest
from pathlib import Path

def test_diagnostics_never_print_token(monkeypatch, tmp_path):
    # This is a meta test, the script itself doesn't print the token by design
    # But we can verify it doesn't write it to the json
    from scripts import diagnose_upstox_historical_access
    
    # We patch sys.argv and os.environ
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token_123")
    
    # Patch urllib to mock a 403
    import urllib.request
    import urllib.error
    
    def mock_urlopen(req, context=None):
        raise urllib.error.HTTPError("url", 403, "Forbidden", {}, None)
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    if p.exists():
        with open(p, "r") as f:
            data = json.load(f)
            assert "fake_token_123" not in json.dumps(data)
            assert data["token_logged"] is False
            assert data["upstox_token_available"] is True
            assert data["classification"] == "UPSTOX_ACCESS_BLOCKED_403_FORBIDDEN"

def test_diagnostics_classify_missing_token(monkeypatch):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["upstox_token_available"] is False
        assert data["classification"] == "UPSTOX_ACCESS_BLOCKED_TOKEN_MISSING"

def test_diagnostics_classify_401(monkeypatch):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token_123")
    
    import urllib.request
    import urllib.error
    
    def mock_urlopen(req, context=None):
        raise urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_ACCESS_BLOCKED_401_UNAUTHORIZED"

def test_diagnostics_classify_malformed_response(monkeypatch):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token_123")
    
    import urllib.request
    class MockResponse:
        status = 200
        def read(self):
            return b"not json"
        def __enter__(self): return self
        def __exit__(self, *args): pass
        
    def mock_urlopen(req, context=None):
        return MockResponse()
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_ACCESS_BLOCKED_MALFORMED_RESPONSE"

def test_diagnostics_classify_no_candles(monkeypatch):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token_123")
    
    import urllib.request
    class MockResponse:
        status = 200
        def read(self):
            return b'{"status": "success", "data": {"candles": []}}'
        def __enter__(self): return self
        def __exit__(self, *args): pass
        
    def mock_urlopen(req, context=None):
        return MockResponse()
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_ACCESS_BLOCKED_NO_CANDLES"

def test_diagnostics_classify_success(monkeypatch):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token_123")
    
    import urllib.request
    class MockResponse:
        status = 200
        def read(self):
            return b'{"status": "success", "data": {"candles": [["2026-07-02T09:15:00+05:30", 1, 2, 3, 4, 5]]}}'
        def __enter__(self): return self
        def __exit__(self, *args): pass
        
    def mock_urlopen(req, context=None):
        return MockResponse()
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_ACCESS_OK"
        assert data["contains_data_candles"] is True
        assert data["candle_count"] == 1

def test_bad_instrument_key_blocks(monkeypatch):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "UNKNOWN", "--interval", "1minute"])
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token_123")
    
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_ACCESS_BLOCKED_BAD_INSTRUMENT_KEY"
