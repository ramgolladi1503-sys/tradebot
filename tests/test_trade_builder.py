from strategies.trade_builder import TradeBuilder

def test_trade_builder_returns_none_when_no_signal():
    tb = TradeBuilder()
    md = {"symbol": "NIFTY", "ltp": 100, "vwap": 100, "atr": 0.0, "option_chain": []}
    assert tb.build(md) is None
