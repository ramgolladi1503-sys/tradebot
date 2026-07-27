import pandas as pd
import json
import logging
from zoneinfo import ZoneInfo
from datetime import datetime
from .schemas import ensure_schema
from .validation import validate_ohlc, validate_post_expiry

logger = logging.getLogger(__name__)

KOLKATA = ZoneInfo("Asia/Kolkata")
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
