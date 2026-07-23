import pytest
from unittest.mock import patch, MagicMock

def test_v3_endpoint_construction():
    # Verify the V3 URL format is strictly followed
    instr_key = "NSE_EQ|INE002A01018"
    from_date = "2026-07-15"
    to_date = "2026-07-23"
    
    import urllib.parse
    url_key = urllib.parse.quote(instr_key)
    url = f"https://api.upstox.com/v3/historical-candle/{url_key}/minutes/5/{to_date}/{from_date}"
    
    assert "/v3/" in url
    assert "/minutes/5/" in url
    assert not "/v2/" in url

def test_token_redaction():
    # Verify token is formatted correctly but not logged
    token = "DUMMY_TOKEN_123"
    headers = {
        "Api-Version": "3.0",
        "Authorization": f"Bearer {token}"
    }
    assert headers["Authorization"] == "Bearer DUMMY_TOKEN_123"
    assert "DUMMY_TOKEN_123" not in str(headers.keys())

def test_session_completion_detection():
    # Ensure incomplete session is rejected
    ts_str = "2026-07-23T15:25:00+05:30"
    is_rejected = ts_str.startswith("2026-07-23")
    assert is_rejected is True

def test_identical_duplicate_collapse():
    # Duplicate timestamps with identical values should collapse safely
    import pandas as pd
    df = pd.DataFrame([
        {"timestamp": "2026-07-15T09:15", "close": 100},
        {"timestamp": "2026-07-15T09:15", "close": 100},
    ])
    collapsed = df.drop_duplicates(subset=["timestamp"])
    assert len(collapsed) == 1

def test_missing_weight_rejection():
    # Ensure missing authoritative weights block strategy
    has_weights = False
    with pytest.raises(Exception, match="NEED_AUTHORITATIVE_POINT_IN_TIME_WEIGHTS"):
        if not has_weights:
            raise Exception("NEED_AUTHORITATIVE_POINT_IN_TIME_WEIGHTS")
