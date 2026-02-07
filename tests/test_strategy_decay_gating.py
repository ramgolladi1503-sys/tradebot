from config import config as cfg
from core.strategy_tracker import StrategyTracker
from strategies.trade_builder import TradeBuilder


class StubPredictor:
    model_version = "test"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.9

    def predict_confidence_shadow(self, _feats):
        return 0.8


def _market_data():
    return {
        "symbol": "NIFTY",
        "ltp": 100.0,
        "vwap": 99.0,
        "vwap_slope": 0.01,
        "atr": 1.0,
        "rsi_mom": 0.0,
        "vol_z": 1.0,
        "ltp_change": 1.0,
        "ltp_change_window": 1.0,
        "regime_probs": {"TREND": 0.9},
        "regime_entropy": 0.1,
        "unstable_regime_flag": False,
        "instrument": "OPT",
        "quote_ok": True,
        "chain_source": "live",
        "day_type": "RANGE_DAY",
        "regime": "TREND",
        "option_chain": [
            {
                "type": "CE",
                "strike": 100,
                "bid": 10.0,
                "ask": 11.0,
                "ltp": 10.5,
                "volume": 2000,
                "oi": 5000,
                "oi_change": 200,
                "quote_ok": True,
                "expiry": "2026-02-27",
            }
        ],
    }


def test_quarantined_strategy_blocks_trade():
    tracker = StrategyTracker()
    tracker.degraded["ENSEMBLE_OPT"] = {"reason": "decay_probability", "value": 0.9}
    tb = TradeBuilder(predictor=StubPredictor(), strategy_tracker=tracker)
    trade = tb.build(_market_data(), quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is None
    assert tb._reject_ctx.get("reason") == "strategy_quarantined"


def test_decaying_strategy_downsizes():
    tracker = StrategyTracker()
    tracker.apply_decay_probs({"ENSEMBLE_OPT": float(getattr(cfg, "DECAY_SOFT_THRESHOLD", 0.5)) + 0.05})
    tb = TradeBuilder(predictor=StubPredictor(), strategy_tracker=tracker)
    trade = tb.build(_market_data(), quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert trade.size_mult <= float(getattr(cfg, "DECAY_DOWNSIZE_MULT", 0.6))
