# core/filters.py

from datetime import time as dtime

def allowed_time(now):
    return (
        dtime(9, 30) <= now <= dtime(11, 30) or
        dtime(13, 15) <= now <= dtime(14, 30)
    )

def get_bias(ltp, vwap):
    if abs(ltp - vwap) < 15:
        return "NEUTRAL"
    return "BULLISH" if ltp > vwap else "BEARISH"

def filter_by_premium(options_df, ltp_map, bias):
    valid = []

    for _, row in options_df.iterrows():
        symbol = f"NFO:{row['tradingsymbol']}"
        if symbol not in ltp_map:
            continue

        premium = ltp_map[symbol]["last_price"]

        if premium < 40 or premium > 120:
            continue

        if bias == "BULLISH" and row["instrument_type"] != "CE":
            continue

        if bias == "BEARISH" and row["instrument_type"] != "PE":
            continue

        valid.append((row, premium))

    return valid

