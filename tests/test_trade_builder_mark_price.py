from __future__ import annotations

from config import config as cfg
from core.option_liquidity_cache import clear_option_liquidity_cache, update_option_liquidity_cache
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


def _market_data(
    *,
    bid=100.0,
    ask=102.0,
    mark_price=101.0,
    ltp=150.0,
    signal_price=None,
) -> dict:
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
                "ltp": ltp,
                "last_price": ltp,
                "bid": bid,
                "ask": ask,
                "best_bid": bid,
                "best_ask": ask,
                "mid_price": 101.0,
                "mark_price": mark_price,
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
                "signal_price": signal_price,
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
    assert float(trade.volume) == 5000.0
    assert float(trade.current_volume) == 5000.0
    assert float(trade.oi) == 20000.0
    assert float(trade.oi_change) == 1000.0


def test_trade_builder_hydrates_option_liquidity_from_cache(monkeypatch):
    clear_option_liquidity_cache()
    try:
        monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
        monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
        monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
        builder = TradeBuilder(predictor=_PredictorStub())
        _patch_builder(monkeypatch, builder)
        update_option_liquidity_cache(
            [
                {
                    "symbol": "SENSEX",
                    "expiry": "2026-03-05",
                    "strike": 82000.0,
                    "type": "CE",
                    "instrument_token": 556677,
                    "volume": 7000,
                    "current_volume": 7000,
                    "oi": 28000,
                    "oi_change": 900,
                    "snapshot_ts_epoch": 1771400005.0,
                }
            ],
            source="unit_test_cache",
        )
        market_data = _market_data()
        market_data["option_chain"][0].pop("volume", None)
        market_data["option_chain"][0].pop("oi", None)
        market_data["option_chain"][0].pop("oi_change", None)

        trade = builder.build(market_data, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

        assert trade is not None
        assert float(trade.volume) == 7000.0
        assert float(trade.current_volume) == 7000.0
        assert float(trade.oi) == 28000.0
        assert float(trade.oi_change) == 900.0
    finally:
        clear_option_liquidity_cache()


def test_quick_option_trade_uses_executable_premium_for_entry_and_expected(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)

    trade = builder.build(_market_data(), quick_mode=True, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.strategy == "QUICK_OPT"
    assert round(float(trade.entry_price), 2) >= 102.00
    assert round(float(trade.expected_entry), 2) == round(float(trade.entry_price), 2)
    assert trade.entry_price_source == "ask"
    assert trade.expected_entry_source == "ask"


def test_quick_option_entry_price_prefers_ask_over_mark_and_ltp(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)

    trade = builder.build(
        _market_data(bid=229.85, ask=230.15, mark_price=230.0, ltp=229.9, signal_price=100.99),
        quick_mode=True,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    assert round(float(trade.entry_price), 2) == 230.15
    assert round(float(trade.expected_entry), 2) == 230.15
    assert trade.entry_price_source == "ask"
    assert trade.expected_entry_source == "ask"
    assert round(float(trade.signal_price), 2) == 100.99


def test_option_executable_price_falls_back_to_mark_price_when_ask_missing(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    price, source = builder._option_executable_price(
        {
            "ask": None,
            "best_ask": None,
            "mark_price": 230.0,
            "ltp": 229.9,
            "signal_price": 100.99,
        },
        side="BUY",
    )

    assert price == 230.0
    assert source == "mark_price"


def test_option_executable_price_falls_back_to_ltp_when_ask_and_mark_missing(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    price, source = builder._option_executable_price(
        {
            "ask": None,
            "best_ask": None,
            "mark_price": None,
            "ltp": 229.9,
            "last_price": 229.9,
            "signal_price": 100.99,
        },
        side="BUY",
    )

    assert price == 229.9
    assert source == "ltp"
