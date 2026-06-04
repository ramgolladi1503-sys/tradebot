from __future__ import annotations

from types import SimpleNamespace

import pytest

from config import config as cfg
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.95


def _field(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _source_flags(obj):
    flags = _field(obj, "source_flags", {}) or {}
    return dict(flags) if isinstance(flags, dict) else {}


def _assert_real_candidate(candidate) -> None:
    flags = _source_flags(candidate)
    assert _field(candidate, "symbol") == "NIFTY"
    assert _field(candidate, "tradingsymbol")
    assert _field(candidate, "instrument_token") is not None
    assert str(_field(candidate, "strategy_family") or "").strip()
    assert str(_field(candidate, "strategy_family") or "").strip().lower() not in {
        "synthetic_advisory",
        "builder_soft_reject",
        "fallback",
    }
    assert str(_field(candidate, "candidate_status") or "").strip().lower() not in {
        "advisory_only",
        "builder_soft_reject",
        "fallback",
    }
    assert str(_field(candidate, "execution_status") or "").strip().lower() not in {
        "advisory_only",
        "queue_only",
        "blocked",
        "rejected",
    }
    assert str(_field(candidate, "candidate_class") or "").strip().upper() == "EXECUTABLE"
    assert str(_field(candidate, "candidate_status") or "").strip().lower() == "executable"
    assert str(_field(candidate, "permission") or "").strip().upper() == "EXECUTE"
    assert bool(_field(candidate, "tradable")) is True
    assert str(_field(candidate, "execution_entry_status") or "").strip().lower() == "executable"
    assert _field(candidate, "rank_score") is not None
    assert _field(candidate, "confidence") is not None
    assert _field(candidate, "quote_source") not in {None, "", "unknown"}
    assert _field(candidate, "quote_age_sec") is not None
    assert any(
        _field(candidate, key) is not None
        for key in ("spread_pct", "spread", "bid", "ask", "best_bid", "best_ask")
    )
    assert bool(_field(candidate, "liquidity_ok", True)) is True or _field(candidate, "liquidity_score") is not None or bool(_field(candidate, "liquidity")) is True
    origin = flags.get("candidate_origin")
    if isinstance(origin, dict):
        origin_text = " ".join(str(value) for value in origin.values()).lower()
        assert "softened_builder_path" not in origin_text
        assert "fallback" not in origin_text
        assert "synthetic" not in origin_text
        assert "advisory" not in origin_text
    else:
        origin_text = str(origin or "").lower()
        assert "softened_builder_path" not in origin_text
        assert "fallback" not in origin_text
        assert "synthetic" not in origin_text
        assert "advisory" not in origin_text


def _clean_live_option_row() -> dict:
    return {
        "type": "CE",
        "strike": 25000,
        "expiry": "2099-03-26",
        "tradingsymbol": "NIFTY2099032625000CE",
        "instrument_token": 987654,
        "ltp": 100.0,
        "bid": 99.5,
        "ask": 100.5,
        "quote_ok": True,
        "quote_live": True,
        "quote_age_sec": 1.0,
        "quote_ts_epoch": 4102444800.0,
        "quote_source": "option_chain_live",
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


def _clean_live_market_data(option_row: dict | None = None) -> dict:
    row = dict(option_row or _clean_live_option_row())
    return {
        "symbol": "NIFTY",
        "market_open": True,
        "valid": True,
        "execution_mode": "LIVE",
        "market_context": {"execution_mode": "LIVE", "market_open": True, "mode": "LIVE"},
        "ltp": 25000.0,
        "bid": 24999.0,
        "ask": 25001.0,
        "ltp_source": "live",
        "quote_ok": True,
        "quote_live": True,
        "quote_age_sec": 1.0,
        "chain_source": "live",
        "option_chain_source": "live",
        "option_chain": [row],
        "vwap": 24990.0,
        "atr": 20.0,
        "bias": "Bullish",
        "instrument": "OPT",
        "regime": "TREND",
        "regime_day": "TREND",
        "day_type": "TREND_DAY",
        "htf_dir": "UP",
        "orb_bias": "UP",
    }


def _prepared_builder(monkeypatch) -> TradeBuilder:
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ALPHA_ENSEMBLE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_AB_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_USE_ONLY_WITH_HISTORY", False, raising=False)
    monkeypatch.setattr(cfg, "ML_MIN_PROBA", 0.1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 1.0, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)
    monkeypatch.setattr(cfg, "MIN_RR", 0.1, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "NO_SIGNAL_FALLBACK_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "PLANNING_NO_SIGNAL_FALLBACK_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_STRIKE_LADDER_WIDTH", 0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_EXPIRY_BUCKET_MODE", "SAME", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ENFORCE_STRIKE_LADDER", True, raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    builder = TradeBuilder(predictor=_PredictorStub())
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda _md, force_family=None: {
            "direction": "BUY_CALL",
            "reason": "real_candidate_supply_contract",
            "score": 0.95,
            "regime_day": "TREND",
        },
        raising=True,
    )
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"), raising=True)
    monkeypatch.setattr(builder, "_apply_decay_gate", lambda _strategy_name, base_score=None, size_mult=1.0: (True, base_score, size_mult, None), raising=True)
    monkeypatch.setattr(builder, "_validate_ml_features", lambda _feats: (True, "ok"), raising=True)
    monkeypatch.setattr(
        trade_builder_module,
        "compute_trade_score",
        lambda *args, **kwargs: {"score": 100.0, "alignment": 1.0},
        raising=True,
    )
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)
    return builder


def _prepare_live_candidate(builder: TradeBuilder, market_data: dict, monkeypatch):
    monkeypatch.setattr(builder.execution, "spread_ok", lambda *_args, **_kwargs: True, raising=False)
    monkeypatch.setattr(builder.execution, "estimate_slippage", lambda *_args, **_kwargs: 0.0, raising=True)
    return builder.build(
        market_data,
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )


def test_live_strong_signal_valid_option_row_reaches_ranked_candidate_pool(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    trade = _prepare_live_candidate(builder, _clean_live_market_data(), monkeypatch)

    assert trade is not None
    assert len(builder._last_ranked_candidates) >= 1
    ranked = builder._last_ranked_candidates[0]
    _assert_real_candidate(ranked)
    assert _field(trade, "advisory_only", False) is False
    assert _field(trade, "queue_only", False) is False
    assert _field(trade, "tradingsymbol")
    assert _field(trade, "instrument_token") is not None
    assert _field(trade, "strike") == 25000
    assert _field(trade, "expiry")
    flags = _source_flags(trade)
    origin = flags.get("candidate_origin")
    if isinstance(origin, dict):
        origin_text = " ".join(str(value) for value in origin.values()).lower()
        assert "softened_builder_path" not in origin_text
        assert "fallback" not in origin_text
        assert "synthetic" not in origin_text


def test_live_no_signal_with_fallbacks_disabled_does_not_create_ranked_candidate(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda _md, force_family=None: None,
        raising=True,
    )

    trade = builder.build(
        _clean_live_market_data(),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None or not bool(_field(trade, "execution_allowed", False))
    assert list(getattr(builder, "_last_ranked_candidates", []) or []) == []


def test_live_missing_bid_ask_does_not_reach_real_candidate_pool(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    market_data = _clean_live_market_data()
    market_data["option_chain"][0]["bid"] = None
    market_data["option_chain"][0]["ask"] = None

    trade = builder.build(
        market_data,
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    ranked = list(getattr(builder, "_last_ranked_candidates", []) or [])
    if trade is not None:
        assert bool(_field(trade, "execution_allowed", False)) is False
        assert str(_field(trade, "execution_status") or "").strip().lower() != "executable"
    assert all(bool(_field(candidate, "execution_allowed", False)) is False for candidate in ranked)


def test_real_candidate_contract_has_no_broker_or_runtime_side_effects(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    calls: list[str] = []

    for name in ("place_order", "modify_order", "cancel_order", "exit_order"):
        monkeypatch.setattr(trade_builder_module, name, lambda *args, _name=name, **kwargs: calls.append(_name), raising=False)

    trade = _prepare_live_candidate(builder, _clean_live_market_data(), monkeypatch)

    assert trade is not None
    assert calls == []
