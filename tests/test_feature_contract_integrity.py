from __future__ import annotations

from core.feature_contract import FeatureContract
from strategies.trade_builder import TradeBuilder


class StubPredictor:
    model_version = "test-model"
    shadow_version = None

    def __init__(self, required_features):
        self._contract = FeatureContract(required_features=list(required_features))

    def get_feature_contract(self):
        return self._contract

    def predict_confidence(self, _features):
        return 0.9

    def predict_confidence_shadow(self, _features):
        return None


def _market_data():
    return {
        "symbol": "NIFTY",
        "ltp": 25000.0,
        "vwap": 24950.0,
        "vwap_slope": 0.1,
        "atr": 50.0,
        "htf_dir": "UP",
        "rsi_mom": 0.2,
        "vol_z": 0.2,
        "ltp_change": 10.0,
        "ltp_change_window": 15.0,
        "ltp_change_5m": 5.0,
        "regime_probs": {"TREND": 0.9},
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
                "strike": 25000,
                "bid": 99.5,
                "ask": 100.5,
                "ltp": 100.0,
                "volume": 70000,
                "oi": 5000,
                "oi_change": 500,
                "quote_ok": True,
                "quote_age_sec": 1.0,
                "quote_ts_epoch": 1.0,
                "depth_ok": True,
                "expiry": "2026-02-27",
                "oi_build": "LONG",
                "iv_z": 0.0,
                "iv": 0.2,
            }
        ],
    }


def _relax_thresholds(monkeypatch):
    monkeypatch.setattr("config.config.STRICT_STRATEGY_SCORE", 0.1, raising=False)
    monkeypatch.setattr("config.config.ML_USE_ONLY_WITH_HISTORY", False, raising=False)
    monkeypatch.setattr("config.config.ML_MIN_PROBA", 0.1, raising=False)
    monkeypatch.setattr("config.config.TRADE_SCORE_MIN", 1, raising=False)
    monkeypatch.setattr("config.config.MAX_SPREAD_PCT", 0.2, raising=False)


def test_missing_required_feature_blocks_trading(monkeypatch):
    _relax_thresholds(monkeypatch)
    monkeypatch.setattr(
        "strategies.trade_builder.build_trade_features",
        lambda _md, _opt: {"feat_a": 1.0},
    )
    tb = TradeBuilder(predictor=StubPredictor(required_features=["feat_a", "feat_b"]))
    trade = tb.build(_market_data(), quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert trade.tradable is False
    assert any(str(reason).startswith("MODEL_FEATURE_MISMATCH:") for reason in trade.tradable_reasons_blocking)
    assert str(tb._reject_ctx.get("reason", "")).startswith("MODEL_FEATURE_MISMATCH:")


def test_nan_required_feature_blocks_trading(monkeypatch):
    _relax_thresholds(monkeypatch)
    monkeypatch.setattr(
        "strategies.trade_builder.build_trade_features",
        lambda _md, _opt: {"feat_a": 1.0, "feat_b": float("nan")},
    )
    tb = TradeBuilder(predictor=StubPredictor(required_features=["feat_a", "feat_b"]))
    trade = tb.build(_market_data(), quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert trade.tradable is False
    assert any(str(reason).startswith("FEATURE_NAN_PRESENT:") for reason in trade.tradable_reasons_blocking)
    assert str(tb._reject_ctx.get("reason", "")).startswith("FEATURE_NAN_PRESENT:")
