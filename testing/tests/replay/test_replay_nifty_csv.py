import pandas as pd
from pathlib import Path

from core.feature_builder import add_indicators
from core.option_chain import fetch_option_chain
from strategies.trade_builder import TradeBuilder


def _build_market_data(row, symbol="NIFTY"):
    ltp = float(row["close"])
    vwap = float(row.get("vwap", ltp))
    atr = float(row.get("atr_14", max(1.0, ltp * 0.002)))
    option_chain = fetch_option_chain(symbol, ltp, force_synthetic=True)
    return {
        "symbol": symbol,
        "ltp": ltp,
        "vwap": vwap,
        "atr": atr,
        "volume": float(row.get("volume", 0)),
        "ltp_change_5m": float(row.get("return_1", 0)),
        "ltp_change_10m": float(row.get("return_1", 0)),
        "option_chain": option_chain,
        "timestamp": row.get("datetime"),
    }


def test_replay_nifty_csv_no_crash():
    path = Path("data/NIFTY_20260123.csv")
    assert path.exists(), "Missing NIFTY replay data"

    df = pd.read_csv(path)
    df = add_indicators(df).dropna().reset_index(drop=True)

    tb = TradeBuilder()
    trades = []
    for _, row in df.iterrows():
        md = _build_market_data(row, symbol="NIFTY")
        trade = tb.build(md, quick_mode=True)
        if trade:
            trades.append(trade)

    # The replay should not crash and should be deterministic per run.
    assert isinstance(trades, list)


def test_replay_nifty_deterministic_trade_count():
    path = Path("data/NIFTY_20260123.csv")
    df = pd.read_csv(path)
    df = add_indicators(df).dropna().reset_index(drop=True)

    tb = TradeBuilder()
    def run():
        count = 0
        for _, row in df.iterrows():
            md = _build_market_data(row, symbol="NIFTY")
            if tb.build(md, quick_mode=True):
                count += 1
        return count

    c1 = run()
    c2 = run()
    assert c1 == c2
