from __future__ import annotations

import strategies.trade_builder as trade_builder_module
from config import config as cfg
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.95


def _prepared_builder(monkeypatch) -> TradeBuilder:
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ALPHA_ENSEMBLE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_AB_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_USE_ONLY_WITH_HISTORY", False, raising=False)
    monkeypatch.setattr(cfg, "ML_MIN_PROBA", 0.1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 1.0, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)
    monkeypatch.setattr(cfg, "MIN_RR", 0.1, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
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
    monkeypatch.setattr(builder.execution, "spread_ok", lambda *_args, **_kwargs: True, raising=False)
    monkeypatch.setattr(builder.execution, "estimate_slippage", lambda *_args, **_kwargs: 0.0, raising=True)
    return builder


def _field(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _source_flags(obj) -> dict:
    flags = _field(obj, "source_flags", {}) or {}
    return flags if isinstance(flags, dict) else {}


def _list_field(obj, key) -> list[str]:
    value = _field(obj, key, []) or []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _option_row(**overrides) -> dict:
    base = {
        "type": "CE",
        "strike": 25000.0,
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
    base.update(overrides)
    return base


def test_legacy_trade_builder_row_cannot_bypass_canonical_ranking(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    trade = builder.build(
        {
            "symbol": "NIFTY",
            "market_open": True,
            "valid": True,
            "execution_mode": "PAPER",
            "market_context": {"execution_mode": "PAPER", "market_open": True, "mode": "PAPER"},
            "ltp": 25000.0,
            "vwap": 24990.0,
            "atr": 20.0,
            "bias": "Bullish",
            "instrument": "OPT",
            "chain_source": "live",
            "quote_ok": True,
            "bid": 24999.0,
            "ask": 25001.0,
            "regime": "TREND",
            "regime_day": "TREND",
            "day_type": "TREND_DAY",
            "htf_dir": "UP",
            "orb_bias": "UP",
            "option_chain": [
                _option_row(bid=None, ask=None, quote_ok=False),
            ],
        },
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    ranked = list(getattr(builder, "_last_ranked_candidates", []) or [])
    assert trade is not None
    assert ranked
    assert all(bool(row.get("execution_allowed", False)) is False for row in ranked)
    assert all(str(row.get("candidate_origin") or "") == "dirty_option_bridge" for row in ranked)
    assert any(str(row.get("execution_block_reason") or "") == "no_quote" for row in ranked)
    assert all(str(row.get("candidate_status") or "") == "advisory_only" for row in ranked)


def test_wide_spread_trade_builder_row_is_ranked_but_not_executable(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    trade = builder.build(
        {
            "symbol": "NIFTY",
            "market_open": True,
            "valid": True,
            "execution_mode": "PAPER",
            "market_context": {"execution_mode": "PAPER", "market_open": True, "mode": "PAPER"},
            "ltp": 25000.0,
            "vwap": 24990.0,
            "atr": 20.0,
            "bias": "Bullish",
            "instrument": "OPT",
            "chain_source": "live",
            "quote_ok": True,
            "bid": 24999.0,
            "ask": 25001.0,
            "regime": "TREND",
            "regime_day": "TREND",
            "day_type": "TREND_DAY",
            "htf_dir": "UP",
            "orb_bias": "UP",
            "option_chain": [
                _option_row(bid=10.0, ask=18.0, quote_ok=True),
            ],
        },
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    ranked = list(getattr(builder, "_last_ranked_candidates", []) or [])
    assert trade is not None
    assert ranked
    assert any(
        (_field(row, "dirty_option_reason") or _source_flags(row).get("dirty_option_reason")) == "spread_pct"
        for row in ranked
    )
    spread_blocked_rows = [
        row
        for row in ranked
        if "spread_pct" in _list_field(row, "tradable_reasons_blocking")
        or "spread_pct" in _list_field(row, "gate_reasons")
        or "spread_pct" in _list_field(row, "hard_blockers")
    ]
    assert spread_blocked_rows
    assert all(_field(row, "execution_allowed", False) is False for row in spread_blocked_rows)
    assert all(_field(row, "tradable", False) is False for row in spread_blocked_rows)
