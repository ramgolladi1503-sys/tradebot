import os
from pathlib import Path

# Package paths
PKG_DIR = Path("research/upstox_expired_options")
TEST_DIR = Path("tests/upstox_expired_options")
PKG_DIR.mkdir(parents=True, exist_ok=True)
TEST_DIR.mkdir(parents=True, exist_ok=True)

files = {}

files[PKG_DIR / "__init__.py"] = ""

files[PKG_DIR / "schemas.py"] = """
import pandas as pd
from typing import List, Dict

REQUIRED_CANDLE_COLUMNS = [
    "timestamp", "session_date", "underlying", "underlying_key", "expiry", 
    "strike", "option_type", "trading_symbol", "expired_instrument_key", 
    "exchange_token", "open", "high", "low", "close", "volume", 
    "open_interest", "lot_size", "minimum_lot", "weekly", "source", 
    "interval", "fetched_at", "request_from_date", "request_to_date", 
    "raw_response_sha256", "normalizer_version"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED_CANDLE_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing schema columns: {missing}")
    return df[REQUIRED_CANDLE_COLUMNS].copy()
"""

files[PKG_DIR / "validation.py"] = """
import pandas as pd
import pytz
from datetime import datetime

KOLKATA = pytz.timezone("Asia/Kolkata")

def validate_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    invalid = (df['high'] < df[['open', 'close', 'low']].max(axis=1)) | (df['low'] > df[['open', 'close', 'high']].min(axis=1))
    return df[~invalid].copy(), df[invalid].copy()

def validate_post_expiry(df: pd.DataFrame, expiry_date: str) -> pd.DataFrame:
    exp_d = datetime.strptime(expiry_date, "%Y-%m-%d").date()
    # allow until 15:30 on expiry
    exp_dt = KOLKATA.localize(datetime(exp_d.year, exp_d.month, exp_d.day, 15, 30))
    post = df['timestamp'] > exp_dt
    return df[~post].copy(), df[post].copy()
"""

files[PKG_DIR / "normalizer.py"] = """
import pandas as pd
import json
import pytz
from datetime import datetime
from .schemas import ensure_schema
from .validation import validate_ohlc, validate_post_expiry

KOLKATA = pytz.timezone("Asia/Kolkata")
NORMALIZER_VERSION = "1.0.0"

def parse_candles(raw_json: bytes, meta: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = json.loads(raw_json)
    candles = data.get("data", {}).get("candles", [])
    if not candles:
        return pd.DataFrame(), pd.DataFrame()
        
    df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume", "open_interest"])
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert(KOLKATA)
    df['session_date'] = df['timestamp'].dt.date.astype(str)
    
    # Sort and remove duplicate timestamps
    df = df.sort_values('timestamp')
    dupes = df.duplicated(subset=['timestamp'], keep='first')
    quarantined = df[dupes].copy()
    df = df[~dupes].copy()
    
    df, ohlc_q = validate_ohlc(df)
    quarantined = pd.concat([quarantined, ohlc_q])
    
    df, exp_q = validate_post_expiry(df, meta['expiry'])
    quarantined = pd.concat([quarantined, exp_q])
    
    for k, v in meta.items():
        df[k] = v
    
    df['normalizer_version'] = NORMALIZER_VERSION
    df = ensure_schema(df)
    return df, quarantined
"""

files[PKG_DIR / "aggregation.py"] = """
import pandas as pd

def aggregate_5m(df_1m: pd.DataFrame) -> pd.DataFrame:
    if df_1m.empty:
        return pd.DataFrame()
        
    df = df_1m.set_index('timestamp').copy()
    df['open_interest'] = df['open_interest'].replace(0, pd.NA).ffill().fillna(0)
    
    # Ensure timezone is kept correctly
    # resample by 5m, grouped by session date so we don't bridge sessions
    # actually resample directly works if we dropnas later, but session grouping is safer
    
    def agg_group(g):
        res = g.resample('5min', origin='start_day').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'open_interest': 'last'
        })
        res['source_bar_count'] = g['open'].resample('5min', origin='start_day').count()
        return res.dropna(subset=['open'])
        
    agg = df.groupby('session_date').apply(agg_group).reset_index(level=0, drop=True)
    agg['is_complete_5m_bar'] = agg['source_bar_count'] == 5
    
    # Copy metadata from first row of 1m
    meta_cols = [c for c in df_1m.columns if c not in ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'open_interest']]
    meta_vals = df_1m.iloc[0][meta_cols].to_dict()
    for k, v in meta_vals.items():
        if k != 'interval':
            agg[k] = v
    agg['interval'] = '5minute'
    
    return agg.reset_index()
"""

files[PKG_DIR / "storage.py"] = """
import os
import shutil
from pathlib import Path
import pandas as pd

def atomic_write_parquet(df: pd.DataFrame, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(".tmp")
    df.to_parquet(tmp_path, index=False)
    # atomic rename
    os.rename(tmp_path, out_path)
"""

files[PKG_DIR / "client.py"] = """
import urllib.request
import urllib.error
import urllib.parse
import json
import time

class UpstoxAPIError(Exception):
    def __init__(self, code, reason):
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")

class UpstoxClient:
    def __init__(self, token):
        self.token = token
        
    def get(self, url, max_retries=3):
        if not self.token:
            raise UpstoxAPIError("MISSING_TOKEN", "AUTHENTICATION_ROTATION_REQUIRED")
            
        headers = {
            "Accept": "application/json",
            "Api-Version": "3.0",
            "Authorization": f"Bearer {self.token}",
            "User-Agent": "curl/8.4.0"
        }
        req = urllib.request.Request(url, headers=headers)
        attempt = 0
        while attempt < max_retries:
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.read()
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    raise UpstoxAPIError("AUTHENTICATION_FAILED", "401")
                elif e.code == 403:
                    body = e.read()
                    try:
                        j = json.loads(body)
                        if any(err.get('errorCode') == 'UDAPI1149' for err in j.get('errors', [])):
                            raise UpstoxAPIError("PLUS_ENTITLEMENT_FAILED", "UDAPI1149")
                    except Exception:
                        pass
                    raise UpstoxAPIError("FORBIDDEN", "403")
                elif e.code == 429:
                    r = int(e.headers.get("Retry-After", 2 ** attempt))
                    time.sleep(r)
                    attempt += 1
                elif e.code in (500, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    attempt += 1
                else:
                    raise UpstoxAPIError("HTTP_ERROR", str(e.code))
            except Exception as e:
                time.sleep(2 ** attempt)
                attempt += 1
                
        raise UpstoxAPIError("MAX_RETRIES", "Retries exceeded")
"""

files[TEST_DIR / "test_client.py"] = """
import pytest
from research.upstox_expired_options.client import UpstoxClient, UpstoxAPIError

def test_missing_token():
    client = UpstoxClient("")
    with pytest.raises(UpstoxAPIError) as exc:
        client.get("http://example.com")
    assert exc.value.code == "MISSING_TOKEN"
"""

files[TEST_DIR / "test_aggregation.py"] = """
import pandas as pd
import pytz
from datetime import datetime
from research.upstox_expired_options.aggregation import aggregate_5m

KOLKATA = pytz.timezone("Asia/Kolkata")

def test_aggregate_5m():
    # 3 bars in first 5 min, 1 bar in next
    dt1 = KOLKATA.localize(datetime(2026, 7, 7, 9, 15))
    dt2 = KOLKATA.localize(datetime(2026, 7, 7, 9, 16))
    dt3 = KOLKATA.localize(datetime(2026, 7, 7, 9, 17))
    dt4 = KOLKATA.localize(datetime(2026, 7, 7, 9, 21))
    
    df = pd.DataFrame([
        {'timestamp': dt1, 'session_date': '2026-07-07', 'open': 10, 'high': 15, 'low': 9, 'close': 14, 'volume': 100, 'open_interest': 50},
        {'timestamp': dt2, 'session_date': '2026-07-07', 'open': 14, 'high': 16, 'low': 13, 'close': 16, 'volume': 150, 'open_interest': 60},
        {'timestamp': dt3, 'session_date': '2026-07-07', 'open': 16, 'high': 20, 'low': 15, 'close': 19, 'volume': 200, 'open_interest': 70},
        {'timestamp': dt4, 'session_date': '2026-07-07', 'open': 19, 'high': 21, 'low': 18, 'close': 20, 'volume': 300, 'open_interest': 80}
    ])
    df['interval'] = '1minute'
    
    agg = aggregate_5m(df)
    assert len(agg) == 2
    assert agg.iloc[0]['open'] == 10
    assert agg.iloc[0]['high'] == 20
    assert agg.iloc[0]['low'] == 9
    assert agg.iloc[0]['close'] == 19
    assert agg.iloc[0]['volume'] == 450
    assert agg.iloc[0]['source_bar_count'] == 3
    assert not agg.iloc[0]['is_complete_5m_bar']
    
    assert agg.iloc[1]['open'] == 19
    assert agg.iloc[1]['source_bar_count'] == 1
"""

files[Path("pytest.ini")] = """
[pytest]
pythonpath = .
"""

for p, content in files.items():
    with open(p, "w") as f:
        f.write(content.strip() + "\\n")
print("Package structure written successfully.")
