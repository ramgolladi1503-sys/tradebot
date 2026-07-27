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
