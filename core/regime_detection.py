import pandas as pd

def detect_regime(df):
    """
    Simple regime detection:
    - TRENDING: price above SMA 50
    - RANGING: price within Bollinger Bands
    - VOLATILE: ATR high
    """
    df["SMA_50"] = df["Close"].rolling(50).mean()
    df["ATR"] = df["High"] - df["Low"]

    latest = df.iloc[-1]
    if latest["Close"] > latest["SMA_50"]:
        return "TRENDING"
    elif latest["ATR"] > df["ATR"].rolling(20).mean().iloc[-1]*1.5:
        return "VOLATILE"
    else:
        return "RANGING"

