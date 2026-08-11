from __future__ import annotations

import strategies.trade_builder as trade_builder_module
from config import config as cfg
from core.runtime_authority_cutover import apply_runtime_authority
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


def _source_flags(obj) -> dict:
    flags = _field(obj, "source_flags", {}) or {}
    return flags if isinstance(flags, dict) else {}


def _list_field(obj, key) -> list[str]:
    value = _field(obj, key, []) or []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


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


def _market_data(option_row: dict) -> dict:
    return {
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
        "option_chain": [option_row],
    }


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


def _assert_dirty_candidate(candidate, reason: str) -> None:
    flags = _source_flags(candidate)
    assert candidate is not None
    assert _field(candidate, "candidate_origin") == "dirty_option_bridge"
    assert (_field(candidate, "dirty_option_reason") or flags.get("dirty_option_reason")) == reason
    assert _field(candidate, "primary_blocker") == reason
    assert _field(candidate, "execution_block_reason") == reason
    assert reason in _list_field(candidate, "gate_reasons")
    assert reason in _list_field(candidate, "tradable_reasons_blocking")
    # This object is the builder-internal candidate before the runtime-authority
    # cutover, so preserve its lifecycle label while proving it cannot execute.
    assert _field(candidate, "candidate_status") == "advisory_only"
    assert _field(candidate, "execution_status") == "advisory_only"
    assert _field(candidate, "execution_allowed") is False
    assert _field(candidate, "execution_ok") is False
    assert _field(candidate, "tradable") is False

    # Canonical execution truth is applied at the authority boundary. The same
    # dirty candidate must become explicitly not_executable there.
    canonical = apply_runtime_authority(candidate, mode="PAPER")
    assert _field(canonical, "execution_status") == "not_executable"
    assert _field(canonical, "execution_allowed") is False


def test_dirty_option_rows_are_preserved_into_ranked_advisory_candidates(monkeypatch):
    cases = {
        "no_quote": _option_row(bid=None, ask=None, quote_ok=False),
        "spread_pct": _option_row(bid=10.0, ask=18.0, quote_ok=True),
        "iv_surface_slope": _option_row(iv_surface_slope=0.35),
        "iv_term": _option_row(
            iv_term=None,
            iv_term_unavailable=True,
            iv_term_unavailable_reason="next_expiry_missing",
        ),
    }

    for reason, row in cases.items():
        builder = _prepared_builder(monkeypatch)
        trade = builder.build(
            _market_data(row),
            quick_mode=False,
            allow_fallbacks=False,
            allow_baseline=False,
        )

        assert trade is not None
        ranked = list(getattr(builder, "_last_ranked_candidates", []) or [])
        assert ranked
        assert any(
            _field(candidate, "candidate_origin") == "dirty_option_bridge"
            for candidate in ranked
        )
        dirty_rows = [
            candidate
            for candidate in ranked
            if _field(candidate, "candidate_origin") == "dirty_option_bridge"
            and (_field(candidate, "dirty_option_reason") or _source_flags(candidate).get("dirty_option_reason")) == reason
        ]
        assert dirty_rows
        _assert_dirty_candidate(dirty_rows[0], reason)


def test_dirty_option_blockers_prevent_normal_trade_builder_bypass(monkeypatch):
    cases = {
        "spread_pct": _option_row(bid=10.0, ask=18.0, quote_ok=True),
        "iv_surface_slope": _option_row(iv_surface_slope=0.35),
        "iv_term": _option_row(
            iv_term=None,
            iv_term_unavailable=True,
            iv_term_unavailable_reason="next_expiry_missing",
        ),
    }

    for reason, row in cases.items():
        builder = _prepared_builder(monkeypatch)
        trade = builder.build(
            _market_data(row),
            quick_mode=False,
            allow_fallbacks=False,
            allow_baseline=False,
        )

        assert trade is not None
        ranked = list(getattr(builder, "_last_ranked_candidates", []) or [])
        assert ranked
        blocked_rows = [
            candidate
            for candidate in ranked
            if reason in _list_field(candidate, "tradable_reasons_blocking")
            or reason in _list_field(candidate, "gate_reasons")
            or reason in _list_field(candidate, "hard_blockers")
        ]
        assert blocked_rows
        assert all(_field(candidate, "execution_allowed", False) is False for candidate in blocked_rows)
        assert all(_field(candidate, "tradable", False) is False for candidate in blocked_rows)
