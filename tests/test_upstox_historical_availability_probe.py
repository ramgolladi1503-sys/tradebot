import json
import os
import pytest
from pathlib import Path

def test_probe_missing_token(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from scripts import probe_upstox_historical_availability
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "")
    
    import sys
    monkeypatch.setattr(sys, 'argv', ['probe.py', '--start-date', '2024-07-01', '--end-date', '2026-07-03', '--symbols', 'NIFTY', 'BANKNIFTY', '--interval', '1minute'])
    
    probe_upstox_historical_availability.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_availability_probe.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_HISTORY_BLOCKED_TOKEN_MISSING"

def test_probe_missing_keys(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from scripts import probe_upstox_historical_availability
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock_token")
    
    import sys
    monkeypatch.setattr(sys, 'argv', ['probe.py', '--start-date', '2024-07-01', '--end-date', '2026-07-03', '--symbols', 'NIFTY', 'BANKNIFTY', '--interval', '1minute'])
    
    # Missing resolution file
    probe_upstox_historical_availability.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_availability_probe.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_HISTORY_BLOCKED_INSTRUMENT_KEY_FAILURE"

def test_probe_api_error_403(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from scripts import probe_upstox_historical_availability
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock_token")
    
    out_dir = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    res_data = {
        "classification": "UPSTOX_INSTRUMENT_KEYS_RESOLVED",
        "resolved": {
            "NIFTY": {"instrument_key": "NSE_INDEX|Nifty 50"},
            "BANKNIFTY": {"instrument_key": "NSE_INDEX|Nifty Bank"}
        }
    }
    with open(out_dir / "upstox_instrument_resolution.json", "w") as f:
        json.dump(res_data, f)
        
    import sys
    monkeypatch.setattr(sys, 'argv', ['probe.py', '--start-date', '2024-07-01', '--end-date', '2026-07-03', '--symbols', 'NIFTY', 'BANKNIFTY', '--interval', '1minute'])
    
    import urllib.request
    import urllib.error
    
    def mock_urlopen(req, context=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    probe_upstox_historical_availability.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_availability_probe.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_HISTORY_BLOCKED_API_ERROR"
        assert data["api_status"] == "403_FORBIDDEN"

def test_probe_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    from scripts import probe_upstox_historical_availability
    monkeypatch.setenv("UPSTOX_ACCESS_TOKEN", "mock_token")
    
    out_dir = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    res_data = {
        "classification": "UPSTOX_INSTRUMENT_KEYS_RESOLVED",
        "resolved": {
            "NIFTY": {"instrument_key": "NSE_INDEX|Nifty 50"},
            "BANKNIFTY": {"instrument_key": "NSE_INDEX|Nifty Bank"}
        }
    }
    with open(out_dir / "upstox_instrument_resolution.json", "w") as f:
        json.dump(res_data, f)
        
    import sys
    monkeypatch.setattr(sys, 'argv', ['probe.py', '--start-date', '2024-07-01', '--end-date', '2026-07-03', '--symbols', 'NIFTY', 'BANKNIFTY', '--interval', '1minute'])
    
    import urllib.request
    from unittest.mock import MagicMock
    
    def mock_urlopen(req, context=None):
        mock = MagicMock()
        mock.read.return_value = b'{}'
        return mock
        
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)
    
    probe_upstox_historical_availability.main()
    
    p = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION/upstox_availability_probe.json")
    with open(p, "r") as f:
        data = json.load(f)
        assert data["classification"] == "UPSTOX_HISTORY_AVAILABLE"
        assert data["api_status"] == "OK"
