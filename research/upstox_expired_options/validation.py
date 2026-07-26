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
    return df[~post].copy(), df[post].copy()\n