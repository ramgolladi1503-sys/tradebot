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
            "reason": "partial_row_reject_test",
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


def test_partial_option_rows_are_rejected_and_recorded(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    md = _base_market_data()
    md["option_chain"] = [
        {"type": "CE", "strike": 25000, "bid": 99, "ask": 101},  # missing ltp
        {"type": "CE", "strike": 25000, "ltp": 100, "ask": 101},  # missing bid
        {"type": "CE", "strike": 25000, "ltp": 100, "bid": 99},  # missing ask
        {"type": "CE", "strike": 25000, "ltp": 100, "bid": 101, "ask": 99},  # invalid quote
        {"type": "PE", "strike": 25000, "ltp": 100, "bid": 99, "ask": 101},
    ]

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("no_quote", 0)) >= 2
    assert int(builder._scan_reject_counts.get("no_bid_ask", 0)) >= 1


def test_missing_instrument_token_is_hard_reject(monkeypatch):
    builder = _prepared_builder(monkeypatch)
    md = _base_market_data()
    md["option_chain"] = [
        {"type": "CE", "strike": 25000, "ltp": 100, "bid": 99, "ask": 101, "expiry": "2026-01-01"}
    ]

    monkeypatch.setattr(
        builder,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-01-01",
            "expiry_date": "2026-01-01",
            "tradingsymbol": "NIFTY26JAN25000CE",
            "instrument_token": None,
            "instrument_id": "NIFTY|OPT|2026-01-01|25000|CE",
        },
    )
    monkeypatch.setattr(
        builder,
        "_identity_fields",
        lambda *_args, **_kwargs: ("OPT", "NIFTY|OPT|2026-01-01|25000|CE", 1, None),
    )

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("missing_contract_fields", 0)) >= 1
    gate_reasons = builder._reject_ctx.get("gate_reasons") if isinstance(builder._reject_ctx, dict) else []
    assert "missing_contract_fields" in list(gate_reasons or [])
