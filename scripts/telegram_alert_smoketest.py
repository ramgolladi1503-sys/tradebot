import sys
from datetime import timedelta

from core.trade_ticket import TradeTicket
from core.time_utils import now_ist, now_utc_epoch


def _sample_ticket():
    exp = (now_ist().date() + timedelta(days=1)).isoformat()
    return TradeTicket(
        trace_id="TEST-123",
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
        entry_price=120.5,
        sl_price=100.0,
        tgt_price=170.0,
        qty_lots=1,
        qty_units=50,
        validity_sec=180,
        reason_codes=["regime:TREND", "strategy:SCALP"],
        guardrails=["spread>3%", "quote_age>2s"],
    )


def _incomplete_ticket():
    return TradeTicket(
        trace_id="TEST-NA",
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
        entry_price=120.5,
        sl_price=100.0,
        tgt_price=170.0,
        qty_lots=1,
        qty_units=50,
        validity_sec=180,
        reason_codes=[],
        guardrails=[],
    )


def main():
    ticket = _sample_ticket()
    ok, reason = ticket.is_actionable()
    print("sample_actionable:", ok, reason)
    print(ticket.format_message())
    bad = _incomplete_ticket()
    ok2, reason2 = bad.is_actionable()
    print("incomplete_actionable:", ok2, reason2)
    if ok is not True or ok2 is not False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
