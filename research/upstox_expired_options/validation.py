import pandas as pd
from zoneinfo import ZoneInfo
from datetime import datetime

KOLKATA = ZoneInfo("Asia/Kolkata")

def validate_ohlc(df: pd.DataFrame) -> pd.DataFrame:
    invalid = (df['high'] < df[['open', 'close', 'low']].max(axis=1)) | (df['low'] > df[['open', 'close', 'high']].min(axis=1))
    return df[~invalid].copy(), df[invalid].copy()

def validate_post_expiry(df: pd.DataFrame, expiry_date: str) -> pd.DataFrame:
    exp_d = datetime.strptime(expiry_date, "%Y-%m-%d").date()
    # allow until 15:30 on expiry
    exp_dt = datetime(exp_d.year, exp_d.month, exp_d.day, 15, 30, tzinfo=KOLKATA)
    post = df['timestamp'] > exp_dt
    return df[~post].copy(), df[post].copy()

def is_contract_complete(path_1m, path_5m):
    import os
    if not path_1m or not path_5m: return False
    return os.path.exists(path_1m) and os.path.exists(path_5m)
