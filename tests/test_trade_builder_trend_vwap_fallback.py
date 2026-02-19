from config import config as cfg
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.9


def _base_market_data(vwap_slope: float):
    return {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "primary_regime": "TREND",
        "regime": "TREND",
        "indicators_ok": True,
        "vwap_slope": vwap_slope,
        "orb_bias": "PENDING",
        "orb_lock_min": 15,
        "minutes_since_open": 5,
        "ltp": 25000.0,
        "vwap": 24995.0,
        "atr": 25.0,
    }


def _patch_primary_signal_paths_to_none(monkeypatch):
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None)


def test_trend_vwap_fallback_negative_slope_emits_buy_put(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TREND_VWAP_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "TREND_VWAP_FALLBACK_SCORE", 0.60, raising=False)
    monkeypatch.setattr(cfg, "TREND_VWAP_FALLBACK_SLOPE_ABS_MIN", 0.0008, raising=False)
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(tmp_path / "logs" / "desks" / "DEFAULT"), raising=False)
    _patch_primary_signal_paths_to_none(monkeypatch)

    builder = TradeBuilder(predictor=_PredictorStub())
    sig = builder._signal_for_symbol(_base_market_data(vwap_slope=-0.002))

    assert sig is not None
    assert sig["reason"] == "trend_vwap_fallback"
    assert sig["score"] == 0.60
    assert sig["direction"] == "BUY_PUT"


def test_trend_vwap_fallback_positive_slope_emits_buy_call(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TREND_VWAP_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "TREND_VWAP_FALLBACK_SCORE", 0.60, raising=False)
    monkeypatch.setattr(cfg, "TREND_VWAP_FALLBACK_SLOPE_ABS_MIN", 0.0008, raising=False)
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(tmp_path / "logs" / "desks" / "DEFAULT"), raising=False)
    _patch_primary_signal_paths_to_none(monkeypatch)

    builder = TradeBuilder(predictor=_PredictorStub())
    sig = builder._signal_for_symbol(_base_market_data(vwap_slope=0.002))

    assert sig is not None
    assert sig["reason"] == "trend_vwap_fallback"
    assert sig["score"] == 0.60
    assert sig["direction"] == "BUY_CALL"
