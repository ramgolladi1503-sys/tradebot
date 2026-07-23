import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from scripts.fetch_upstox_constituent_history_v3 import get_monthly_chunks, fetch_chunk

def test_v3_url_construction_and_no_v2_fallback():
    with tempfile.TemporaryDirectory() as td:
        with patch("urllib.request.urlopen") as mock_open:
            # Mock success response
            mock_response = MagicMock()
            mock_response.status = 200
            mock_response.read.return_value = b'{"status":"success","data":{"candles":[["2026-07-15T09:15:00+05:30",1,2,0.5,1.5,100,0]]}}'
            mock_open.return_value.__enter__.return_value = mock_response
            
            from pathlib import Path
            res = fetch_chunk("NSE_EQ|INE123", "TESTSYM", "2026-07-01", "2026-07-31", "tok", Path(td))
            
            assert res["status"] == "SUCCESS"
            
            # Verify URL called
            args, kwargs = mock_open.call_args
            req = args[0]
            assert "/v3/historical-candle/NSE_EQ%7CINE123/minutes/5/2026-07-31/2026-07-01" in req.full_url
            assert req.headers["Api-version"] == "3.0"
            assert "tok" in req.headers["Authorization"]

def test_monthly_chunk_boundaries():
    chunks = get_monthly_chunks("2026-01-15", "2026-03-05")
    assert chunks[0] == ("2026-01-15", "2026-01-31")
    assert chunks[1] == ("2026-02-01", "2026-02-28")
    assert chunks[2] == ("2026-03-01", "2026-03-05")

def test_429_retry_and_5xx():
    with tempfile.TemporaryDirectory() as td:
        with patch("urllib.request.urlopen") as mock_open:
            import urllib.error
            # First fail with 429, then 502, then succeed
            err_429 = urllib.error.HTTPError(url="", code=429, msg="Rate", hdrs={}, fp=None)
            err_502 = urllib.error.HTTPError(url="", code=502, msg="Bad Gateway", hdrs={}, fp=None)
            
            succ = MagicMock()
            succ.status = 200
            succ.read.return_value = b'{"status":"success","data":{"candles":[]}}'
            succ_ctx = MagicMock()
            succ_ctx.__enter__.return_value = succ
            
            mock_open.side_effect = [err_429, err_502, succ_ctx]
            
            with patch("time.sleep") as mock_sleep:
                from pathlib import Path
                res = fetch_chunk("KEY", "SYM", "2026-01-01", "2026-01-31", "tok", Path(td))
                assert res["status"] == "SUCCESS"
                assert mock_sleep.call_count == 2

def test_401_403_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        with patch("urllib.request.urlopen") as mock_open:
            import urllib.error
            err_401 = urllib.error.HTTPError(url="", code=401, msg="Unauth", hdrs={}, fp=None)
            mock_open.side_effect = err_401
            
            from pathlib import Path
            res = fetch_chunk("KEY", "SYM", "2026-01-01", "2026-01-31", "tok", Path(td))
            assert res["status"] == "FAILED"
            assert res["http_status"] == 401

def test_stored_file_checksum():
    with tempfile.TemporaryDirectory() as td:
        with patch("urllib.request.urlopen") as mock_open:
            succ = MagicMock()
            succ.status = 200
            succ.read.return_value = b'{"status":"success","data":{"candles":[]}}'
            mock_open.return_value.__enter__.return_value = succ
            
            from pathlib import Path
            res = fetch_chunk("KEY", "SYM", "2026-01-01", "2026-01-31", "tok", Path(td))
            assert res["status"] == "SUCCESS"
            assert res["file_sha256"] is not None
            
            # Verify file exists
            assert (Path(td) / "SYM_2026-01-01_2026-01-31.json.gz.sha256").exists()
