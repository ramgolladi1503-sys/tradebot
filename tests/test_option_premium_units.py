from config import config as cfg
from strategies.trade_builder import TradeBuilder
from core.trade_schema import build_instrument_id


class _PredictorStub:
    def predict_confidence(self, _feats):
        return 0.9


def test_quick_synth_uses_premium_units(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr(builder, "_apply_decay_gate", lambda *_args, **_kwargs: (True, None, 1.0, None))
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda *_args, **_kwargs: {
            "direction": "BUY_CALL",
            "reason": "unit_test_signal",
            "score": 0.9,
            "regime_day": "TREND",
        },
    )
    monkeypatch.setattr(builder, "_resolve_expiry_for_symbol", lambda *_args, **_kwargs: "2026-02-27")

    def _resolve_contract(symbol, strike, opt_type, expiry, market_data):
        return {
            "expiry": expiry,
            "expiry_date": expiry,
            "tradingsymbol": f"{symbol}TEST{int(strike)}{opt_type}",
            "instrument_token": 123456,
            "instrument_id": build_instrument_id(symbol, "OPT", expiry, strike, opt_type),
        }

    monkeypatch.setattr(builder, "_resolve_option_contract", _resolve_contract)

    trade = builder.build(
        {
            "symbol": "BANKNIFTY",
            "valid": True,
            "ltp": 60000.0,
            "quote_age_sec": 1.0,
            "instrument": "OPT",
            "option_chain": [],
            "chain_source": "synthetic",
            "quote_ok": True,
            "bid": None,
            "ask": None,
        },
        quick_mode=True,
        allow_fallbacks=True,
        allow_baseline=True,
    )

    assert trade is not None
    assert trade.entry_price < 1000
    assert trade.target < 1000
    assert trade.expiry_date == "2026-02-27"
    assert trade.tradingsymbol is not None
