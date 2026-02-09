from datetime import timedelta

from core.trade_ticket import TradeTicket
from core.time_utils import now_ist, now_utc_epoch


def test_trade_ticket_actionable():
    exp = (now_ist().date() + timedelta(days=1)).isoformat()
    ticket = TradeTicket(
        trace_id="T1",
        timestamp_epoch=now_utc_epoch(),
        timestamp_ist=now_ist().isoformat(),
        desk_id="DEFAULT",
        underlying="NIFTY",
        instrument_type="OPT",
        expiry=exp,
        strike=22000,
        right="CE",
        instrument_id=f"NIFTY|{exp}|22000|CE",
        side="BUY",
        entry_type="LIMIT",
        entry_price=100.0,
        sl_price=90.0,
        tgt_price=140.0,
        qty_lots=1,
        qty_units=50,
        validity_sec=120,
        reason_codes=["regime:TREND"],
        guardrails=["spread>3%"],
    )
    ok, reason = ticket.is_actionable()
    assert ok is True
    assert reason == "ok"


def test_trade_ticket_missing_contract():
    ticket = TradeTicket(
        trace_id="T2",
        timestamp_epoch=now_utc_epoch(),
        timestamp_ist=now_ist().isoformat(),
        desk_id="DEFAULT",
        underlying="NIFTY",
        instrument_type="OPT",
        expiry=None,
        strike=None,
        right=None,
        instrument_id=None,
        side="BUY",
        entry_type="LIMIT",
        entry_price=100.0,
        sl_price=90.0,
        tgt_price=140.0,
        qty_lots=1,
        qty_units=50,
        validity_sec=120,
        reason_codes=[],
        guardrails=[],
    )
    ok, reason = ticket.is_actionable()
    assert ok is False
    assert reason in ("missing_expiry", "missing_strike", "missing_right", "missing_instrument_id")
