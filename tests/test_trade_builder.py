from strategies.trade_builder import TradeBuilder

def test_trade_builder_returns_borderline_candidate_when_no_signal():
    tb = TradeBuilder()
    md = {
        "symbol": "NIFTY",
        "ltp": 25010.0,
        "vwap": 25010.0,
        "atr": 0.0,
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25000CE",
                "instrument_token": 123456,
                "ltp": 102.0,
                "bid": 101.5,
                "ask": 102.5,
            }
        ],
    }
    out = tb.build(md)
    assert out is not None
    assert out.get("candidate_status") == "near_executable"
    assert out.get("execution_status") == "scored"
