from config import config as cfg
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.95


def _base_market_data():
    return {
        "symbol": "NIFTY",
        "valid": True,
        "ltp": 25000.0,
        "vwap": 24990.0,
        "bias": "Bullish",
        "instrument": "OPT",
        "chain_source": "live",
        "quote_ok": False,
        "bid": None,
        "ask": None,
        "index_quote_cache": {"symbol": "NIFTY", "last_price": 25000.0, "ts_epoch": 1771400000.0},
        "regime": "TREND",
        "regime_day": "TREND",
        "day_type": "TREND_DAY",
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000,
                "expiry": "2026-02-26",
                "instrument_token": 123456,
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
                "moneyness": 0.0,
            }
        ],
    }


def _patch_builder_for_deterministic_pass(monkeypatch, builder):
    monkeypatch.setattr(builder, "_signal_for_symbol", lambda md, force_family=None: {"direction": "BUY_CALL", "reason": "unit", "score": 0.95, "regime_day": "TREND"})
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda strategy_name, mode="MAIN": (True, "ok"))
    monkeypatch.setattr(builder, "_apply_decay_gate", lambda strategy_name, base_score=None, size_mult=1.0: (True, base_score, size_mult, None))
    monkeypatch.setattr(builder, "_validate_ml_features", lambda feats: (True, "ok"))
    monkeypatch.setattr(trade_builder_module, "compute_trade_score", lambda *args, **kwargs: {"score": 100.0, "alignment": 1.0})
    monkeypatch.setattr(cfg, "ALPHA_ENSEMBLE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_AB_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_USE_ONLY_WITH_HISTORY", False, raising=False)
    monkeypatch.setattr(cfg, "ML_MIN_PROBA", 0.1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 1.0, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)
    monkeypatch.setattr(cfg, "MIN_RR", 0.1, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)


def test_paper_missing_index_bid_ask_uses_synthetic(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    events = []
    monkeypatch.setattr(trade_builder_module, "_log_signal_event", lambda kind, symbol, payload=None: events.append({"kind": kind, "symbol": symbol, "payload": payload or {}}))

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder_for_deterministic_pass(monkeypatch, builder)
    trade = builder.build(_base_market_data(), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.source_flags.get("index_quote_source") == "synthetic"
    assert trade.source_flags.get("index_bidask_synthetic") is True
    assert trade.source_flags.get("index_quote_kind") == "synthetic"
    rows = [e for e in events if e["kind"] == "index_bidask_source" and e["payload"].get("source") == "synthetic"]
    assert rows
    payload = rows[-1]["payload"]
    assert payload.get("quote_kind") == "synthetic"
    assert payload.get("last_price") == 25000.0
    assert payload.get("bid") == 24995.0
    assert payload.get("ask") == 25005.0


def test_live_missing_index_bid_ask_rejects(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    events = []
    monkeypatch.setattr(trade_builder_module, "_log_signal_event", lambda kind, symbol, payload=None: events.append({"kind": kind, "symbol": symbol, "payload": payload or {}}))

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder_for_deterministic_pass(monkeypatch, builder)
    trade = builder.build(
        _base_market_data(),
        quick_mode=False,
        debug_reasons=True,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None
    assert builder._reject_ctx.get("reason") == "missing_live_bidask"
    assert builder._reject_ctx.get("gate_reasons") == ["missing_live_bidask", "quote_api_issue"]
    assert any(e["kind"] == "index_bidask_source" and e["payload"].get("source") == "missing" for e in events)
    reject_rows = [e for e in events if e["kind"] == "trade_reject_missing_live_bidask"]
    assert reject_rows
    reject_payload = reject_rows[-1]["payload"]
    assert set(["ltp", "ltp_source", "has_depth", "has_quote", "ws_subscribed"]).issubset(reject_payload.keys())
    assert reject_payload.get("gate_reasons") == ["missing_live_bidask", "quote_api_issue"]
    out = capsys.readouterr().out
    assert "missing_live_bidask" in out
    assert "ltp=" in out
    assert "ltp_source=" in out
    assert "has_depth=" in out
    assert "has_quote=" in out
    assert "ws_subscribed=" in out
