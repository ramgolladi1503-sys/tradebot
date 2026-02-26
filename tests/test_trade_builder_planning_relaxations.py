from __future__ import annotations

from config import config as cfg
from strategies.trade_builder import TradeBuilder


def test_planning_signal_fallback_uses_vwap_edge(monkeypatch):
    monkeypatch.setattr(cfg, "PLANNING_SIGNAL_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "PLANNING_SIGNAL_VWAP_EDGE_MIN", 0.0005, raising=False)
    tb = TradeBuilder()
    signal = tb._planning_signal_fallback_signal(
        {
            "atr": 40.0,
            "ltp_change_window": 0.0,
            "ltp_change": 0.0,
        },
        ltp=25040.0,
        vwap=25000.0,
    )
    assert signal is not None
    assert signal["direction"] == "BUY_CALL"
    assert signal["reason"] == "Planning VWAP fallback"


def test_build_planning_relaxes_orb_neutral_block(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_NEUTRAL_ALLOW", False, raising=False)
    monkeypatch.setattr(cfg, "PLANNING_ORB_NEUTRAL_ALLOW", True, raising=False)
    monkeypatch.setattr(cfg, "ALLOW_BASELINE_SIGNAL", False, raising=False)
    monkeypatch.setattr(cfg, "PLANNING_SIGNAL_FALLBACK_ENABLE", False, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_resolve_index_bid_ask", lambda md, _mode: dict(md), raising=True)
    monkeypatch.setattr(
        tb,
        "_signal_for_symbol",
        lambda _md, force_family=None: {
            "direction": "BUY_CALL",
            "reason": "test_signal",
            "score": 0.95,
            "regime_day": "TREND",
        },
        raising=True,
    )
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, None), raising=True)
    monkeypatch.setattr(tb, "_apply_decay_gate", lambda *_args, **_kwargs: (True, None, 1.0, None), raising=True)

    blocked_reasons: list[str] = []

    def _capture(symbol, reason, message, market_data=None, extra=None):
        blocked_reasons.append(str(reason))

    monkeypatch.setattr(tb, "_log_blocked_candidate", _capture, raising=True)

    md = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_open": True,
        "market_context": {"execution_mode": "SIM", "market_open": True},
        "ltp": 25000.0,
        "vwap": 24990.0,
        "atr": 40.0,
        "quote_ok": True,
        "bid": 24995.0,
        "ask": 25005.0,
        "orb_bias": "NEUTRAL",
        "regime": "TREND",
        "regime_probs": {"TREND": 0.7, "RANGE": 0.3},
        "option_chain": [],
    }

    trade = tb.build(md, quick_mode=False, allow_fallbacks=True, allow_baseline=False)
    assert trade is None
    assert "orb_neutral_blocked" not in blocked_reasons


def test_build_live_respects_orb_neutral_block(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_HARD_BLOCK_LIVE", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_NEUTRAL_ALLOW", False, raising=False)
    monkeypatch.setattr(cfg, "PLANNING_ORB_NEUTRAL_ALLOW", True, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_resolve_index_bid_ask", lambda md, _mode: dict(md), raising=True)
    monkeypatch.setattr(
        tb,
        "_signal_for_symbol",
        lambda _md, force_family=None: {
            "direction": "BUY_CALL",
            "reason": "test_signal",
            "score": 0.95,
            "regime_day": "TREND",
        },
        raising=True,
    )
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, None), raising=True)
    monkeypatch.setattr(tb, "_apply_decay_gate", lambda *_args, **_kwargs: (True, None, 1.0, None), raising=True)

    blocked_reasons: list[str] = []

    def _capture(symbol, reason, message, market_data=None, extra=None):
        blocked_reasons.append(str(reason))

    monkeypatch.setattr(tb, "_log_blocked_candidate", _capture, raising=True)

    md = {
        "symbol": "NIFTY",
        "instrument": "OPT",
        "market_open": True,
        "market_context": {"execution_mode": "LIVE", "market_open": True},
        "chain_source": "live",
        "ltp": 25000.0,
        "vwap": 24990.0,
        "atr": 40.0,
        "quote_ok": True,
        "bid": 24995.0,
        "ask": 25005.0,
        "orb_bias": "NEUTRAL",
        "regime": "TREND",
        "regime_probs": {"TREND": 0.7, "RANGE": 0.3},
        "option_chain": [],
    }

    trade = tb.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is None
    assert "orb_neutral_blocked" in blocked_reasons
