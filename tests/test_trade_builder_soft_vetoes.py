from __future__ import annotations

from dataclasses import asdict
import logging
import json
from types import SimpleNamespace
import pytest

from config import config as cfg
from core import review_queue
import core.offline_family_learning as family_learning
from core.threshold_audit import load_candidate_decisions
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


def _opportunity_market_data(symbol: str = "NIFTY", option_ltp: float = 100.0) -> dict:
    market_data = _base_market_data(option_ltp=option_ltp)
    market_data["symbol"] = symbol
    market_data["execution_mode"] = "SIM"
    market_data["market_context"] = {"execution_mode": "SIM", "market_open": True}
    market_data["atr"] = 50.0
    market_data["ltp_change"] = 0.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = 0.0
    market_data["ltp_change_10m"] = 0.0
    market_data["rsi_mom"] = 0.0
    market_data["vol_z"] = 0.0
    put_opt = dict(market_data["option_chain"][0])
    put_opt["type"] = "PE"
    put_opt["tradingsymbol"] = f"{symbol}26FEB25000PE"
    put_opt["instrument_token"] = 223456
    market_data["option_chain"] = [dict(market_data["option_chain"][0]), put_opt]
    return market_data


def _signal(direction: str) -> SimpleNamespace:
    return SimpleNamespace(direction=direction, reason="unit_test_signal", score=0.72)


def _disable_opportunity_signals(monkeypatch) -> None:
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)


_STAGED_CONFIDENCE_FIELDS = (
    "confidence_model_raw",
    "confidence_model_component",
    "confidence_micro_component",
    "confidence_micro_blend_method",
    "confidence_after_micro",
    "confidence_after_alpha",
    "confidence_after_latency",
    "confidence_before_soft_veto",
    "confidence_after_soft_veto",
    "confidence_penalty_soft_veto_total",
    "confidence_penalty_soft_veto_reasons",
    "confidence_gate_threshold",
    "confidence_raw_gate_threshold",
    "confidence_final_gate_threshold",
    "confidence_rejection_stage",
    "confidence_base",
    "confidence_penalty_total",
    "confidence_penalty_reasons",
)


def _serialize_trade_row(tmp_path, monkeypatch, trade):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "ENABLE_EQUITIES", True, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    review_queue.add_to_queue(asdict(trade))
    return json.loads(qpath.read_text())[-1]


def _assert_staged_confidence_fields_present(row: dict):
    for key in _STAGED_CONFIDENCE_FIELDS:
        assert key in row


def build_id(symbol: str, expiry: str, strike: int, opt_type: str) -> str:
    return f"{symbol}|OPT|{expiry}|{strike}|{opt_type}"


def test_premium_band_summary_logging_and_spam_suppressed(monkeypatch, caplog):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (10.0, 20.0)}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    market_data = _base_market_data(option_ltp=100.0)
    opt2 = dict(market_data["option_chain"][0])
    opt2["strike"] = 25050
    opt2["tradingsymbol"] = "NIFTY26FEB25050CE"
    opt2["instrument_token"] = 123457
    market_data["option_chain"].append(opt2)

    calls: list[str] = []
    orig = builder._log_blocked_candidate

    def _spy(*args, **kwargs):
        if len(args) > 2:
            calls.append(str(args[2]))
        elif "reason_code" in kwargs:
            calls.append(str(kwargs["reason_code"]))
        return orig(*args, **kwargs)

    monkeypatch.setattr(builder, "_log_blocked_candidate", _spy, raising=True)

    caplog.set_level(logging.INFO)
    builder.build(market_data, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert caplog.text.count("PREMIUM_BAND_FAIL_SUMMARY") == 1
    assert "premium_band_fail_count=2" in caplog.text
    assert "premium_band_fail" not in calls


def test_premium_band_out_of_band_does_not_kill_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (10.0, 20.0)}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.9))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=True, allow_baseline=False)

    assert trade is not None
    source_flags = dict(trade.source_flags or {})
    assert source_flags.get("premium_soft_veto") is True
    assert "premium_out_of_band" in (source_flags.get("soft_veto_codes") or [])


def test_fallback_top_ranked_candidate_when_selection_none(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    def _select_best_stub(_candidates, **_kwargs):
        return None, [
            {
                "trade_id": "cand_1",
                "rank_score": 0.91,
                "confidence": 0.42,
                "size_mult": 1.0,
                "tradable_reasons_blocking": [],
                "source_flags": {},
            }
        ]

    monkeypatch.setattr(trade_builder_module, "select_best_opportunity", _select_best_stub, raising=True)
    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=True, allow_baseline=False)

    assert trade is not None
    if isinstance(trade, dict):
        assert trade.get("fallback_candidate") is True
        assert trade.get("fallback_reason") == "no_viable_candidates_top_ranked"
        assert trade.get("execution_allowed") is False
    else:
        assert trade.source_flags.get("fallback_candidate") is True
        assert trade.reason == "no_viable_candidates_top_ranked"
        assert trade.execution_allowed is False
        assert trade.candidate_class == "ADVISORY_ONLY"


def test_build_sets_concrete_reject_reason_when_no_trade_and_no_fallback(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    def _select_best_stub(_candidates, **_kwargs):
        return None, []

    monkeypatch.setattr(trade_builder_module, "select_best_opportunity", _select_best_stub, raising=True)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert str(builder._reject_ctx.get("reason") or "").strip() in {"no_viable_candidates", "no_candidates_survived"}
    assert isinstance(builder._last_option_scan_summary, dict)
    assert builder._last_option_scan_summary.get("symbol") == "NIFTY"


def test_invalid_snapshot_still_blocks_trade(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    builder = TradeBuilder()

    trade = builder.build(
        {"symbol": "NIFTY", "valid": False, "invalid_reason": "invalid_snapshot"},
        quick_mode=False,
    )

    assert trade is None
    assert builder._reject_ctx.get("reason") == "invalid_snapshot"


def test_offhours_ranks_candidates_without_executable_rows(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.88))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    market_data = _base_market_data(option_ltp=100.0)
    market_data["market_open"] = False
    market_data["market_context"] = {"execution_mode": "LIVE", "market_open": False}

    trade = builder.build(market_data, quick_mode=False, allow_fallbacks=True, allow_baseline=False)

    assert trade is not None
    assert trade.market_mode == "OFFHOURS"
    assert trade.execution_allowed is False
    assert trade.candidate_class == "ADVISORY_ONLY"
    ranked = list(builder._last_ranked_candidates or [])
    assert ranked
    ranked_classes = {
        str((row.get("candidate_class") if isinstance(row, dict) else getattr(row, "candidate_class", None)) or "").strip().upper()
        for row in ranked
    }
    assert "EXECUTABLE" not in ranked_classes


def test_bearish_snapshot_produces_non_bullish_candidates(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.82))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["ltp"] = 24920.0
    market_data["vwap"] = 25010.0
    market_data["ltp_change_window"] = -35.0
    market_data["ltp_change_5m"] = -24.0
    market_data["ltp_change_10m"] = -42.0
    market_data["rsi_mom"] = -0.45
    market_data["vol_z"] = 1.2

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_bearish",
    )

    assert candidates
    assert any(str(getattr(candidate, "direction", "")).strip().upper() == "BUY_PUT" for candidate in candidates)


def test_bearish_regime_generates_real_bearish_candidates(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.82))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 24880.0
    market_data["vwap"] = 25020.0
    market_data["ltp_change_window"] = -40.0
    market_data["ltp_change_5m"] = -22.0
    market_data["ltp_change_10m"] = -45.0
    market_data["rsi_mom"] = -0.55
    market_data["vol_z"] = 1.3

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_bearish_regime",
    )

    assert candidates
    assert any(str(getattr(candidate, "direction", "")).strip().upper() == "BUY_PUT" for candidate in candidates)
    bearish_candidates = [
        candidate
        for candidate in candidates
        if str(getattr(candidate, "direction_family", "")).strip().lower() == "bearish"
    ]
    assert bearish_candidates
    assert all(float(getattr(candidate, "family_strength", 0.0) or 0.0) > 0.0 for candidate in bearish_candidates)
    assert all(getattr(candidate, "family_blocker", None) in (None, "") for candidate in bearish_candidates)


def test_sideways_snapshot_does_not_only_emit_buys(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.76))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="BANKNIFTY")
    market_data["ltp"] = 25005.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = 0.0
    market_data["ltp_change_10m"] = 0.0
    market_data["rsi_mom"] = 0.32
    market_data["vol_z"] = 0.15

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_sideways",
    )

    assert candidates
    assert any(getattr(candidate, "strategy_family", None) == "mean-reversion" for candidate in candidates)
    directions = {str(getattr(candidate, "direction", "")).strip().upper() for candidate in candidates}
    assert directions != {"BUY_CALL"}


def test_sideways_regime_caps_directional_candidates(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "RANGE_WATCHLIST_ENABLE", True, raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.76))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="BANKNIFTY")
    market_data["regime"] = "RANGE"
    market_data["regime_day"] = "RANGE"
    market_data["ltp"] = 25024.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = 0.0
    market_data["ltp_change_10m"] = 0.0
    market_data["rsi_mom"] = 0.10
    market_data["vol_z"] = 0.10

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_sideways_cap",
    )

    assert candidates
    assert all(getattr(candidate, "strategy", None) != "OPP_DIRECTIONAL" for candidate in candidates)
    assert all(str(getattr(candidate, "direction_family", "")).strip().lower() != "bullish" for candidate in candidates)


def test_sideways_snapshot_can_emit_watchlist_candidates(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "RANGE_WATCHLIST_ENABLE", True, raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.76))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="BANKNIFTY")
    market_data["regime"] = "RANGE"
    market_data["regime_day"] = "RANGE"
    market_data["ltp"] = 25024.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = 0.0
    market_data["ltp_change_10m"] = 0.0
    market_data["rsi_mom"] = 0.10
    market_data["vol_z"] = 0.10

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_sideways_watchlist",
    )

    assert candidates
    watchlist = next(candidate for candidate in candidates if getattr(candidate, "strategy", None) == "OPP_RANGE_WATCHLIST")
    assert watchlist.direction_family == "sideways"
    assert watchlist.family_blocker == "sideways_watchlist_only"
    assert float(watchlist.family_strength or 0.0) > 0.0


def test_mirrored_bearish_candidate_is_penalized_or_rejected(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "BEARISH_DIRECTIONAL_STRUCTURE_MIN", 0.95, raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.82))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 25080.0
    market_data["vwap"] = 24980.0
    market_data["ltp_change_window"] = 28.0
    market_data["ltp_change_5m"] = 18.0
    market_data["ltp_change_10m"] = 32.0
    market_data["rsi_mom"] = 0.35
    market_data["vol_z"] = 0.9

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_mirrored_bearish",
    )

    assert all(
        not (
            str(getattr(candidate, "strategy", "")).strip().upper() == "OPP_DIRECTIONAL"
            and str(getattr(candidate, "direction", "")).strip().upper() == "BUY_PUT"
        )
        for candidate in candidates
    )


def test_family_scarcity_prevents_directional_flooding(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES", 1, raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.84))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 24860.0
    market_data["vwap"] = 25030.0
    market_data["ltp_change_window"] = -45.0
    market_data["ltp_change_5m"] = -25.0
    market_data["ltp_change_10m"] = -50.0
    market_data["rsi_mom"] = -0.62
    market_data["vol_z"] = 1.4

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_family_scarcity",
    )

    bearish_candidates = [
        candidate
        for candidate in candidates
        if str(getattr(candidate, "direction_family", "")).strip().lower() == "bearish"
    ]
    assert bearish_candidates
    assert len(bearish_candidates) == 1
    assert int(getattr(bearish_candidates[0], "family_rank", 0) or 0) == 1


def test_strong_family_can_gain_small_extra_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / ".runtime"), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_FAMILY_LEARNING_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES", 1, raising=False)
    state = {
        "version": 1,
        "generated_at": "2026-04-04T00:00:00+00:00",
        "min_samples": 25,
        "families": {
            "continuation|bearish": {
                "family_score_adjustment": 0.04,
                "family_scarcity_adjustment": 1,
                "family_confidence": 0.8,
                "family_feedback_applied": True,
                "expectancy_score": 0.5,
            }
        },
    }
    family_learning.save_family_learning_state(state)

    builder = TradeBuilder(predictor=_PredictorFixed(0.84))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 24860.0
    market_data["vwap"] = 25030.0
    market_data["ltp_change_window"] = -45.0
    market_data["ltp_change_5m"] = -25.0
    market_data["ltp_change_10m"] = -50.0
    market_data["rsi_mom"] = -0.62
    market_data["vol_z"] = 1.4

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_family_learning_strong",
    )

    bearish_candidates = [
        candidate
        for candidate in candidates
        if str(getattr(candidate, "direction_family", "")).strip().lower() == "bearish"
    ]
    assert len(bearish_candidates) == 2
    assert all(int(getattr(candidate, "family_cap_effective", 0) or 0) == 2 for candidate in bearish_candidates)
    assert any(float(getattr(candidate, "family_learning_adjustment", 0.0) or 0.0) > 0.0 for candidate in bearish_candidates)


def test_weak_family_can_lose_small_slot(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / ".runtime"), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_FAMILY_LEARNING_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES", 2, raising=False)
    state = {
        "version": 1,
        "generated_at": "2026-04-04T00:00:00+00:00",
        "min_samples": 25,
        "families": {
            "continuation|bearish": {
                "family_score_adjustment": -0.05,
                "family_scarcity_adjustment": -1,
                "family_confidence": 0.8,
                "family_feedback_applied": True,
                "expectancy_score": -0.4,
            },
            "breakout|bearish": {
                "family_score_adjustment": -0.04,
                "family_scarcity_adjustment": -1,
                "family_confidence": 0.8,
                "family_feedback_applied": True,
                "expectancy_score": -0.3,
            },
            "mean-reversion|bearish": {
                "family_score_adjustment": -0.03,
                "family_scarcity_adjustment": -1,
                "family_confidence": 0.8,
                "family_feedback_applied": True,
                "expectancy_score": -0.2,
            },
        },
    }
    family_learning.save_family_learning_state(state)

    builder = TradeBuilder(predictor=_PredictorFixed(0.84))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 24860.0
    market_data["vwap"] = 25030.0
    market_data["ltp_change_window"] = -45.0
    market_data["ltp_change_5m"] = -25.0
    market_data["ltp_change_10m"] = -50.0
    market_data["rsi_mom"] = -0.62
    market_data["vol_z"] = 1.4

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_family_learning_weak",
    )

    bearish_candidates = [
        candidate
        for candidate in candidates
        if str(getattr(candidate, "direction_family", "")).strip().lower() == "bearish"
    ]
    assert len(bearish_candidates) == 1
    assert int(getattr(bearish_candidates[0], "family_cap_effective", 0) or 0) == 1
    assert float(getattr(bearish_candidates[0], "family_learning_adjustment", 0.0) or 0.0) < 0.0


def test_family_scarcity_adjustment_is_bounded(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / ".runtime"), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_FAMILY_LEARNING_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_FAMILY_LEARNING_MAX_SCARCITY_DELTA", 1, raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES", 1, raising=False)
    state = {
        "version": 1,
        "generated_at": "2026-04-04T00:00:00+00:00",
        "min_samples": 25,
        "families": {
            "continuation|bearish": {
                "family_score_adjustment": 0.05,
                "family_scarcity_adjustment": 5,
                "family_confidence": 0.9,
                "family_feedback_applied": True,
                "expectancy_score": 0.7,
            }
        },
    }
    family_learning.save_family_learning_state(state)

    builder = TradeBuilder(predictor=_PredictorFixed(0.84))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 24860.0
    market_data["vwap"] = 25030.0
    market_data["ltp_change_window"] = -45.0
    market_data["ltp_change_5m"] = -25.0
    market_data["ltp_change_10m"] = -50.0
    market_data["rsi_mom"] = -0.62
    market_data["vol_z"] = 1.4

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=market_data["ltp"],
        vwap=market_data["vwap"],
        trigger_reason="unit_test_family_learning_bounded",
    )

    bearish_candidates = [
        candidate
        for candidate in candidates
        if str(getattr(candidate, "direction_family", "")).strip().lower() == "bearish"
    ]
    assert len(bearish_candidates) == 2
    assert all(int(getattr(candidate, "family_cap_effective", 0) or 0) == 2 for candidate in bearish_candidates)


def test_sideways_regime_disables_weak_trend_families(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.76))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="BANKNIFTY")
    market_data["regime"] = "RANGE"
    market_data["regime_day"] = "RANGE"
    market_data["ltp"] = 25008.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 2.0
    market_data["ltp_change_5m"] = 1.0
    market_data["ltp_change_10m"] = 2.0
    market_data["rsi_mom"] = 0.05
    market_data["vol_z"] = 0.10

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_sideways_disable_trend")

    assert all(getattr(candidate, "strategy", None) not in {"OPP_DIRECTIONAL", "OPP_VOL_EXPANSION"} for candidate in candidates)


def test_low_vol_regime_defaults_to_sparse_or_no_trade_behavior(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.70))
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "NEUTRAL"
    market_data["regime_day"] = "NEUTRAL"
    market_data["atr"] = 60.0
    market_data["ltp"] = 25001.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 1.0
    market_data["ltp_change_5m"] = 0.5
    market_data["ltp_change_10m"] = 0.8
    market_data["rsi_mom"] = 0.01
    market_data["vol_z"] = 0.05

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_low_vol_sparse")

    assert candidates == [] or all(getattr(candidate, "direction_family", None) == "sideways" for candidate in candidates)


def test_trending_regime_suppresses_weak_range_family(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.78))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 25040.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 30.0
    market_data["ltp_change_5m"] = 20.0
    market_data["ltp_change_10m"] = 35.0
    market_data["rsi_mom"] = 0.08
    market_data["vol_z"] = 0.4

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_trending_suppress_range")

    assert all(getattr(candidate, "strategy_family", None) != "mean-reversion" for candidate in candidates)


def test_sideways_snapshot_can_emit_real_sideways_watchlist_candidates(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "RANGE_WATCHLIST_ENABLE", True, raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.76))
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="BANKNIFTY")
    market_data["regime"] = "RANGE"
    market_data["regime_day"] = "RANGE"
    market_data["ltp"] = 24970.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = -1.0
    market_data["ltp_change_10m"] = 1.0
    market_data["rsi_mom"] = -0.14
    market_data["vol_z"] = 0.10

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_sideways_real_watchlist")

    assert any(getattr(candidate, "strategy", None) == "OPP_RANGE_WATCHLIST" for candidate in candidates)


def test_sideways_range_candidate_carries_sideways_direction_family(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "RANGE_WATCHLIST_ENABLE", True, raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.76))
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="BANKNIFTY")
    market_data["regime"] = "RANGE"
    market_data["regime_day"] = "RANGE"
    market_data["ltp"] = 25030.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = 1.0
    market_data["ltp_change_10m"] = -1.0
    market_data["rsi_mom"] = 0.14
    market_data["vol_z"] = 0.10

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_sideways_direction_family")
    watchlist = next(candidate for candidate in candidates if getattr(candidate, "strategy", None) == "OPP_RANGE_WATCHLIST")

    assert watchlist.direction_family == "sideways"


def test_sideways_without_clean_range_edge_emits_none(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "RANGE_WATCHLIST_ENABLE", True, raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.76))
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="BANKNIFTY")
    market_data["regime"] = "RANGE"
    market_data["regime_day"] = "RANGE"
    market_data["ltp"] = 25000.5
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = 0.0
    market_data["ltp_change_10m"] = 0.0
    market_data["rsi_mom"] = 0.01
    market_data["vol_z"] = 0.05

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_sideways_no_edge")

    assert candidates == []


def test_bearish_candidate_requires_positive_bearish_structure(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.82))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 25080.0
    market_data["vwap"] = 24980.0
    market_data["ltp_change_window"] = 28.0
    market_data["ltp_change_5m"] = 18.0
    market_data["ltp_change_10m"] = 32.0
    market_data["rsi_mom"] = 0.35
    market_data["vol_z"] = 0.9

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_bearish_requires_positive")

    assert all(str(getattr(candidate, "direction_family", "")).strip().lower() != "bearish" for candidate in candidates)


def test_strong_aligned_family_can_gain_bounded_extra_slot(monkeypatch, tmp_path):
    test_strong_family_can_gain_small_extra_slot(monkeypatch, tmp_path)


def test_weak_or_uncertain_regime_reduces_effective_family_cap(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES", 2, raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.82))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: None, raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "NEUTRAL"
    market_data["regime_day"] = "NEUTRAL"
    market_data["ltp"] = 25020.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 12.0
    market_data["ltp_change_5m"] = 8.0
    market_data["ltp_change_10m"] = 10.0
    market_data["rsi_mom"] = 0.10
    market_data["vol_z"] = 0.15

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_uncertain_cap")

    bullish_candidates = [candidate for candidate in candidates if getattr(candidate, "direction_family", None) == "bullish"]
    assert bullish_candidates
    assert all(int(getattr(candidate, "family_cap_effective", 0) or 0) == 1 for candidate in bullish_candidates)


def test_no_family_can_exceed_hard_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / ".runtime"), raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_FAMILY_LEARNING_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "OFFLINE_STRATEGY_WEIGHT_LEARNING_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_DIRECTION_FAMILY_MAX_CANDIDATES", 1, raising=False)
    family_learning.save_family_learning_state(
        {
            "version": 1,
            "generated_at": "2026-04-04T00:00:00+00:00",
            "min_samples": 25,
            "families": {
                "continuation|bearish": {
                    "family_score_adjustment": 0.06,
                    "family_scarcity_adjustment": 1,
                    "family_confidence": 1.0,
                    "family_feedback_applied": True,
                    "expectancy_score": 0.7,
                }
            },
        }
    )
    builder = TradeBuilder(predictor=_PredictorFixed(0.84))
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)
    monkeypatch.setattr(trade_builder_module, "micro_pattern_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 24860.0
    market_data["vwap"] = 25030.0
    market_data["ltp_change_window"] = -45.0
    market_data["ltp_change_5m"] = -25.0
    market_data["ltp_change_10m"] = -50.0
    market_data["rsi_mom"] = -0.62
    market_data["vol_z"] = 1.4

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_hard_cap")
    bearish_candidates = [candidate for candidate in candidates if getattr(candidate, "direction_family", None) == "bearish"]
    assert len(bearish_candidates) == 1


def test_family_can_emit_zero_candidates_without_filler(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.70))
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "TREND"
    market_data["regime_day"] = "TREND"
    market_data["ltp"] = 25000.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = 0.0
    market_data["ltp_change_10m"] = 0.0
    market_data["rsi_mom"] = 0.0
    market_data["vol_z"] = 0.0

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_zero_family")

    assert candidates == []


def test_all_families_can_fail_and_preserve_no_trade_behavior(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.70))
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="BANKNIFTY")
    market_data["regime"] = "NEUTRAL"
    market_data["regime_day"] = "NEUTRAL"
    market_data["ltp"] = 25000.0
    market_data["vwap"] = 25000.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = 0.0
    market_data["ltp_change_10m"] = 0.0
    market_data["rsi_mom"] = 0.0
    market_data["vol_z"] = 0.0

    candidates = builder._build_nonlive_opportunity_candidates(market_data, ltp=market_data["ltp"], vwap=market_data["vwap"], trigger_reason="unit_test_all_families_fail")

    assert candidates == []


def _make_quick_synth_trade(builder: TradeBuilder, market_data: dict):
    symbol = str(market_data["symbol"])
    opt_type = "CE"
    underlying_spot = 25000.0
    spot_source = "ltp"
    ts = "UNIT"
    expiry_resolved = "2026-02-26"
    step = (getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}).get(symbol, getattr(cfg, "STRIKE_STEP", 50))
    atm_strike = int(round(float(underlying_spot) / step) * step) if step else 0
    contract = builder._resolve_option_contract(symbol, atm_strike, opt_type, expiry_resolved, market_data)
    expiry_resolved = contract.get("expiry") or expiry_resolved
    tradingsymbol = contract.get("tradingsymbol")
    instrument_token = contract.get("instrument_token")
    instrument_id = contract.get("instrument_id")
    instrument_type, _, qty_units, ident_err = builder._identity_fields(symbol, "OPT", expiry_resolved, atm_strike, opt_type, 1)
    assert ident_err is None
    assert tradingsymbol
    assert instrument_id
    min_p, max_p = (getattr(cfg, "PREMIUM_BANDS", {}) or {}).get(
        symbol,
        (getattr(cfg, "MIN_PREMIUM", 40), getattr(cfg, "MAX_PREMIUM", 150)),
    )
    ltp_opt = max(min_p, min(max_p, float(underlying_spot) * 0.004))
    bid = round(ltp_opt * 0.995, 2)
    ask = round(ltp_opt * 1.005, 2)
    mark_price = round((bid + ask) / 2.0, 2)
    synthetic_opt = {
        "bid": bid,
        "ask": ask,
        "ltp": mark_price,
        "last_price": mark_price,
        "quote_ok": True,
        "quote_live": True,
        "volume": 1000,
        "spread_pct": ((ask - bid) / mark_price) if mark_price else None,
    }
    entry_price = ask
    entry_price, entry_condition, entry_ref_price = builder._apply_entry_trigger(entry_price, side="BUY", quick_mode=True)
    option_risk = builder._option_risk_proxy(entry_price, bid, ask)
    stop_loss, target = builder._opt_risk_levels(entry_price, bid, ask, option_risk, stop_mult=1.0, target_mult=1.5)
    intent = builder.trade_intent_flags(market_data, opt={"quote_ok": True}, additional_blockers=[])
    quick_final_gate_threshold = builder._final_confidence_gate_threshold("NEUTRAL", quick_mode=True)
    quick_raw_gate_threshold = builder._raw_confidence_gate_threshold("NEUTRAL", quick_mode=True)
    synthetic_confidence = float(max(0.5, quick_final_gate_threshold))
    return trade_builder_module.Trade(
        trade_id=f"{symbol}-{opt_type}-ATM-QK-{ts}",
        timestamp=trade_builder_module.datetime.now(),
        symbol=symbol,
        instrument="OPT",
        instrument_type=instrument_type,
        right=opt_type,
        instrument_id=instrument_id,
        instrument_token=instrument_token,
        strike=atm_strike,
        expiry=expiry_resolved,
        expiry_date=expiry_resolved,
        tradingsymbol=tradingsymbol,
        option_type=opt_type,
        side="BUY",
        entry_price=round(entry_price, 2),
        stop_loss=round(stop_loss, 2),
        target=round(target, 2),
        qty=1,
        qty_lots=1,
        qty_units=qty_units,
        validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
        capital_at_risk=round(max(entry_price - stop_loss, 0.01), 2),
        expected_slippage=0.0,
        confidence=round(synthetic_confidence, 3),
        strategy="QUICK_SYNTH",
        regime=market_data.get("regime", "NEUTRAL"),
        tier="EXPLORATION",
        day_type=market_data.get("day_type", "UNKNOWN"),
        signal_price=None,
        entry_price_source="ask",
        expected_entry=round(entry_price, 2),
        expected_entry_source="ask",
        **builder._option_liquidity_fields(synthetic_opt),
        entry_condition=entry_condition,
        entry_ref_price=entry_ref_price,
        alpha_confidence=None,
        alpha_uncertainty=None,
        size_mult=1.0,
        tradable=bool(intent["tradable"]),
        tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
        planning_only=bool(intent["planning_only"]),
        execution_allowed=bool(intent["execution_allowed"]),
        reason=intent["execution_reason"],
        source_flags=dict(intent["source_flags"]),
        underlying_spot=underlying_spot,
        spot_source=spot_source,
        option_ltp_source=None,
        chain_source=market_data.get("chain_source") or "synthetic",
        **builder._staged_confidence_payload(
            confidence=synthetic_confidence,
            model_raw=synthetic_confidence,
            model_component=synthetic_confidence,
            micro_blend_method="model_only",
            before_soft_veto=synthetic_confidence,
            after_soft_veto=synthetic_confidence,
            penalty_soft_veto_total=0.0,
            penalty_soft_veto_reasons=[],
            gate_threshold=quick_final_gate_threshold,
            raw_gate_threshold=quick_raw_gate_threshold,
            final_gate_threshold=quick_final_gate_threshold,
            base=synthetic_confidence,
            penalty_total=0.0,
            penalty_reasons=[],
        ),
    )


def _make_equity_fallback_trade(builder: TradeBuilder, market_data: dict):
    symbol = str(market_data["symbol"])
    ltp = float(market_data["ltp"])
    vwap = float(market_data.get("vwap") or ltp)
    direction = "BUY_CALL"
    atr = market_data.get("atr", max(1.0, ltp * 0.002))
    vwap_dist = (ltp - vwap) / vwap if vwap else 0.0
    base_conf = min(0.8, max(0.5, 0.5 + abs(vwap_dist) * 10))
    strat_name = "EQ_TREND"
    side = "BUY" if direction == "BUY_CALL" else "SELL"
    stop_loss = ltp - atr if side == "BUY" else ltp + atr
    target = ltp + atr * 1.5 if side == "BUY" else ltp - atr * 1.5
    instrument_type, instrument_id, qty_units, ident_err = builder._identity_fields(
        symbol,
        "EQ",
        getattr(cfg, "FUT_EXPIRY", ""),
        None,
        None,
        1,
    )
    assert ident_err is None
    intent = builder.trade_intent_flags(
        market_data,
        opt={"quote_ok": bool(market_data.get("quote_ok", True)), "quote_age_sec": market_data.get("quote_age_sec")},
    )
    final_gate_threshold = builder._final_confidence_gate_threshold(market_data.get("regime"), quick_mode=False)
    return trade_builder_module.Trade(
        trade_id=f"{symbol}-FUT-UNIT",
        timestamp=trade_builder_module.datetime.now(),
        symbol=symbol,
        instrument="EQ",
        instrument_type=instrument_type,
        instrument_id=instrument_id,
        instrument_token=None,
        strike=0,
        expiry=str(getattr(cfg, "FUT_EXPIRY", "")),
        side=side,
        entry_price=round(ltp, 2),
        stop_loss=round(stop_loss, 2),
        target=round(target, 2),
        qty=1,
        qty_lots=1,
        qty_units=qty_units,
        validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
        capital_at_risk=round(abs(ltp - stop_loss), 2),
        expected_slippage=0.0,
        confidence=round(base_conf, 3),
        strategy=strat_name,
        regime=market_data.get("regime", "NEUTRAL"),
        tier="MAIN",
        day_type=market_data.get("day_type", "UNKNOWN"),
        alpha_confidence=None,
        alpha_uncertainty=None,
        size_mult=1.0,
        tradable=bool(intent["tradable"]),
        tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
        planning_only=bool(intent["planning_only"]),
        execution_allowed=bool(intent["execution_allowed"]),
        reason=intent["execution_reason"],
        source_flags=dict(intent["source_flags"]),
        **builder._staged_confidence_payload(
            confidence=base_conf,
            model_raw=base_conf,
            model_component=base_conf,
            micro_blend_method="model_only",
            before_soft_veto=base_conf,
            after_soft_veto=base_conf,
            penalty_soft_veto_total=0.0,
            penalty_soft_veto_reasons=[],
            gate_threshold=final_gate_threshold,
            final_gate_threshold=final_gate_threshold,
            base=base_conf,
            penalty_total=0.0,
            penalty_reasons=[],
        ),
    )


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
    assert "premium_out_of_band" not in (trade.source_flags.get("gates_failed") or [])
    assert "premium_out_of_band" not in (trade.source_flags.get("warning_codes") or [])
    assert float(trade.confidence_before_soft_veto) == 0.95
    assert 0.85 <= float(trade.confidence_after_soft_veto) <= 0.89
    assert 0.06 <= float(trade.confidence_penalty_soft_veto_total) <= 0.10
    assert "premium_out_of_band" in list(trade.confidence_penalty_soft_veto_reasons)


def test_stale_quote_survives_as_advisory_gate_without_soft_penalty(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["market_open"] = False
    opt = md["option_chain"][0]
    opt["quote_ts_epoch"] = None
    opt["quote_age_sec"] = 999.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.execution_allowed is False
    assert "stale_option_quote" in (trade.source_flags.get("gates_failed") or [])
    assert "stale_option_quote" not in (trade.source_flags.get("soft_veto_codes") or [])
    assert "stale_option_quote" not in (trade.source_flags.get("warning_codes") or [])
    assert trade.source_flags.get("execution_block_type") == "advisory"
    assert trade.order_policy == "advisory"
    assert trade.order_policy_reason == "data_not_live"


def test_paper_stale_option_tick_survives_as_advisory_gate_without_soft_penalty(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    opt = md["option_chain"][0]
    opt["quote_ts_epoch"] = None
    opt["quote_age_sec"] = 999.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.execution_allowed is False
    assert "stale_option_quote" in (trade.source_flags.get("gates_failed") or [])
    assert "stale_option_quote" not in (trade.source_flags.get("soft_veto_codes") or [])
    assert "stale_option_quote" not in (trade.source_flags.get("warning_codes") or [])


def test_live_market_open_stale_option_tick_remains_rejected(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    opt = md["option_chain"][0]
    opt["quote_ts_epoch"] = None
    opt["quote_age_sec"] = 999.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("STALE_OPTION_TICK", 0)) >= 1


def test_low_volume_becomes_warning_without_duplicate_suppression(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["option_chain"][0]["volume"] = 25

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert "low_volume" in (trade.source_flags.get("warning_codes") or [])
    assert "low_volume" not in (trade.source_flags.get("soft_veto_codes") or [])
    assert "low_volume" not in (trade.source_flags.get("gates_failed") or [])


def test_live_missing_option_bidask_survives_as_non_executable_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_DISPLAY_ONLY_OPTION_CANDIDATES", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["quote_ok"] = True
    md["bid"] = 24999.0
    md["ask"] = 25001.0
    opt = md["option_chain"][0]
    opt["bid"] = None
    opt["ask"] = None
    opt["quote_source"] = "last"
    opt["option_ltp_source"] = "last"
    opt["last_price"] = 100.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.execution_allowed is False
    assert trade.selected_for_execution is False
    assert "option_bidask_missing" in (trade.source_flags.get("gates_failed") or [])


def test_display_only_last_price_candidate_survives_but_is_not_executable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", True, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_DISPLAY_ONLY_OPTION_CANDIDATES", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    opt = md["option_chain"][0]
    opt["bid"] = None
    opt["ask"] = None
    opt["best_bid"] = None
    opt["best_ask"] = None
    opt["depth_ok"] = False
    opt["quote_ok"] = True
    opt["quote_live"] = True
    opt["price_source"] = "last"
    opt["quote_source"] = "last"
    opt["option_ltp_source"] = "last"
    opt["last_price"] = 100.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.execution_allowed is False
    assert trade.selected_for_execution is False
    assert "option_bidask_missing" in (trade.source_flags.get("gates_failed") or [])
    assert "option_depth_missing" in (trade.source_flags.get("warning_codes") or [])
    assert int(builder._last_scan_summary.get("total_candidates") or 0) >= 1
    assert int(builder._last_scan_summary.get("accepted") or 0) >= 1


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
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY", False, raising=False)
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
    assert trade.confidence_penalty_soft_veto_reasons == ["orb_pending", "premium_out_of_band"]


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


def test_planning_fallback_trade_serializes_staged_confidence_fields(tmp_path, monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    market_data = _base_market_data(option_ltp=100.0)
    market_data["option_chain"] = []

    trade = builder._build_planning_no_signal_trade(market_data, ltp=25000.0, vwap=24990.0)

    assert trade is not None
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == "NO_SIGNAL_PLANNING"
    assert row["confidence_model_raw"] == row["builder_confidence"]
    assert row["confidence_after_soft_veto"] == row["builder_confidence"]
    assert row["confidence_final"] == row["gating_final_confidence"]
    assert row["confidence"] == row["confidence_final"]
    assert row["confidence_micro_component"] is None
    assert row["confidence_after_micro"] is None
    assert row["confidence_penalty_soft_veto_total"] == 0.0


def test_quick_synthetic_fallback_serializes_staged_confidence_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.44, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.31, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder, "_decorate_trade_context", lambda trade, *_args, **_kwargs: trade, raising=True)
    monkeypatch.setattr(builder, "_resolve_underlying_spot", lambda *_args, **_kwargs: (25000.0, "ltp", True, None), raising=True)
    monkeypatch.setattr(
        builder,
        "_resolve_option_contract",
        lambda symbol, strike, opt_type, expiry, market_data: {
            "expiry": expiry or "2026-02-26",
            "tradingsymbol": f"{symbol}{strike}{opt_type}",
            "instrument_token": 123456,
            "instrument_id": build_id(symbol, expiry or "2026-02-26", strike, opt_type),
        },
        raising=True,
    )
    monkeypatch.setattr(builder.execution, "estimate_slippage", lambda *_args, **_kwargs: 0.0, raising=False)

    market_data = _base_market_data(option_ltp=100.0)
    market_data["option_chain"] = []
    market_data["chain_source"] = "live"

    trade = _make_quick_synth_trade(builder, market_data)

    assert trade is not None
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == "QUICK_SYNTH"
    assert row["confidence_model_raw"] == trade.confidence_model_raw
    assert row["confidence_micro_blend_method"] == "model_only"
    assert row["confidence_raw_gate_threshold"] == 0.35
    assert abs(float(row["confidence_final_gate_threshold"]) - 0.31) < 0.011


def test_equity_fallback_trade_serializes_staged_confidence_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "ENABLE_EQUITIES", True, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.30, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)
    monkeypatch.setattr(builder, "_decorate_trade_context", lambda trade, *_args, **_kwargs: trade, raising=True)

    market_data = _base_market_data(option_ltp=100.0)
    market_data["instrument"] = "EQ"
    market_data["option_chain"] = []

    trade = _make_equity_fallback_trade(builder, market_data)

    assert trade is not None
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == "EQ_TREND"
    assert row["confidence_model_raw"] == trade.confidence_model_raw
    assert row["confidence_after_alpha"] is None
    assert row["confidence_final_gate_threshold"] == 0.30
    assert row["confidence_penalty_total"] == 0.0


def test_main_path_trade_serializes_staged_confidence_fields(tmp_path, monkeypatch):
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
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == trade.strategy
    assert row["confidence_model_raw"] == 0.52
    assert row["confidence_after_soft_veto"] == trade.confidence_after_soft_veto
    assert row["confidence_raw_gate_threshold"] == 0.44
    assert abs(float(row["confidence_final_gate_threshold"]) - 0.31) < 0.011


def test_no_signal_sim_uses_fallback_signal(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "NO_SIGNAL_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder, "_signal_for_symbol", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(
        builder,
        "_quick_neutral_fallback_signal",
        lambda *_args, **_kwargs: {
            "direction": "BUY_CALL",
            "reason": "unit_test_no_signal_fallback",
            "score": 0.4,
        },
        raising=True,
    )
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=True, allow_baseline=False)

    assert trade is not None
    assert str((builder._reject_ctx or {}).get("reason") or "") != "no_signal"


def test_live_offhours_no_signal_does_not_use_planning_fallback(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)

    builder = TradeBuilder()
    monkeypatch.setattr(builder, "_signal_for_symbol", lambda *_args, **_kwargs: None, raising=True)
    called = {"hit": False}

    def _boom(*_args, **_kwargs):
        called["hit"] = True
        raise AssertionError("planning fallback should not run in LIVE")

    monkeypatch.setattr(builder, "_build_planning_no_signal_trade", _boom, raising=True)

    market_data = _base_market_data(option_ltp=100.0)
    market_data["market_open"] = False
    market_data["market_context"] = {"execution_mode": "LIVE", "market_open": False}
    market_data["allow_planning_no_signal_fallback"] = True

    trade = builder.build(market_data, quick_mode=False, allow_fallbacks=True, allow_baseline=False)

    assert trade is None
    assert called["hit"] is False


@pytest.mark.parametrize(
    ("symbol", "expected_strategy", "signal_setup"),
    [
        ("NIFTY", "OPP_DIRECTIONAL", lambda monkeypatch: monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)),
        ("BANKNIFTY", "OPP_MEAN_REVERT", lambda monkeypatch: monkeypatch.setattr(trade_builder_module, "mean_reversion_signal", lambda *_args, **_kwargs: _signal("BUY_PUT"), raising=True)),
        ("SENSEX", "OPP_VOL_EXPANSION", lambda monkeypatch: monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)),
    ],
)
def test_nonlive_opportunity_candidates_vary_by_signal_family(monkeypatch, symbol, expected_strategy, signal_setup):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder()
    _disable_opportunity_signals(monkeypatch)
    signal_setup(monkeypatch)

    market_data = _opportunity_market_data(symbol=symbol)
    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=float(market_data["ltp"]),
        vwap=float(market_data["vwap"]),
        trigger_reason="unit_test",
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.symbol == symbol
    assert candidate.strategy == expected_strategy
    assert bool(candidate.planning_only) is True
    assert bool(candidate.execution_allowed) is False
    score_breakdown = dict(candidate.score_breakdown or {})
    assert float(score_breakdown.get("candidate_quality_score") or 0.0) > 0.0
    assert float(score_breakdown.get("execution_feasibility_score") or 0.0) > 0.0
    assert float(score_breakdown.get("ranking_score") or 0.0) > 0.0
    assert float(candidate.rank_score or 0.0) <= float(score_breakdown["candidate_quality_score"])


def test_directional_signal_strength_increases_candidate_quality(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder()
    _disable_opportunity_signals(monkeypatch)

    weak_market = _opportunity_market_data(symbol="NIFTY")
    weak_market["vwap"] = 24978.0

    strong_market = _opportunity_market_data(symbol="NIFTY")
    strong_market["vwap"] = 24955.0

    weak_candidates = builder._build_nonlive_opportunity_candidates(
        weak_market,
        ltp=float(weak_market["ltp"]),
        vwap=float(weak_market["vwap"]),
        trigger_reason="unit_test",
    )
    strong_candidates = builder._build_nonlive_opportunity_candidates(
        strong_market,
        ltp=float(strong_market["ltp"]),
        vwap=float(strong_market["vwap"]),
        trigger_reason="unit_test",
    )

    weak_directional = next(candidate for candidate in weak_candidates if candidate.strategy == "OPP_DIRECTIONAL")
    strong_directional = next(candidate for candidate in strong_candidates if candidate.strategy == "OPP_DIRECTIONAL")

    weak_breakout_strength = float((weak_directional.score_breakdown or {}).get("breakout_strength") or 0.0)
    strong_breakout_strength = float((strong_directional.score_breakdown or {}).get("breakout_strength") or 0.0)
    weak_quality = float((weak_directional.score_breakdown or {}).get("candidate_quality_score") or 0.0)
    strong_quality = float((strong_directional.score_breakdown or {}).get("candidate_quality_score") or 0.0)

    assert weak_breakout_strength >= 1.0
    assert strong_breakout_strength > weak_breakout_strength
    assert strong_quality > weak_quality
    assert float(strong_directional.rank_score or 0.0) <= strong_quality


def test_nonlive_fallback_context_allows_bounded_signal_activation(monkeypatch, caplog):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_FALLBACK_SIGNAL_STRENGTH_MIN", 0.75, raising=False)
    builder = TradeBuilder()
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["vwap"] = market_data["ltp"]
    market_data["atr"] = 25.0
    market_data["ltp_change_window"] = 0.10
    market_data["ltp_change_5m"] = 0.0
    market_data["ltp_change_10m"] = 0.0
    market_data["rsi_mom"] = 0.0
    market_data["vol_z"] = 0.0
    market_data["nonlive_feature_fallback"] = True
    market_data["nonlive_feature_fallback_fields"] = ["atr", "ltp_change_window"]

    caplog.set_level(logging.INFO)
    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=float(market_data["ltp"]),
        vwap=float(market_data["vwap"]),
        trigger_reason="fallback_unit_test",
    )

    assert len(candidates) >= 1
    assert any(candidate.strategy == "OPP_DIRECTIONAL" for candidate in candidates)
    assert "SIGNAL_EVAL_SUMMARY" in caplog.text
    assert "OPPORTUNITY_SET_BUILT" in caplog.text


def test_nonlive_fallback_context_without_basis_does_not_create_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_FALLBACK_SIGNAL_STRENGTH_MIN", 0.75, raising=False)
    builder = TradeBuilder()
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["vwap"] = market_data["ltp"]
    market_data["atr"] = 25.0
    market_data["ltp_change_window"] = 0.0
    market_data["ltp_change_5m"] = 0.0
    market_data["ltp_change_10m"] = 0.0
    market_data["rsi_mom"] = 0.0
    market_data["vol_z"] = 0.0
    market_data["nonlive_feature_fallback"] = True
    market_data["nonlive_feature_fallback_fields"] = ["atr"]

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=float(market_data["ltp"]),
        vwap=float(market_data["vwap"]),
        trigger_reason="fallback_unit_test",
    )

    assert candidates == []


def test_build_with_trace_does_not_invent_opportunity_without_signal_basis(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "NO_SIGNAL_FALLBACK_ENABLE", False, raising=False)

    builder = TradeBuilder()
    monkeypatch.setattr(builder, "_signal_for_symbol", lambda *_args, **_kwargs: None, raising=True)
    monkeypatch.setattr(builder, "_quick_neutral_fallback_signal", lambda *_args, **_kwargs: None, raising=True)
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["allow_planning_no_signal_fallback"] = True

    trade, _trace = builder.build_with_trace(
        market_data,
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None


def test_candidate_separates_setup_trigger_and_entry_quality(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder()
    _disable_opportunity_signals(monkeypatch)
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["minutes_since_open"] = 10
    market_data["minutes_to_close"] = 300
    market_data["vwap"] = 24970.0
    market_data["ltp_change_window"] = 35.0
    market_data["ltp_change_5m"] = 18.0
    market_data["ltp_change_10m"] = 28.0
    market_data["rsi_mom"] = 0.25
    market_data["vol_z"] = 0.8

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=float(market_data["ltp"]),
        vwap=float(market_data["vwap"]),
        trigger_reason="unit_test_setup_trigger_entry",
    )

    directional = next(candidate for candidate in candidates if candidate.strategy == "OPP_DIRECTIONAL")
    assert directional.setup_score is not None
    assert directional.trigger_score is not None
    assert directional.entry_quality_score is not None
    assert directional.entry_quality_reason is not None
    assert len({round(float(directional.setup_score), 4), round(float(directional.trigger_score), 4), round(float(directional.entry_quality_score), 4)}) >= 2


def test_overextended_entry_is_penalized_or_rejected(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder()
    _disable_opportunity_signals(monkeypatch)
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["minutes_since_open"] = 25
    market_data["minutes_to_close"] = 280
    market_data["atr"] = 40.0
    market_data["vwap"] = 24750.0
    market_data["ltp_change_window"] = 180.0
    market_data["ltp_change_5m"] = 90.0
    market_data["ltp_change_10m"] = 130.0
    market_data["vol_z"] = 1.4

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=float(market_data["ltp"]),
        vwap=float(market_data["vwap"]),
        trigger_reason="unit_test_overextended",
    )

    directional = next((candidate for candidate in candidates if candidate.strategy == "OPP_DIRECTIONAL"), None)
    assert directional is None or (
        float(directional.overextension_penalty or 0.0) > 0.5
        and (
            directional.entry_quality_reason == "overextended_entry"
            or directional.execution_allowed is False
        )
    )


def test_midday_breakout_requires_stronger_trigger(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "SESSION_MIDDAY_DIRECTIONAL_TRIGGER_MIN", 0.80, raising=False)
    builder = TradeBuilder()
    _disable_opportunity_signals(monkeypatch)

    opening = _opportunity_market_data(symbol="NIFTY")
    opening["minutes_since_open"] = 10
    opening["minutes_to_close"] = 320
    opening["vwap"] = 24998.0
    opening["ltp_change_window"] = 0.25
    opening["ltp_change_5m"] = 0.05
    opening["ltp_change_10m"] = 0.1

    midday = _opportunity_market_data(symbol="NIFTY")
    midday["minutes_since_open"] = 150
    midday["minutes_to_close"] = 180
    midday["vwap"] = 24998.0
    midday["ltp_change_window"] = 0.25
    midday["ltp_change_5m"] = 0.05
    midday["ltp_change_10m"] = 0.1

    opening_candidates = builder._build_nonlive_opportunity_candidates(
        opening,
        ltp=float(opening["ltp"]),
        vwap=float(opening["vwap"]),
        trigger_reason="unit_test_opening_breakout",
    )
    midday_candidates = builder._build_nonlive_opportunity_candidates(
        midday,
        ltp=float(midday["ltp"]),
        vwap=float(midday["vwap"]),
        trigger_reason="unit_test_midday_breakout",
    )

    opening_directional = next(candidate for candidate in opening_candidates if candidate.strategy == "OPP_DIRECTIONAL")
    midday_directional = next(candidate for candidate in midday_candidates if candidate.strategy == "OPP_DIRECTIONAL")

    assert float(midday_directional.trigger_score or 0.0) < float(opening_directional.trigger_score or 0.0)
    assert (
        midday_directional.entry_quality_reason == "midday_trigger_too_weak"
        or float(midday_directional.trigger_score or 0.0) < float(getattr(cfg, "SESSION_MIDDAY_DIRECTIONAL_TRIGGER_MIN", 0.80))
    )
    assert midday_directional.execution_allowed is False or midday_directional.candidate_status != "executable"


def test_flashy_signal_cannot_survive_without_consensus(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "NONLIVE_EXECUTABLE_MIN_FAMILY_SURVIVAL", 0.70, raising=False)
    builder = TradeBuilder()
    _disable_opportunity_signals(monkeypatch)

    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["regime"] = "RANGE"
    market_data["regime_day"] = "RANGE"
    market_data["day_type"] = "RANGE_DAY"
    market_data["minutes_since_open"] = 140
    market_data["minutes_to_close"] = 170
    market_data["atr"] = 25.0
    market_data["vwap"] = 24860.0
    market_data["ltp_change_window"] = 85.0
    market_data["ltp_change_5m"] = 45.0
    market_data["ltp_change_10m"] = 55.0
    market_data["vol_z"] = 1.2
    market_data["data_confidence"] = 0.25
    market_data["quote_ok"] = False

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=float(market_data["ltp"]),
        vwap=float(market_data["vwap"]),
        trigger_reason="unit_test_flashy_without_consensus",
    )

    directional = next(candidate for candidate in candidates if candidate.strategy == "OPP_DIRECTIONAL")
    assert float(directional.trigger_score or 0.0) > float(directional.setup_score or 0.0)
    assert float(directional.family_survival_score or 0.0) < float(getattr(cfg, "NONLIVE_EXECUTABLE_MIN_FAMILY_SURVIVAL", 0.55))
    assert directional.execution_allowed is False
    assert list(getattr(builder, "_last_ranked_candidates", []) or []) == []


def test_sim_relaxes_basic_filters(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.03, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)
    monkeypatch.setattr(cfg, "MIN_OI", 1000, raising=False)
    monkeypatch.setattr(cfg, "DELTA_MIN", 0.25, raising=False)
    monkeypatch.setattr(cfg, "DELTA_MAX", 0.7, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    market_data = _base_market_data(option_ltp=100.0)
    opt = market_data["option_chain"][0]
    opt["volume"] = 1
    opt["oi"] = 1
    opt["delta"] = 0.1
    opt["bid"] = 90.0
    opt["ask"] = 110.0
    opt["spread_pct"] = 0.2

    trade = builder.build(market_data, quick_mode=False, allow_fallbacks=True, allow_baseline=False)

    assert trade is not None


def test_live_does_not_relax_basic_filters(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.03, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)
    monkeypatch.setattr(cfg, "MIN_OI", 1000, raising=False)
    monkeypatch.setattr(cfg, "DELTA_MIN", 0.25, raising=False)
    monkeypatch.setattr(cfg, "DELTA_MAX", 0.7, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    market_data = _base_market_data(option_ltp=100.0)
    opt = market_data["option_chain"][0]
    opt["volume"] = 1
    opt["oi"] = 1
    opt["delta"] = 0.1
    opt["bid"] = 90.0
    opt["ask"] = 110.0
    opt["spread_pct"] = 0.2

    trade = builder.build(market_data, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None


def test_option_scan_reject_summary_log(monkeypatch, caplog):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    market_data = _base_market_data(option_ltp=100.0)
    market_data["option_chain"] = [
        {"type": "CE", "strike": 25000, "bid": 99, "ask": 101}
    ]

    caplog.set_level(logging.INFO)
    trade = builder.build(market_data, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert "OPTION_SCAN_REJECT_SUMMARY" in caplog.text


def test_no_candidates_survived_emits_reject_wall_logs(monkeypatch, caplog):
    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    def _fake_signal(*_args, **_kwargs):
        return {
            "direction": "BUY_CALL",
            "confidence": 0.55,
            "score": 0.9,
            "regime_day": "TREND",
            "reason": "test_signal",
        }

    def _fake_chain_rows(*_args, **_kwargs):
        return [{"type": "CE", "strike": 25000}]

    def _fake_normalize(_raw, _opt_type):
        return None, "type_mismatch"

    def _fake_select(*_args, **_kwargs):
        return None, []

    monkeypatch.setattr(builder, "_signal_for_symbol", _fake_signal, raising=True)
    monkeypatch.setattr(builder, "_annotate_candidate_chain_rows", _fake_chain_rows, raising=True)
    monkeypatch.setattr(builder, "_normalize_option_row", _fake_normalize, raising=True)
    monkeypatch.setattr(trade_builder_module, "select_best_opportunity", _fake_select, raising=True)

    caplog.set_level(logging.INFO)
    trade = builder.build(
        {
            "symbol": "NIFTY",
            "market_open": True,
            "valid": True,
            "ltp": 25000.0,
            "vwap": 24990.0,
            "instrument": "OPT",
            "chain_source": "live",
            "quote_ok": True,
            "bid": 24999.0,
            "ask": 25001.0,
            "regime": "TREND",
        },
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None
    assert "OPTION_SCAN_REJECT_SUMMARY symbol=NIFTY" in caplog.text
    assert "NO_CANDIDATE_PATH symbol=NIFTY" in caplog.text


def test_build_with_trace_softens_no_candidates_survived_in_sim(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    def _fake_signal(*_args, **_kwargs):
        return {
            "direction": "BUY_CALL",
            "confidence": 0.55,
            "score": 0.9,
            "regime_day": "TREND",
            "reason": "test_signal",
        }

    def _fake_chain_rows(*_args, **_kwargs):
        return [{"type": "CE", "strike": 25000}]

    def _fake_normalize(_raw, _opt_type):
        return None, "type_mismatch"

    def _fake_select(*_args, **_kwargs):
        return None, []

    monkeypatch.setattr(builder, "_signal_for_symbol", _fake_signal, raising=True)
    monkeypatch.setattr(builder, "_annotate_candidate_chain_rows", _fake_chain_rows, raising=True)
    monkeypatch.setattr(builder, "_normalize_option_row", _fake_normalize, raising=True)
    monkeypatch.setattr(trade_builder_module, "select_best_opportunity", _fake_select, raising=True)
    _disable_opportunity_signals(monkeypatch)
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)

    trade, _trace = builder.build_with_trace(
        {
            "symbol": "NIFTY",
            "market_open": True,
            "valid": True,
            "ltp": 25000.0,
            "vwap": 24990.0,
            "instrument": "OPT",
            "chain_source": "live",
            "quote_ok": True,
            "bid": 24999.0,
            "ask": 25001.0,
            "regime": "TREND",
            "atr": 50.0,
            "option_chain": _opportunity_market_data(symbol="NIFTY")["option_chain"],
        },
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    assert trade.symbol == "NIFTY"
    assert trade.strategy == "OPP_DIRECTIONAL"
    assert bool(trade.planning_only) is True
    assert bool(trade.execution_allowed) is False
    ranked = list(getattr(builder, "_last_ranked_candidates", []) or [])
    assert len(ranked) >= 1
    ranked_strategies = {str(row.get("strategy") or "") for row in ranked if isinstance(row, dict)}
    assert "OPP_DIRECTIONAL" in ranked_strategies
    assert float((trade.score_breakdown or {}).get("candidate_quality_score") or 0.0) > 0.0
    assert float((trade.score_breakdown or {}).get("execution_feasibility_score") or 0.0) > 0.0


def test_candidate_rejection_records_stage_and_reason(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / ".runtime"), raising=False)
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / ".runtime"))
    monkeypatch.setattr(cfg, "OFFLINE_THRESHOLD_AUDIT_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _disable_opportunity_signals(monkeypatch)
    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["minutes_since_open"] = 150
    market_data["minutes_to_close"] = 180
    market_data["vwap"] = 24998.0
    market_data["ltp_change_window"] = 0.25
    market_data["ltp_change_5m"] = 0.05
    market_data["ltp_change_10m"] = 0.1
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)

    candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=float(market_data["ltp"]),
        vwap=float(market_data["vwap"]),
        trigger_reason="unit_test_rejection_record",
    )

    directional = next(candidate for candidate in candidates if candidate.strategy == "OPP_DIRECTIONAL")
    assert directional.execution_allowed is False
    records = load_candidate_decisions(path=tmp_path / ".runtime" / "analytics" / "candidate_decisions.jsonl")
    builder_record = next(
        row for row in records
        if row["decision_phase"] == "builder" and row["trade_id"] == directional.trade_id
    )

    assert builder_record["rejected_at_stage"] in {"trigger", "entry_quality", "risk_budget"}
    assert builder_record["rejection_reason_code"] is not None
    assert builder_record["strategy_family"] == "continuation"
    assert builder_record["direction_family"] == "bullish"
    assert builder_record["session_mode"] == directional.session_mode
    assert builder_record["strategy_regime_mode"] in {"TRENDING", "UNCERTAIN"}
    assert float(builder_record["setup_score"] or 0.0) >= 0.0
    assert float(builder_record["trigger_score"] or 0.0) >= 0.0
    assert float(builder_record["entry_quality_score"] or 0.0) >= 0.0
    assert float(builder_record["family_survival_score"] or 0.0) >= 0.0


def test_builder_reads_session_policy_without_behavior_change(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _disable_opportunity_signals(monkeypatch)
    market_data = _opportunity_market_data(symbol="NIFTY")
    market_data["minutes_since_open"] = 150
    market_data["minutes_to_close"] = 180
    market_data["vwap"] = 24998.0
    market_data["ltp_change_window"] = 0.25
    market_data["ltp_change_5m"] = 0.05
    market_data["ltp_change_10m"] = 0.1
    monkeypatch.setattr(trade_builder_module, "ensemble_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)
    monkeypatch.setattr(trade_builder_module, "event_breakout_signal", lambda *_args, **_kwargs: _signal("BUY_CALL"), raising=True)

    baseline_candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=float(market_data["ltp"]),
        vwap=float(market_data["vwap"]),
        trigger_reason="unit_test_session_policy_baseline",
    )
    baseline_directional = next(candidate for candidate in baseline_candidates if candidate.strategy == "OPP_DIRECTIONAL")

    original = cfg.get_session_policy

    def _wrapped_policy(session_mode=None):
        policy = dict(original(session_mode))
        policy["policy_source"] = "test_session_policy"
        return policy

    monkeypatch.setattr(cfg, "get_session_policy", _wrapped_policy, raising=True)
    patched_candidates = builder._build_nonlive_opportunity_candidates(
        market_data,
        ltp=float(market_data["ltp"]),
        vwap=float(market_data["vwap"]),
        trigger_reason="unit_test_session_policy_wrapped",
    )
    patched_directional = next(candidate for candidate in patched_candidates if candidate.strategy == "OPP_DIRECTIONAL")

    assert patched_directional.session_mode == baseline_directional.session_mode
    assert patched_directional.execution_allowed == baseline_directional.execution_allowed
    assert patched_directional.effective_session_policy["policy_source"] == "test_session_policy"
