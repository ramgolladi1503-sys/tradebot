from __future__ import annotations

from config import config as cfg
import strategies.trade_builder as trade_builder_module
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
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ENFORCE_STRIKE_LADDER", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda _md, force_family=None: {
            "direction": "BUY_CALL",
            "reason": "VWAP trend up",
            "score": 0.95,
            "regime_day": "TREND",
        },
        raising=True,
    )
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"), raising=True)
    monkeypatch.setattr(
        builder,
        "_apply_decay_gate",
        lambda _strategy_name, base_score=None, size_mult=1.0: (True, base_score, size_mult, None),
        raising=True,
    )
    monkeypatch.setattr(builder, "_validate_ml_features", lambda _feats: (True, "ok"), raising=True)
    monkeypatch.setattr(
        trade_builder_module,
        "compute_trade_score",
        lambda *args, **kwargs: {"score": 100.0, "alignment": 1.0},
        raising=True,
    )
    return builder


def _option_row(*, strike: int, expiry: str, token: int) -> dict:
    moneyness = abs(float(strike) - 25000.0) / 25000.0
    return {
        "type": "CE",
        "strike": strike,
        "expiry": expiry,
        "tradingsymbol": f"NIFTY{expiry.replace('-', '')}{strike}CE",
        "instrument_token": token,
        "ltp": 100.0,
        "bid": 99.0,
        "ask": 101.0,
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
        "moneyness": moneyness,
    }


def _market_data(chain: list[dict]) -> dict:
    return {
        "symbol": "NIFTY",
        "market_open": True,
        "market_context": {"execution_mode": "PAPER", "market_open": True, "mode": "PAPER"},
        "valid": True,
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
        "option_chain": list(chain),
    }


def test_candidate_pool_increases_for_broader_ladder_and_next_expiry(monkeypatch):
    chain = []
    token = 1000
    for expiry in ("2026-03-26", "2026-04-02"):
        for strike in (24900, 24950, 25000, 25050, 25100):
            chain.append(_option_row(strike=strike, expiry=expiry, token=token))
            token += 1
    baseline_builder = _prepared_builder(monkeypatch)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_STRIKE_LADDER_WIDTH", 0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_EXPIRY_BUCKET_MODE", "SAME", raising=False)
    baseline_trade = baseline_builder.build(_market_data(chain), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    broadened_builder = _prepared_builder(monkeypatch)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_STRIKE_LADDER_WIDTH", 2, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_EXPIRY_BUCKET_MODE", "SAME_AND_NEXT", raising=False)
    broadened_trade = broadened_builder.build(_market_data(chain), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert baseline_trade is not None
    assert broadened_trade is not None
    assert len(baseline_builder._last_ranked_candidates) == 1
    assert len(broadened_builder._last_ranked_candidates) > len(baseline_builder._last_ranked_candidates)
    origin = (broadened_builder._last_ranked_candidates[0].source_flags or {}).get("candidate_origin") or {}
    assert set(origin) >= {"strike_offset", "setup_family", "expiry_bucket"}
    assert origin["setup_family"] == "continuation"


def test_duplicate_candidate_rows_are_suppressed(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_STRIKE_LADDER_WIDTH", 0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_EXPIRY_BUCKET_MODE", "SAME", raising=False)
    row = _option_row(strike=25000, expiry="2026-03-26", token=123456)
    trade = builder.build(
        _market_data([dict(row), dict(row)]),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    assert len(builder._last_ranked_candidates) == 1
    assert int(builder._last_scan_summary.get("total_candidates") or 0) == 1


def test_strike_ladder_generation_is_deterministic(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_STRIKE_LADDER_WIDTH", 2, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_EXPIRY_BUCKET_MODE", "SAME", raising=False)
    chain = [
        _option_row(strike=25050, expiry="2026-03-26", token=1),
        _option_row(strike=24900, expiry="2026-03-26", token=2),
        _option_row(strike=25100, expiry="2026-03-26", token=3),
        _option_row(strike=25000, expiry="2026-03-26", token=4),
        _option_row(strike=24950, expiry="2026-03-26", token=5),
    ]

    rows = builder._annotate_candidate_chain_rows("NIFTY", _market_data(chain), 25000.0)
    offsets = [row["candidate_origin"]["strike_offset"] for row in rows]
    buckets = [row["candidate_origin"]["expiry_bucket"] for row in rows]

    assert offsets == [0, -1, 1, -2, 2]
    assert buckets == ["same_expiry"] * 5


def test_force_family_emits_canonical_setup_family_metadata(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda _md, force_family=None: {
            "direction": "BUY_CALL",
            "reason": "Mean reversion up",
            "score": 0.95,
            "regime_day": "RANGE",
        },
        raising=True,
    )
    monkeypatch.setattr(cfg, "TRADE_BUILDER_STRIKE_LADDER_WIDTH", 0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_EXPIRY_BUCKET_MODE", "SAME", raising=False)
    trade = builder.build(
        _market_data([_option_row(strike=25000, expiry="2026-03-26", token=777001)]),
        quick_mode=False,
        force_family="MEAN_REVERT",
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    origin = (trade.source_flags or {}).get("candidate_origin") or {}
    assert origin["setup_family"] == "mean-reversion"
