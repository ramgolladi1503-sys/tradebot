from __future__ import annotations

import logging

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
    monkeypatch.setattr(cfg, "DEBUG_TRADE_MODE", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
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


def _market_data_with_option_overrides(**overrides) -> dict:
    option_row = {
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
    option_row.update(overrides)
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
        "option_chain": [option_row],
    }


def test_reject_exit_emits_aggregated_tb_reject_summary(caplog):
    builder = TradeBuilder()
    builder._scan_total_candidates = 6
    builder._scan_reject_counts = {
        "no_quote": 3,
        "confidence_final_gate": 2,
        "spread_pct": 1,
    }
    builder._last_option_scan_summary = {
        "symbol": "NIFTY",
        "considered": 6,
        "survivors": 0,
        "option_reject_total": 6,
        "top_rejects": {"no_quote": 3, "confidence_final_gate": 2, "spread_pct": 1},
    }

    with caplog.at_level(logging.INFO):
        builder._reject_exit({"symbol": "NIFTY"}, "no_candidates_survived")

    assert "TB_REJECT_SUMMARY" in caplog.text
    assert any(
        record.levelno >= logging.WARNING and "TB_REJECT_SUMMARY" in record.getMessage()
        for record in caplog.records
    )
    assert "'symbol': 'NIFTY'" in caplog.text
    assert "'total_candidates': 6" in caplog.text
    assert "'survived': 0" in caplog.text
    assert "'survived_candidates': 0" in caplog.text
    assert "'no_quote': 3" in caplog.text
    assert "'confidence_final_gate': 2" in caplog.text
    assert builder._reject_ctx["reject_counts"]["no_quote"] == 3


def test_build_tracks_iv_reject_and_emits_summary(caplog, monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", True, raising=False)

    with caplog.at_level(logging.INFO):
        builder.build(
            _market_data_with_option_overrides(iv=0.8),
            quick_mode=False,
            allow_fallbacks=False,
            allow_baseline=False,
        )

    assert int(builder._scan_reject_counts.get("iv_bounds", 0)) >= 1
    assert "TB_REJECT_SUMMARY" in caplog.text
    assert "'iv_bounds':" in caplog.text


def test_build_emits_reject_summary_on_softened_no_viable_path(caplog, monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(cfg, "DEBUG_TRADE_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", True, raising=False)

    with caplog.at_level(logging.INFO):
        trade = builder.build(
            _market_data_with_option_overrides(iv=0.8),
            quick_mode=False,
            allow_fallbacks=False,
            allow_baseline=False,
        )

    assert trade is None
    assert builder._reject_ctx["reason"] == "no_candidates_survived"
    assert int(builder._scan_reject_counts.get("iv_bounds", 0)) >= 1
    assert "TB_REJECT_SUMMARY" in caplog.text
    assert "OPTION_SCAN_REJECT_SUMMARY" in caplog.text
    assert "NO_CANDIDATE_PATH" in caplog.text
    assert any(
        record.levelno >= logging.WARNING and "TB_REJECT_SUMMARY" in record.getMessage()
        for record in caplog.records
    )


def test_build_non_live_iv_bounds_survives_as_soft_veto(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)

    trade = builder.build(
        _market_data_with_option_overrides(iv=0.8),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    assert "iv_bounds" in list(getattr(trade, "source_flags", {}).get("soft_veto_codes") or [])
    assert "iv_bounds" in list(getattr(trade, "source_flags", {}).get("non_live_relaxed_gate_codes") or [])


def test_build_live_iv_bounds_still_rejects_when_hard_gate_enabled(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", True, raising=False)

    trade = builder.build(
        _market_data_with_option_overrides(iv=0.8),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None
    assert int(builder._scan_reject_counts.get("iv_bounds", 0)) >= 1


def test_build_live_iv_bounds_softens_by_default(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_IV_BOUNDS_HARD_REJECT", False, raising=False)

    trade = builder.build(
        _market_data_with_option_overrides(iv=0.8),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    source_flags = getattr(trade, "source_flags", {}) or {}
    assert "iv_bounds" in list(source_flags.get("soft_veto_codes") or [])
    assert "iv_bounds" in list(source_flags.get("non_live_relaxed_gate_codes") or [])


def test_build_live_iv_skew_curvature_softens_by_default(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_IV_SKEW_CURVATURE_HARD_REJECT", False, raising=False)

    trade = builder.build(
        _market_data_with_option_overrides(iv_skew_curvature=2.0),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    source_flags = getattr(trade, "source_flags", {}) or {}
    assert "iv_skew_curvature" in list(source_flags.get("soft_veto_codes") or [])
    assert "iv_skew_curvature" in list(source_flags.get("non_live_relaxed_gate_codes") or [])


def test_build_live_iv_skew_curvature_still_rejects_when_hard_gate_enabled(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_IV_SKEW_CURVATURE_HARD_REJECT", True, raising=False)

    trade = builder.build(
        _market_data_with_option_overrides(iv_skew_curvature=2.0),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None
    assert int(builder._scan_reject_counts.get("iv_skew_curvature", 0)) >= 1


def test_build_live_iv_skew_curve_call_softens_by_default(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_IV_SKEW_CURVE_HARD_REJECT", False, raising=False)

    trade = builder.build(
        _market_data_with_option_overrides(iv_skew_curvature_call=2.0),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    source_flags = getattr(trade, "source_flags", {}) or {}
    assert "iv_skew_curvature" in list(source_flags.get("soft_veto_codes") or [])
    assert "iv_skew_curve_call" in list(source_flags.get("non_live_relaxed_gate_codes") or [])


def test_build_live_iv_skew_curve_call_rejects_when_hard_gate_enabled(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "OPTION_IV_SKEW_CURVE_HARD_REJECT", True, raising=False)

    trade = builder.build(
        _market_data_with_option_overrides(iv_skew_curvature_call=2.0),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None
    assert int(builder._scan_reject_counts.get("iv_skew_curve_call", 0)) >= 1


def test_build_can_inject_min_scan_survivors_when_all_rows_rejected(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "OPTION_SCAN_MIN_SURVIVORS_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OPTION_SCAN_MIN_SURVIVORS_COUNT", 2, raising=False)
    monkeypatch.setattr(cfg, "OPTION_SCAN_MIN_SURVIVOR_SCORE", 0.33, raising=False)
    monkeypatch.setattr(cfg, "OPTION_SCAN_MIN_SURVIVORS_ALLOWED_MODES", "SIM", raising=False)

    trade = builder.build(
        _market_data_with_option_overrides(
            ltp=0.0,
            last_price=0.0,
            bid=0.0,
            ask=0.0,
            best_bid=0.0,
            best_ask=0.0,
        ),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    if isinstance(trade, dict):
        source_flags = dict(trade.get("source_flags") or {})
        candidate_origin = trade.get("candidate_origin")
    else:
        source_flags = dict(getattr(trade, "source_flags", {}) or {})
        candidate_origin = getattr(trade, "candidate_origin", None)
    assert source_flags.get("scan_min_survivor") is True
    assert candidate_origin == "scan_min_survivor"


def test_build_non_live_low_trade_score_survives_to_candidate(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(
        trade_builder_module,
        "compute_trade_score",
        lambda *args, **kwargs: {"score": 10.0, "alignment": 1.0},
    )
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 75.0, raising=False)

    trade = builder.build(
        _market_data_with_option_overrides(),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    assert "trade_score" in list(getattr(trade, "source_flags", {}).get("soft_veto_codes") or [])
    assert "trade_score" in list(getattr(trade, "source_flags", {}).get("non_live_relaxed_gate_codes") or [])
    assert bool(((getattr(trade, "source_flags", {}) or {}).get("decision_trace") or {}).get("trade_score_gate_relaxed"))


def test_annotate_candidate_chain_rows_emits_empty_chain_debug(caplog):
    builder = TradeBuilder()
    builder._resolve_expiry_for_symbol = lambda symbol, data: None

    with caplog.at_level(logging.INFO):
        rows = builder._annotate_candidate_chain_rows(
            "BANKNIFTY",
            {"symbol": "BANKNIFTY", "option_chain": [], "ltp": 50000.0},
            50000.0,
        )

    assert rows == []
    assert "CHAIN_DEBUG_START symbol=BANKNIFTY raw_len=0" in caplog.text
    assert "CHAIN_DEBUG_EXPIRY symbol=BANKNIFTY len=0" in caplog.text
    assert "CHAIN_DEBUG_STRIKE symbol=BANKNIFTY len=0" in caplog.text
    assert "CHAIN_EMPTY symbol=BANKNIFTY reason=post_filters" in caplog.text
