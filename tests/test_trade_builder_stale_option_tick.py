from __future__ import annotations

from strategies.trade_builder import TradeBuilder


class _MarketCtx:
    def __init__(self, allow_stale_quotes: bool = True):
        self.allow_stale_quotes = allow_stale_quotes
        self.mode = "SIM"
        self.is_market_open = False


def test_stale_option_tick_softens_when_allowed(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-03-26",
            "tradingsymbol": "NIFTY26MAR25000CE",
            "instrument_token": 123456,
            "instrument_id": "NIFTY26MAR25000CE",
        },
        raising=True,
    )
    opt = {
        "strike": 25000,
        "type": "CE",
        "quote_source": "live",
        "option_ltp_source": "option_chain_live",
        "quote_ts_epoch": None,
    }
    ok, ctx = tb._option_tradability_precondition(
        symbol="NIFTY",
        opt=opt,
        market_data={"symbol": "NIFTY"},
        market_ctx=_MarketCtx(allow_stale_quotes=True),
        direction="BUY_CALL",
    )
    assert ok is True
    assert ctx.get("stale_option_tick") is True
