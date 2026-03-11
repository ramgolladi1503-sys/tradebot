from __future__ import annotations

from config import config as cfg
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.95


class _PredictorFixed:
    model_version = "stub"
    shadow_version = None

    def __init__(self, value: float):
        self.value = float(value)

    def predict_confidence(self, _feats):
        return self.value


class _PredictorNone:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return None


class _MicroPredictorFixed:
    def __init__(self, value: float):
        self.value = float(value)

    def predict_confidence(self, _features):
        return self.value


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
    monkeypatch.setattr(cfg, "ORB_SOFT_VETO_CONF_PENALTY", 0.04, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["orb_bias"] = "PENDING"

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert "orb_pending" in (trade.source_flags.get("soft_veto_codes") or [])
    assert float(trade.confidence_before_soft_veto) == 0.95
    assert float(trade.confidence_after_soft_veto) == 0.91
    assert float(trade.confidence_penalty_soft_veto_total) == 0.04
    assert trade.confidence_penalty_soft_veto_reasons == ["orb_pending"]


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
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MIN", 0.06, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MAX", 0.10, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.02, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=180.0)

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert trade.source_flags.get("premium_soft_veto") is True
    assert "premium_out_of_band" in (trade.source_flags.get("soft_veto_codes") or [])
    assert float(trade.confidence_before_soft_veto) == 0.95
    assert 0.85 <= float(trade.confidence_after_soft_veto) <= 0.89
    assert 0.06 <= float(trade.confidence_penalty_soft_veto_total) <= 0.10
    assert "premium_out_of_band" in list(trade.confidence_penalty_soft_veto_reasons)


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


def test_paper_missing_quote_depth_is_rejected_by_option_tradability_precondition(monkeypatch):
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
    assert trade is None
    assert int(builder._scan_reject_counts.get("STALE_OPTION_TICK", 0)) >= 1


def test_trade_builder_candidate_passes_raw_and_final_confidence_gates(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.44, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.31, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.52))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert float(trade.confidence_model_raw) == 0.52
    assert float(trade.confidence_gate_threshold) == 0.31
    assert float(trade.confidence_raw_gate_threshold) == 0.44
    assert float(trade.confidence_final_gate_threshold) == 0.31


def test_trade_builder_candidate_fails_final_confidence_gate_after_soft_veto(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.44, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.33, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (20.0, 120.0)}, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MIN", 0.08, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MAX", 0.14, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.02, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.46))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=300.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("confidence_final_gate", 0)) >= 1


def test_multiple_soft_vetoes_are_bounded_and_interpretable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_HARD_BLOCK_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_NEUTRAL_ALLOW", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_SOFT_VETO_CONF_PENALTY", 0.05, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (20.0, 120.0)}, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MIN", 0.07, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MAX", 0.12, raising=False)
    monkeypatch.setattr(cfg, "SOFT_VETO_CONF_PENALTY_MAX_TOTAL", 0.10, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.02, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)
    md = _base_market_data(option_ltp=300.0)
    md["orb_bias"] = "PENDING"

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert float(trade.confidence_before_soft_veto) == 0.85
    assert float(trade.confidence_penalty_soft_veto_total) == 0.10
    assert float(trade.confidence_after_soft_veto) == 0.75
    assert trade.confidence_penalty_soft_veto_reasons == ["orb_pending", "premium_out_of_band", "premium_band_fail"]


def test_trade_builder_candidate_fails_raw_confidence_gate_early(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.50, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.30, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.42))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("confidence_raw_gate", 0)) >= 1


def test_micro_overlay_keeps_strong_model_from_collapsing(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "USE_MICRO_MODEL", True, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_WEIGHT", 0.25, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_MAX_DELTA", 0.10, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.40, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.30, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.82))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder, "_get_micro_predictor", lambda: _MicroPredictorFixed(0.20), raising=True)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert float(trade.confidence_model_component) == 0.82
    assert float(trade.confidence_micro_component) == 0.20
    assert trade.confidence_micro_blend_method == "bounded_overlay"
    assert float(trade.confidence_after_micro) == 0.72
    assert float(trade.confidence_after_micro) > 0.50


def test_micro_overlay_does_not_overpromote_weak_model(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "USE_MICRO_MODEL", True, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_WEIGHT", 0.25, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_MAX_DELTA", 0.10, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.35, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.25, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.22))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder, "_get_micro_predictor", lambda: _MicroPredictorFixed(0.92), raising=True)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("confidence_raw_gate", 0)) >= 1


def test_micro_confidence_fallback_allows_missing_model(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "USE_MICRO_MODEL", True, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_WEIGHT", 0.25, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_MAX_DELTA", 0.10, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.45, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.35, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorNone())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder, "_get_micro_predictor", lambda: _MicroPredictorFixed(0.58), raising=True)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.confidence_model_component is None
    assert float(trade.confidence_micro_component) == 0.58
    assert trade.confidence_micro_blend_method == "micro_fallback"
    assert float(trade.confidence_after_micro) == 0.58
