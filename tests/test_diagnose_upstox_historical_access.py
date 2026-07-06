import json
import os
import pytest
from pathlib import Path

def setup_resolution_fixture(classification="UPSTOX_INSTRUMENT_KEYS_RESOLVED", blocker=None):
    res_path = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.json")
    res_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "classification": classification,
        "resolved": {
            "NIFTY": {"instrument_key": "NSE_INDEX|Nifty 50"}
        },
        "blockers": [blocker] if blocker else []
    }
    with open(res_path, "w") as f:
        json.dump(data, f)
    return res_path

def test_diagnostics_never_print_token(monkeypatch, tmp_path):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token_123")
    
    setup_resolution_fixture()
        
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
            for res in data["endpoint_results"]:
                assert res["token_logged"] is False
                assert res["classification"] == "UPSTOX_ACCESS_BLOCKED_403_FORBIDDEN"

def test_diagnostics_classify_missing_token(monkeypatch):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    
    setup_resolution_fixture()
        
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    with open(p, "r") as f:
        data = json.load(f)
        for res in data["endpoint_results"]:
            assert res["classification"] == "UPSTOX_ACCESS_BLOCKED_TOKEN_MISSING"

def test_diagnostics_missing_instrument_master_blocks(monkeypatch):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token_123")
    
    setup_resolution_fixture(classification="UPSTOX_INSTRUMENT_KEYS_BLOCKED", blocker="UPSTOX_NIFTY_KEY_NOT_FOUND")
        
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    with open(p, "r") as f:
        data = json.load(f)
        for res in data["endpoint_results"]:
            assert res["classification"] == "UPSTOX_NIFTY_KEY_NOT_FOUND"

def test_diagnostics_classify_success(monkeypatch):
    from scripts import diagnose_upstox_historical_access
    monkeypatch.setattr("sys.argv", ["diagnose", "--start-date", "2026-07-02", "--end-date", "2026-07-02", "--symbols", "NIFTY", "--interval", "1minute"])
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "fake_token_123")
    
    setup_resolution_fixture()
    
    import urllib.request
    class MockResponse:
        status = 200
        def read(self):
            return b'{"status": "success", "data": {"candles": [["2026-07-02T09:15:00+05:30", 1, 2, 3, 4, 5]]}}'
        def __enter__(self): return self
        def __exit__(self, *args): pass
        
    def mock_urlopen(req, context=None):
        # ensure url encoding is done
        assert "NSE_INDEX%7CNifty%2050" in req.full_url
        return MockResponse()
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    diagnose_upstox_historical_access.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_access_diagnostics.json")
    with open(p, "r") as f:
        data = json.load(f)
        for res in data["endpoint_results"]:
            assert res["classification"] == "UPSTOX_ACCESS_OK"
            assert res["candles_count"] == 1
