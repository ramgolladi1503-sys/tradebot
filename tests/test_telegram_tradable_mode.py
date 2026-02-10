from datetime import timedelta

from config import config as cfg
from core.telegram_alerts import send_trade_ticket
from core.time_utils import now_ist, now_utc_epoch
from core.trade_ticket import TradeTicket


class _Resp:
    status_code = 200


def _ticket(*, tradable: bool, expiry: str | None, strike, right, instrument_id: str | None, reasons=None):
    return TradeTicket(
        trace_id="T-TELEGRAM-1",
        timestamp_epoch=now_utc_epoch(),
        timestamp_ist=now_ist().isoformat(),
        desk_id="DEFAULT",
        underlying="NIFTY",
        instrument_type="OPT",
        expiry=expiry,
        strike=strike,
        right=right,
        instrument_id=instrument_id,
        side="BUY",
        entry_type="LIMIT",
        entry_price=100.0,
        sl_price=90.0,
        tgt_price=120.0,
        qty_lots=1,
        qty_units=50,
        validity_sec=180,
        tradable=tradable,
        tradable_reasons_blocking=list(reasons or []),
        source_flags={},
        reason_codes=["strategy:SCALP"],
        guardrails=["spread>3%"],
    )


def test_telegram_sends_market_note_when_non_tradable(monkeypatch):
    sent = []

    def _fake_post(_url, data=None, **_kwargs):
        sent.append(data.get("text"))
        return _Resp()

    monkeypatch.setattr(cfg, "ENABLE_TELEGRAM", True, raising=False)
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "x", raising=False)
    monkeypatch.setattr(cfg, "TELEGRAM_CHAT_ID", "y", raising=False)
    monkeypatch.setattr("core.telegram_alerts.requests.post", _fake_post)

    exp = (now_ist().date() + timedelta(days=1)).isoformat()
    ticket = _ticket(
        tradable=False,
        expiry=exp,
        strike=22000,
        right="CE",
        instrument_id=f"NIFTY|{exp}|22000|CE",
        reasons=["stale_option_quote"],
    )
    ok = send_trade_ticket(ticket)
    assert ok is True
    assert sent
    assert sent[0].startswith("MARKET NOTE")
    assert "- stale_option_quote" in sent[0]


def test_telegram_sends_trade_ticket_when_tradable(monkeypatch):
    sent = []

    def _fake_post(_url, data=None, **_kwargs):
        sent.append(data.get("text"))
        return _Resp()

    monkeypatch.setattr(cfg, "ENABLE_TELEGRAM", True, raising=False)
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "x", raising=False)
    monkeypatch.setattr(cfg, "TELEGRAM_CHAT_ID", "y", raising=False)
    monkeypatch.setattr("core.telegram_alerts.requests.post", _fake_post)

    exp = (now_ist().date() + timedelta(days=1)).isoformat()
    ticket = _ticket(
        tradable=True,
        expiry=exp,
        strike=22000,
        right="CE",
        instrument_id=f"NIFTY|{exp}|22000|CE",
    )
    ok = send_trade_ticket(ticket)
    assert ok is True
    assert sent
    assert sent[0].startswith("TRADE TICKET")


def test_telegram_rejects_actionable_send_when_contract_missing(monkeypatch):
    sent = []

    def _fake_post(_url, data=None, **_kwargs):
        sent.append(data.get("text"))
        return _Resp()

    monkeypatch.setattr(cfg, "ENABLE_TELEGRAM", True, raising=False)
    monkeypatch.setattr(cfg, "TELEGRAM_BOT_TOKEN", "x", raising=False)
    monkeypatch.setattr(cfg, "TELEGRAM_CHAT_ID", "y", raising=False)
    monkeypatch.setattr("core.telegram_alerts.requests.post", _fake_post)

    ticket = _ticket(
        tradable=True,
        expiry=None,
        strike=None,
        right=None,
        instrument_id=None,
    )
    ok = send_trade_ticket(ticket)
    assert ok is False
    assert sent == []
