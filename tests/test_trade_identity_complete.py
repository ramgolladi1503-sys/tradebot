from core.trade_schema import TradeIntent, build_instrument_id, validate_trade_identity


def test_trade_identity_requires_fields():
    ok, reason = validate_trade_identity("NIFTY", "OPT", None, 22000, "CE")
    assert ok is False
    assert reason == "missing_expiry"


def test_build_instrument_id_ok():
    inst = build_instrument_id("NIFTY", "OPT", "2026-02-14", 22000, "CE")
    assert inst == "NIFTY|2026-02-14|22000|CE"


def test_trade_intent_actionable():
    intent = TradeIntent(
        trace_id="T-1",
        desk_id="DEFAULT",
        timestamp_epoch=1700000000.0,
        underlying="NIFTY",
        instrument_type="OPT",
        expiry="2026-02-14",
        strike=22000,
        right="CE",
        instrument_id="NIFTY|2026-02-14|22000|CE",
        side="BUY",
        entry_type="LIMIT",
        entry_price=100.0,
        sl_price=90.0,
        target_price=120.0,
        qty_lots=1,
        qty_units=50,
        validity_sec=180,
        tradable=True,
    )
    ok, reason = intent.is_actionable()
    assert ok is True
    assert reason == "ok"


def test_trade_intent_missing_contract_rejected():
    intent = TradeIntent(
        trace_id="T-2",
        desk_id="DEFAULT",
        timestamp_epoch=1700000000.0,
        underlying="NIFTY",
        instrument_type="OPT",
        expiry=None,
        strike=22000,
        right="CE",
        instrument_id=None,
        side="BUY",
        entry_type="LIMIT",
        entry_price=100.0,
        sl_price=90.0,
        target_price=120.0,
        qty_lots=1,
        qty_units=50,
        validity_sec=180,
        tradable=True,
    )
    ok, reason = intent.is_actionable()
    assert ok is False
    assert reason == "missing_expiry"
