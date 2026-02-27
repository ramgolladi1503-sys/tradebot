from strategies.trade_builder import TradeBuilder
from config import config as cfg


def _market_data_empty_chain(chain_source="empty"):
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
        "chain_source": chain_source,
    }


def test_no_trade_when_live_chain_missing():
    cfg.EXECUTION_MODE = "LIVE"
    tb = TradeBuilder()
    md = _market_data_empty_chain(chain_source="empty")
    md["market_open"] = True
    trade = tb.build(md, quick_mode=True)
    assert trade is None


def test_analysis_only_synthetic_marks_not_tradable():
    cfg.EXECUTION_MODE = "LIVE"
    tb = TradeBuilder()
    md = _market_data_empty_chain(chain_source="synthetic")
    md["market_open"] = True
    trade = tb.build(md, quick_mode=True)
    assert trade is None
