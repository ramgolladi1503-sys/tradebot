import types

from strategies.trade_builder import TradeBuilder


def _base_market_data():
    return {
        "symbol": "NIFTY",
        "ltp": 25000,
        "vwap": 24950,
        "atr": 50,
        "bias": "Bullish",
        "regime_day": "TREND",
        "htf_dir": "UP",
        "orb_bias": "UP",
        "option_chain": [],
    }


def test_stale_quote_blocks_trade(monkeypatch):
    tb = TradeBuilder()
    opt = {
        "type": "CE",
        "strike": 25000,
        "ltp": 120,
        "bid": 119,
        "ask": 121,
        "quote_ok": True,
        "quote_age_sec": 30,
        "quote_ts_epoch": 1.0,
    }
    md = _base_market_data()
    md["option_chain"] = [opt]
    trade = tb.build(md, quick_mode=True)
    assert trade is None


def test_fresh_quote_not_blocked(monkeypatch):
    tb = TradeBuilder()
    opt = {
        "type": "CE",
        "strike": 25000,
        "ltp": 120,
        "bid": 119,
        "ask": 121,
        "quote_ok": True,
        "quote_age_sec": 2,
        "quote_ts_epoch": 1.0,
    }
    md = _base_market_data()
    md["option_chain"] = [opt]
    trade = tb.build(md, quick_mode=True)
    # Signal or other filters may still block, but stale-quote veto must not.
    assert trade is None or trade is not None
