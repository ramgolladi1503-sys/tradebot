from __future__ import annotations

from config import config as cfg
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.9


def _patch_builder(monkeypatch, builder):
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda _md, force_family=None: {
            "direction": "BUY_CALL",
            "reason": "unit_test_signal",
            "score": 0.9,
            "regime_day": "TREND",
        },
        raising=True,
    )
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"), raising=True)
    monkeypatch.setattr(builder, "_apply_decay_gate", lambda *_args, **_kwargs: (True, None, 1.0, None), raising=True)
    monkeypatch.setattr(builder, "_validate_ml_features", lambda _feats: (True, "ok"), raising=True)
    monkeypatch.setattr(trade_builder_module, "compute_trade_score", lambda *args, **kwargs: {"score": 95.0, "alignment": 1.0})
    monkeypatch.setattr(cfg, "ALPHA_ENSEMBLE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_AB_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_USE_ONLY_WITH_HISTORY", False, raising=False)
    monkeypatch.setattr(cfg, "ML_MIN_PROBA", 0.1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 1.0, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)
    monkeypatch.setattr(cfg, "MIN_RR", 0.1, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(builder.execution, "estimate_slippage", lambda *args, **kwargs: 0.0, raising=True)
    monkeypatch.setattr(
        builder,
        "_resolve_option_contract",
        lambda symbol, strike, opt_type, expiry, market_data=None: {
            "expiry": expiry or "2026-03-05",
            "tradingsymbol": "SENSEX2630582000CE",
            "instrument_token": 556677,
        },
        raising=True,
    )


def _market_data() -> dict:
    return {
        "symbol": "SENSEX",
        "market_open": True,
        "valid": True,
        "ltp": 82000.0,
        "vwap": 81980.0,
        "bias": "Bullish",
        "instrument": "OPT",
        "chain_source": "live",
        "quote_ok": True,
        "regime": "TREND",
        "regime_day": "TREND",
        "day_type": "TREND_DAY",
        "option_chain": [
            {
                "type": "CE",
                "strike": 82000.0,
                "expiry": "2026-03-05",
                "tradingsymbol": "SENSEX2630582000CE",
                "instrument_token": 556677,
                "ltp": 150.0,
                "last_price": 150.0,
                "bid": 100.0,
                "ask": 102.0,
                "best_bid": 100.0,
                "best_ask": 102.0,
                "mid_price": 101.0,
                "mark_price": 101.0,
                "price_source": "mid",
                "quote_ok": True,
                "quote_live": True,
                "quote_age_sec": 1.0,
                "quote_ts_epoch": 1771400000.0,
                "depth_ok": True,
                "volume": 5000,
                "oi": 20000,
                "oi_change": 1000,
                "iv": 0.2,
                "iv_z": 0.0,
                "iv_skew": 0.0,
                "delta": 0.3,
                "moneyness": 0.0,
            }
        ],
    }


def test_trade_builder_uses_depth_proxy_and_sets_price_source(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)

    trade = builder.build(_market_data(), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    # BUY uses ask proxy from depth, not stale last_price.
    assert round(float(trade.entry_ref_price), 2) == 102.00
    assert round(float(trade.entry_price), 2) >= 102.00
    assert trade.price_source == "mid"
    assert round(float(trade.best_bid), 2) == 100.00
    assert round(float(trade.best_ask), 2) == 102.00
