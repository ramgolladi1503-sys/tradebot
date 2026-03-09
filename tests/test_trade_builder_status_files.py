import json
from pathlib import Path

from config import config as cfg
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder


def _builder_with_logs(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "DATA_ROOT", str(tmp_path / "data"), raising=False)
    (Path(cfg.LOGS_ROOT)).mkdir(parents=True, exist_ok=True)
    return TradeBuilder()


def _write_feed_runtime(logs_root: str, **overrides):
    payload = {
        "feed_ok": True,
        "ws_connected": True,
        "subscribed_option_tokens_count": 70,
        "missing_option_tokens_count": 0,
    }
    payload.update(overrides)
    (Path(logs_root) / "feed_runtime_latest.json").write_text(json.dumps(payload))


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.95


def _base_market_data(*, market_open=True, mode="LIVE"):
    return {
        "symbol": "NIFTY",
        "market_open": bool(market_open),
        "market_context": {
            "execution_mode": mode,
            "market_open": bool(market_open),
            "mode": "OFFHOURS" if not market_open else mode,
        },
        "valid": True,
        "ltp": 25000.0,
        "vwap": 24990.0,
        "bias": "Bullish",
        "instrument": "OPT",
        "chain_source": "live" if market_open else "synthetic_offhours",
        "quote_ok": True,
        "bid": 24999.0,
        "ask": 25001.0,
        "regime": "TREND",
        "regime_day": "TREND",
        "day_type": "TREND_DAY",
        "htf_dir": "UP",
        "orb_bias": "UP",
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000,
                "expiry": "2026-02-26",
                "tradingsymbol": "NIFTY26FEB25000CE",
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


def _patch_builder_for_accept(monkeypatch, builder):
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda md, force_family=None: {
            "direction": "BUY_CALL",
            "reason": "unit",
            "score": 0.95,
            "regime_day": "TREND",
        },
    )
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda strategy_name, mode="MAIN": (True, "ok"))
    monkeypatch.setattr(
        builder,
        "_apply_decay_gate",
        lambda strategy_name, base_score=None, size_mult=1.0: (True, base_score, size_mult, None),
    )
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


def test_trade_builder_status_files_for_blocked_cycle(monkeypatch, tmp_path):
    builder = _builder_with_logs(monkeypatch, tmp_path)
    _write_feed_runtime(cfg.LOGS_ROOT)
    summary = {
        "ts_epoch": 100.0,
        "symbol": "NIFTY",
        "mode": "LIVE",
        "total_candidates": 4,
        "accepted": 0,
        "rejected_by_reason": {"NO_LIVE_OPTION_FEED": 2, "PRICE_MISMATCH": 1},
    }

    builder._write_scan_status_files(summary)

    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "blocked"
    assert suggestions["subreason"] == "NO_LIVE_OPTION_FEED"
    assert suggestions["primary_blocker"] == "NO_LIVE_OPTION_FEED"
    assert suggestions["ws_connected"] is True
    assert suggestions["subscribed_option_tokens_count"] == 70
    assert engine["candidates_blocked"] == 3
    assert engine["cycle_stage"] == "blocked"
    assert engine["market_mode"] == "LIVE"
    assert engine["market_open"] is True
    assert engine["primary_blocker"] == "NO_LIVE_OPTION_FEED"
    assert engine["reason"] == "candidates_blocked"
    assert engine["subreason"] == "NO_LIVE_OPTION_FEED"
    assert engine["feed_ok"] is True
    assert engine["ws_connected"] is True
    assert engine["top_blockers"][0] == {"reason": "NO_LIVE_OPTION_FEED", "count": 2}


def test_trade_builder_status_files_for_accepted_cycle(monkeypatch, tmp_path):
    builder = _builder_with_logs(monkeypatch, tmp_path)
    _write_feed_runtime(cfg.LOGS_ROOT)
    summary = {
        "ts_epoch": 100.0,
        "symbol": "BANKNIFTY",
        "mode": "LIVE",
        "total_candidates": 3,
        "accepted": 1,
        "rejected_by_reason": {},
    }

    builder._write_scan_status_files(summary)

    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "ok"
    assert suggestions["suggestion_count"] == 1
    assert suggestions["primary_blocker"] is None
    assert engine["candidates_enqueued"] == 1
    assert engine["cycle_stage"] == "ok"
    assert engine["primary_blocker"] is None
    assert engine["reason"] == "suggestions_generated"
    assert engine["subreason"] == ""


def test_trade_builder_status_files_for_no_candidate_cycle(monkeypatch, tmp_path):
    builder = _builder_with_logs(monkeypatch, tmp_path)
    _write_feed_runtime(cfg.LOGS_ROOT)
    summary = {
        "ts_epoch": 100.0,
        "symbol": "SENSEX",
        "mode": "LIVE",
        "total_candidates": 0,
        "accepted": 0,
        "rejected_by_reason": {},
    }

    builder._write_scan_status_files(summary)

    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "no_candidates"
    assert suggestions["suggestion_count"] == 0
    assert suggestions["primary_blocker"] == "NO_CANDIDATES"
    assert engine["candidates_seen"] == 0
    assert engine["cycle_stage"] == "no_candidates"
    assert engine["primary_blocker"] == "NO_CANDIDATES"
    assert engine["reason"] == "no_candidates"


def test_build_market_closed_early_return_still_writes_heartbeat(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    builder = _builder_with_logs(monkeypatch, tmp_path)
    _write_feed_runtime(cfg.LOGS_ROOT, feed_ok=False, ws_connected=False, subscribed_option_tokens_count=0, missing_option_tokens_count=3)
    monkeypatch.setattr(builder, "_signal_for_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(builder, "_planning_signal_fallback_signal", lambda *_args, **_kwargs: None)

    trade = builder.build(
        _base_market_data(market_open=False, mode="PAPER"),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None
    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "market_closed"
    assert suggestions["market_open"] is False
    assert suggestions["suggestion_count"] == 0
    assert suggestions["market_mode"] == "OFFHOURS"
    assert suggestions["reason"] == "MARKET_CLOSED"
    assert suggestions["subreason"] != "cycle_complete"
    assert suggestions["primary_blocker"] == "MARKET_CLOSED"
    assert engine["candidates_enqueued"] == 0
    assert engine["cycle_stage"] == "market_closed"
    assert engine["market_mode"] == "OFFHOURS"
    assert engine["market_open"] is False
    assert engine["primary_blocker"] == "MARKET_CLOSED"
    assert engine["reason"] == "MARKET_CLOSED"
    assert engine["subreason"] == ""


def test_build_blocked_cycle_still_writes_heartbeat(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    builder = _builder_with_logs(monkeypatch, tmp_path)
    _write_feed_runtime(cfg.LOGS_ROOT)
    monkeypatch.setattr(builder, "_signal_for_symbol", lambda *_args, **_kwargs: None)

    trade = builder.build(
        _base_market_data(market_open=True, mode="PAPER"),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None
    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "blocked"
    assert suggestions["subreason"] == "no_signal"
    assert suggestions["primary_blocker"] == "no_signal"
    assert engine["candidates_blocked"] >= 1
    assert engine["cycle_stage"] == "blocked"
    assert engine["primary_blocker"] == "no_signal"
    assert engine["top_blockers"][0]["reason"] == "no_signal"


def test_build_accepted_trade_still_writes_heartbeat(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    builder = _builder_with_logs(monkeypatch, tmp_path)
    _write_feed_runtime(cfg.LOGS_ROOT)
    _patch_builder_for_accept(monkeypatch, builder)

    trade = builder.build(
        _base_market_data(market_open=True, mode="PAPER"),
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is not None
    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "ok"
    assert suggestions["suggestion_count"] >= 1
    assert engine["candidates_enqueued"] >= 1


def test_trade_builder_status_preserves_latest_queue_fields(monkeypatch, tmp_path):
    builder = _builder_with_logs(monkeypatch, tmp_path)
    _write_feed_runtime(cfg.LOGS_ROOT)
    existing = {
        "ts_epoch": 90.0,
        "status": "blocked",
        "latest_trade_id": "T-123",
        "latest_entry_status": "NO_LIVE_OPTION_FEED",
        "latest_permission": "BLOCK",
        "latest_permission_reason": "NO_LIVE_OPTION_FEED",
    }
    (Path(cfg.LOGS_ROOT) / "suggestions_status.json").write_text(json.dumps(existing))

    builder._write_scan_status_files(
        {
            "ts_epoch": 100.0,
            "symbol": "NIFTY",
            "mode": "LIVE",
            "total_candidates": 0,
            "accepted": 0,
            "rejected_by_reason": {},
        }
    )

    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    assert suggestions["latest_trade_id"] == "T-123"
    assert suggestions["latest_entry_status"] == "NO_LIVE_OPTION_FEED"
    assert suggestions["latest_permission"] == "BLOCK"
    assert suggestions["latest_permission_reason"] == "NO_LIVE_OPTION_FEED"


def test_trade_builder_status_uses_explicit_market_open_not_generic_sim_mode(monkeypatch, tmp_path):
    builder = _builder_with_logs(monkeypatch, tmp_path)
    _write_feed_runtime(cfg.LOGS_ROOT)

    builder._write_scan_status_files(
        {
            "ts_epoch": 100.0,
            "symbol": "NIFTY",
            "mode": "SIM",
            "market_mode": "OFFHOURS",
            "market_open": False,
            "total_candidates": 0,
            "accepted": 0,
            "rejected_by_reason": {},
        }
    )

    suggestions = json.loads((Path(cfg.LOGS_ROOT) / "suggestions_status.json").read_text())
    engine = json.loads((Path(cfg.LOGS_ROOT) / "engine_cycle_status.json").read_text())
    assert suggestions["status"] == "market_closed"
    assert suggestions["reason"] == "MARKET_CLOSED"
    assert suggestions["subreason"] != "cycle_complete"
    assert suggestions["market_mode"] == "OFFHOURS"
    assert engine["cycle_stage"] == "market_closed"
    assert engine["primary_blocker"] == "MARKET_CLOSED"
    assert engine["market_mode"] == "OFFHOURS"
    assert engine["market_open"] is False
    assert engine["reason"] == "MARKET_CLOSED"
