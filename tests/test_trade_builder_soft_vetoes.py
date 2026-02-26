from __future__ import annotations

from config import config as cfg
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.95


def _patch_builder(monkeypatch, builder):
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda _md, force_family=None: {
            "direction": "BUY_CALL",
            "reason": "unit_test_signal",
            "score": 0.95,
            "regime_day": "TREND",
        },
        raising=True,
    )
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"), raising=True)
    monkeypatch.setattr(builder, "_apply_decay_gate", lambda *_args, **_kwargs: (True, None, 1.0, None), raising=True)
    monkeypatch.setattr(builder, "_validate_ml_features", lambda _feats: (True, "ok"), raising=True)
    monkeypatch.setattr(trade_builder_module, "compute_trade_score", lambda *args, **kwargs: {"score": 100.0, "alignment": 1.0})
    monkeypatch.setattr(cfg, "ALPHA_ENSEMBLE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_AB_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_USE_ONLY_WITH_HISTORY", False, raising=False)
    monkeypatch.setattr(cfg, "ML_MIN_PROBA", 0.1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 1.0, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)
    monkeypatch.setattr(cfg, "MIN_RR", 0.1, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)


def _base_market_data(option_ltp: float) -> dict:
    return {
        "symbol": "NIFTY",
        "market_open": True,
        "valid": True,
        "ltp": 25000.0,
        "vwap": 24990.0,
        "bias": "Bullish",
        "instrument": "OPT",
        "chain_source": "live",
        "quote_ok": True,
        "bid": 24999.0,
        "ask": 25001.0,
        "regime": "TREND",
        "regime_day": "TREND",
        "day_type": "TREND_DAY",
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000,
                "expiry": "2026-02-26",
                "tradingsymbol": "NIFTY26FEB25000CE",
                "instrument_token": 123456,
                "ltp": option_ltp,
                "bid": option_ltp - 1.0,
                "ask": option_ltp + 1.0,
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


def test_paper_orb_pending_is_soft_veto(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_HARD_BLOCK_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_HARD_CONFLICT_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_NEUTRAL_ALLOW", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["orb_bias"] = "PENDING"

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert "orb_pending" in (trade.source_flags.get("soft_veto_codes") or [])


def test_paper_orb_neutral_is_soft_veto(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_HARD_BLOCK_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_NEUTRAL_ALLOW", False, raising=False)
    monkeypatch.setattr(cfg, "PLANNING_ORB_NEUTRAL_ALLOW", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["orb_bias"] = "NEUTRAL"

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert "orb_neutral_blocked" in (trade.source_flags.get("soft_veto_codes") or [])


def test_premium_out_of_band_is_soft_veto_when_liquid(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (20.0, 120.0)}, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.02, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=180.0)

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert trade.source_flags.get("premium_soft_veto") is True
    assert "premium_out_of_band" in (trade.source_flags.get("soft_veto_codes") or [])


def test_dynamic_premium_band_uses_chain_percentiles_not_global_clamp(monkeypatch):
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (40.0, 150.0)}, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_PERCENTILE_LOW", 0.10, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_PERCENTILE_HIGH", 0.90, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_ATM_MONEYNESS_MAX", 0.05, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_MIN_ROWS", 6, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_MIN_VOLUME", 1, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    chain = [
        {"expiry": "2026-02-26", "ltp": 10 + (i * 20), "volume": 100, "moneyness": 0.01}
        for i in range(10)
    ]
    bands = builder._dynamic_premium_bands("NIFTY", chain)
    assert "2026-02-26" in bands
    band_min, band_max = bands["2026-02-26"]
    # Global fallback band is 40..150; dynamic band should not be hard-clamped to it.
    assert band_min < 40.0
    assert band_max > 150.0


def test_paper_missing_quote_depth_stays_suggestion_with_execution_block(monkeypatch):
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", True, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    opt = md["option_chain"][0]
    opt["quote_ok"] = False
    opt["quote_live"] = False
    opt["quote_ts_epoch"] = None
    opt["quote_age_sec"] = 999.0
    opt["depth_ok"] = False
    opt["volume"] = 0
    opt["bid"] = None
    opt["ask"] = None

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert trade.execution_allowed is False
    soft_codes = set(trade.source_flags.get("soft_veto_codes") or [])
    gate_codes = set(trade.source_flags.get("gates_failed") or [])
    assert "option_quote_missing" in soft_codes or "option_bidask_missing" in soft_codes
    assert "option_quote_missing" in gate_codes or "option_bidask_missing" in gate_codes
