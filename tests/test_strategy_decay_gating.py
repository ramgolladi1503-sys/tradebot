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
        "htf_dir": "UP",
        "rsi_mom": 0.0,
        "vol_z": 0.2,
        "ltp_change": 1.0,
        "ltp_change_window": 1.0,
        "regime_probs": {"TREND": 0.9},
        "trade_score": 80,
        "oi_build": "LONG",
        "regime_entropy": 0.1,
        "unstable_regime_flag": False,
        "instrument": "OPT",
        "quote_ok": True,
        "quote_age_sec": 1.0,
        "ltp_source": "live",
        "chain_source": "live",
        "day_type": "TREND_DAY",
        "regime": "TREND",
        "orb_bias": "UP",
        "option_chain": [
            {
                "type": "CE",
                "strike": 100,
                "bid": 49.7,
                "ask": 50.3,
                "ltp": 50.0,
                "volume": 60000,
                "oi": 5000,
                "oi_change": 400,
                "quote_ok": True,
                "quote_age_sec": 1.0,
                "depth_ok": True,
                "expiry": "2026-02-27",
                "oi_build": "LONG",
                "iv_z": -0.6,
                "iv": 0.2,
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


def test_decaying_strategy_downsizes(monkeypatch):
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.5, raising=False)
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 50, raising=False)
    monkeypatch.setattr(cfg, "ML_USE_ONLY_WITH_HISTORY", False, raising=False)
    tracker = StrategyTracker()
    tracker.apply_decay_probs({"ENSEMBLE_OPT": float(getattr(cfg, "DECAY_SOFT_THRESHOLD", 0.5)) + 0.05})
    tb = TradeBuilder(predictor=StubPredictor(), strategy_tracker=tracker)
    allowed, new_score, new_mult, reason = tb._apply_decay_gate("ENSEMBLE_OPT", base_score=1.0, size_mult=1.0)
    assert allowed is True
    assert reason == "strategy_decaying"
    assert new_score is not None
    assert new_score <= float(getattr(cfg, "DECAY_DOWNSIZE_MULT", 0.6))
    assert new_mult <= float(getattr(cfg, "DECAY_DOWNSIZE_MULT", 0.6))
