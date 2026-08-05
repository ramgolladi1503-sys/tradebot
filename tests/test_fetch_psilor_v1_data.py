import pytest
from datetime import datetime
import json
import urllib.parse
from unittest.mock import patch, mock_open, MagicMock
from scripts.fetch_psilor_v1_data import UpstoxFetcher, UpstoxDataError

@pytest.fixture
def mock_fetcher():
    start = datetime(2026, 1, 1)
    end = datetime(2026, 6, 30)
    with patch("os.environ.get", return_value="test_token"):
        fetcher = UpstoxFetcher(start, end)
        return fetcher

def test_missing_constituent_manifest_fails_closed(mock_fetcher):
    with patch("pathlib.Path.exists", return_value=False):
        mock_fetcher.fetch_constituents()
        assert "MISSING_POINT_IN_TIME_NIFTY_CONSTITUENT_MANIFEST" in mock_fetcher.blockers
        assert mock_fetcher.metrics["CONSTITUENT_MEMBERSHIP_AUTHORITY"] == "FAIL"

def test_duplicate_candle_timestamp_fails(mock_fetcher):
    candles = [
        ["2026-07-01T09:15:00+05:30", "100", "105", "95", "102", "1000", "0"],
        ["2026-07-01T09:15:00+05:30", "102", "106", "101", "104", "1500", "0"] # Mismatch
    ]
    with pytest.raises(UpstoxDataError, match="Duplicate candle conflict"):
        mock_fetcher.validate_candles(candles, "NSE_INDEX|Nifty 50")

def test_duplicate_candle_timestamp_exact_dedup(mock_fetcher):
    candles = [
        ["2026-07-01T09:15:00+05:30", "100", "105", "95", "102", "1000", "0"],
        ["2026-07-01T09:15:00+05:30", "100", "105", "95", "102", "1000", "0"] # Exact match
    ]
    records, first, last = mock_fetcher.validate_candles(candles, "NSE_INDEX|Nifty 50")
    assert len(records) == 1 # Deduplicated safely

def test_ohlcv_bounds_validation(mock_fetcher):
    # High < Low
    candles = [
        ["2026-07-01T09:15:00+05:30", "100", "90", "95", "102", "1000", "0"]
    ]
    with pytest.raises(UpstoxDataError, match="OHLCV bounds violation"):
        mock_fetcher.validate_candles(candles, "NSE_INDEX|Nifty 50")

def test_udapi1149_blocks_execution(mock_fetcher):
    error_resp_bytes = json.dumps({"errors": [{"errorCode": "UDAPI1149"}]}).encode()
    
    mock_err = urllib.error.HTTPError(
        "http://test", 403, "Forbidden", {}, None
    )
    mock_err.read = MagicMock(return_value=error_resp_bytes)
    
    with patch("urllib.request.urlopen", side_effect=mock_err):
        status, data, raw, m_entry = mock_fetcher._make_request("/v2/expired-instruments/expiries")
        assert "BLOCKED_UPSTOX_PLUS_REQUIRED" in mock_fetcher.blockers
        assert m_entry["success_blocker_verdict"] == "BLOCKED_UPSTOX_PLUS_REQUIRED"

def test_verdict_data_ready_psilor(mock_fetcher):
    mock_fetcher.metrics["NIFTY_INDEX_SESSIONS"] = set([str(i) for i in range(40)])
    mock_fetcher.metrics["VIX_OVERLAP_SESSIONS"] = set([str(i) for i in range(40)])
    mock_fetcher.metrics["EXPIRED_FUTURES_OVERLAP_SESSIONS"] = set([str(i) for i in range(40)])
    mock_fetcher.metrics["EXPIRED_OPTION_OVERLAP_SESSIONS"] = set([str(i) for i in range(40)])
    mock_fetcher.metrics["CONSTITUENT_SESSIONS"] = set([str(i) for i in range(40)])
    
    mock_fetcher.metrics["EXPIRED_CANDLE_FETCH"] = "PASS"
    mock_fetcher.metrics["BOTH_CE_AND_PE"] = "PASS"
    
    mock_fetcher.compute_verdict()
    assert mock_fetcher.metrics["DATA_ADMISSION_VERDICT"] == "DATA_READY_FOR_PSILOR_PROXY_VALIDATION"

def test_verdict_dorl_only(mock_fetcher):
    mock_fetcher.metrics["NIFTY_INDEX_SESSIONS"] = set([str(i) for i in range(40)])
    mock_fetcher.metrics["VIX_OVERLAP_SESSIONS"] = set([str(i) for i in range(40)])
    mock_fetcher.metrics["EXPIRED_FUTURES_OVERLAP_SESSIONS"] = set([str(i) for i in range(40)])
    mock_fetcher.metrics["EXPIRED_OPTION_OVERLAP_SESSIONS"] = set([str(i) for i in range(40)])
    
    mock_fetcher.metrics["EXPIRED_CANDLE_FETCH"] = "PASS"
    mock_fetcher.metrics["BOTH_CE_AND_PE"] = "PASS"
    
    mock_fetcher.blockers.add("MISSING_POINT_IN_TIME_NIFTY_CONSTITUENT_MANIFEST")
    
    mock_fetcher.compute_verdict()
    assert mock_fetcher.metrics["DATA_ADMISSION_VERDICT"] == "DATA_READY_FOR_DORL_ONLY"
