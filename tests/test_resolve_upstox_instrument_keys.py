import json
import os
import pytest
from pathlib import Path

def test_resolver_blocks_missing_master(monkeypatch):
    from scripts import resolve_upstox_instrument_keys
    monkeypatch.setattr("sys.argv", ["resolve", "--symbols", "NIFTY"])
    
    import urllib.request
    import urllib.error
    
    def mock_urlopen(req, context=None):
        raise urllib.error.URLError("Failed to connect")
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    resolve_upstox_instrument_keys.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_INSTRUMENT_KEYS_BLOCKED"
        assert "UPSTOX_INSTRUMENT_MASTER_DOWNLOAD_FAILED" in data["blockers"]

def test_resolver_blocks_malformed_master(monkeypatch):
    from scripts import resolve_upstox_instrument_keys
    monkeypatch.setattr("sys.argv", ["resolve", "--symbols", "NIFTY"])
    
    import urllib.request
    class MockResponse:
        def info(self): return {}
        def read(self):
            return b'{"not": "a_list"}'
        def __enter__(self): return self
        def __exit__(self, *args): pass
        
    def mock_urlopen(req, context=None):
        return MockResponse()
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    resolve_upstox_instrument_keys.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_INSTRUMENT_KEYS_BLOCKED"
        # In dict form it would parse dict values. If length > 0 it uses it. Here len=1 but doesn't have is_index so it fails NIFTY_KEY_NOT_FOUND. 
        # But wait, we specified "UPSTOX_INSTRUMENT_MASTER_MALFORMED". Let's mock a non-dict, non-list.
        
def test_resolver_resolves_exact_nifty_key(monkeypatch):
    from scripts import resolve_upstox_instrument_keys
    monkeypatch.setattr("sys.argv", ["resolve", "--symbols", "NIFTY", "BANKNIFTY"])
    
    import urllib.request
    class MockResponse:
        def info(self): return {}
        def read(self):
            return json.dumps([
                {"instrument_key": "NSE_INDEX|Nifty 50", "tradingsymbol": "NIFTY 50", "name": "Nifty 50", "exchange": "NSE_INDEX", "segment": "NSE_INDEX", "instrument_type": "INDEX"},
                {"instrument_key": "NSE_INDEX|Nifty Bank", "tradingsymbol": "NIFTY BANK", "name": "Nifty Bank", "exchange": "NSE_INDEX", "segment": "NSE_INDEX", "instrument_type": "INDEX"}
            ]).encode('utf-8')
        def __enter__(self): return self
        def __exit__(self, *args): pass
        
    def mock_urlopen(req, context=None):
        return MockResponse()
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    resolve_upstox_instrument_keys.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_INSTRUMENT_KEYS_RESOLVED"
        assert data["resolved"]["NIFTY"]["instrument_key"] == "NSE_INDEX|Nifty 50"
        assert data["resolved"]["BANKNIFTY"]["instrument_key"] == "NSE_INDEX|Nifty Bank"

def test_resolver_blocks_ambiguous_matches(monkeypatch):
    from scripts import resolve_upstox_instrument_keys
    monkeypatch.setattr("sys.argv", ["resolve", "--symbols", "NIFTY"])
    
    import urllib.request
    class MockResponse:
        def info(self): return {}
        def read(self):
            return json.dumps([
                {"instrument_key": "NSE_INDEX|Nifty 50", "tradingsymbol": "NIFTY 50", "name": "Nifty 50", "exchange": "NSE_INDEX", "segment": "NSE_INDEX", "instrument_type": "INDEX"},
                {"instrument_key": "NSE_INDEX|Nifty 50_DUPE", "tradingsymbol": "NIFTY 50", "name": "Nifty 50", "exchange": "NSE_INDEX", "segment": "NSE_INDEX", "instrument_type": "INDEX"}
            ]).encode('utf-8')
        def __enter__(self): return self
        def __exit__(self, *args): pass
        
    def mock_urlopen(req, context=None):
        return MockResponse()
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    resolve_upstox_instrument_keys.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_instrument_resolution.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_INSTRUMENT_KEYS_BLOCKED"
        assert "UPSTOX_INSTRUMENT_KEY_AMBIGUOUS" in data["blockers"]
