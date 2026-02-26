from __future__ import annotations

from config import config as cfg
from strategies.trade_builder import TradeBuilder


def _base_market_data() -> dict:
    return {
        "symbol": "NIFTY",
        "valid": True,
        "market_open": False,
        "market_context": {"execution_mode": "PAPER", "market_open": False},
        "ltp": 25000.0,
        "vwap": 24990.0,
        "atr": 25.0,
        "instrument": "OPT",
        "chain_source": "synthetic_offhours",
        "quote_ok": True,
        "bid": 24999.0,
        "ask": 25001.0,
        "regime_day": "TREND",
        "htf_dir": "UP",
        "orb_bias": "UP",
        "bias": "Bullish",
        "option_chain": [],
    }


def _prepared_builder(monkeypatch) -> TradeBuilder:
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    builder = TradeBuilder()
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda *_args, **_kwargs: {
            "direction": "BUY_CALL",
            "reason": "fault_injection_signal",
            "score": 0.9,
            "regime_day": "TREND",
        },
    )
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr(
        builder,
        "_apply_decay_gate",
        lambda _strategy_name, base_score=None, size_mult=1.0: (True, base_score, size_mult, None),
    )
    return builder


def test_build_handles_non_dict_option_rows_without_crash(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    md = _base_market_data()
    md["option_chain"] = [None, "bad-row", 1, ["nested"], {"strike": 25000, "ltp": 100, "bid": 99, "ask": 101}]

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False, debug_reasons=True)

    assert trade is None


def test_build_handles_partial_option_rows_without_crash(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    md = _base_market_data()
    md["option_chain"] = [
        {"type": "CE"},
        {"type": "CE", "strike": "oops", "ltp": 100, "bid": 99, "ask": 101},
        {"type": "CE", "strike": 25000, "ltp": "", "bid": 99, "ask": 101},
        {"type": "PE", "strike": 25000, "ltp": 100, "bid": 99, "ask": 101},
    ]

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False, debug_reasons=True)

    assert trade is None
