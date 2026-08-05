import pytest
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import pytz
import json
import uuid
import math
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from scripts.fetch_psilor_v1_data import UpstoxFetcher, UpstoxDataError

IST_TZ = pytz.timezone('Asia/Kolkata')

@pytest.fixture
def fetcher():
    start = pd.to_datetime("2026-01-01").tz_localize(IST_TZ)
    end = pd.to_datetime("2026-06-30").tz_localize(IST_TZ)
    f = UpstoxFetcher(start, end)
    f.token = "fake-token"
    return f

def test_candle_schema_validation_rejects_nan(fetcher):
    bad_candles = [["2026-05-01T09:15:00+05:30", float('nan'), 100, 100, 100, 1000, 500]]
    with pytest.raises(UpstoxDataError, match="NaN value"):
        fetcher.validate_candles(bad_candles, "TEST")

def test_candle_schema_validation_rejects_inf(fetcher):
    bad_candles = [["2026-05-01T09:15:00+05:30", float('inf'), 100, 100, 100, 1000, 500]]
    with pytest.raises(UpstoxDataError, match="Inf value"):
        fetcher.validate_candles(bad_candles, "TEST")

def test_candle_schema_validation_rejects_negative_volume(fetcher):
    bad_candles = [["2026-05-01T09:15:00+05:30", 100, 100, 100, 100, -1000, 500]]
    with pytest.raises(UpstoxDataError, match="Negative volume/OI"):
        fetcher.validate_candles(bad_candles, "TEST")

def test_candle_schema_validation_accepts_zero_volume_oi(fetcher):
    good_candles = [["2026-05-01T09:15:00+05:30", 100, 100, 100, 100, 0, 0]]
    records, _, _ = fetcher.validate_candles(good_candles, "TEST")
    assert len(records) == 1
    assert records[0]["volume"] == 0
    assert records[0]["open_interest"] == 0

def test_candle_schema_validation_duplicate_conflict(fetcher):
    bad_candles = [
        ["2026-05-01T09:15:00+05:30", 100, 100, 100, 100, 100, 100],
        ["2026-05-01T09:15:00+05:30", 100, 105, 100, 100, 100, 100]
    ]
    with pytest.raises(UpstoxDataError, match="Duplicate candle conflict"):
        fetcher.validate_candles(bad_candles, "TEST")

def test_candle_schema_validation_duplicate_exact(fetcher):
    good_candles = [
        ["2026-05-01T09:15:00+05:30", 100, 100, 100, 100, 100, 100],
        ["2026-05-01T09:15:00+05:30", 100, 100, 100, 100, 100, 100]
    ]
    records, _, _ = fetcher.validate_candles(good_candles, "TEST")
    assert len(records) == 1

def test_error_mapping_403_plus(fetcher):
    err_body = '{"errors": [{"errorCode": "UDAPI1149"}]}'
    verdict = fetcher._map_http_error(403, err_body)
    assert verdict == "BLOCKED_UPSTOX_PLUS_REQUIRED"

def test_error_mapping_401(fetcher):
    verdict = fetcher._map_http_error(401, "")
    assert verdict == "BLOCKED_AUTHENTICATION"
