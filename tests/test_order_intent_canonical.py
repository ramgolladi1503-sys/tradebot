from decimal import Decimal

from core.orders.order_intent import OrderIntent


def _base_intent(**overrides):
    payload = {
        "symbol": "NIFTY",
        "instrument_type": "option",
        "side": "BUY",
        "qty": 10,
        "order_type": "LIMIT",
        "limit_price": 101.0,
        "exchange": "NFO",
        "product": "MIS",
        "strategy_id": "TEST_STRAT",
        "timestamp_bucket": 123456,
        "expiry": "2026-02-12",
        "strike": 25200,
        "right": "CE",
        "multiplier": 1.0,
    }
    payload.update(overrides)
    return OrderIntent(**payload)


def test_order_intent_hash_stable_for_semantically_equal_values():
    one = _base_intent(limit_price=101.0, multiplier=1.0, strike=25200)
    two = _base_intent(limit_price=Decimal("101.000000000"), multiplier=Decimal("1.00000000"), strike=25200.0)
    assert one.to_canonical_dict() == two.to_canonical_dict()
    assert one.intent_hash() == two.intent_hash()


def test_order_intent_hash_changes_when_any_field_changes():
    base = _base_intent()
    assert _base_intent(qty=11).intent_hash() != base.intent_hash()
    assert _base_intent(limit_price=101.25).intent_hash() != base.intent_hash()
    assert _base_intent(strike=25300).intent_hash() != base.intent_hash()
    assert _base_intent(expiry="2026-02-19").intent_hash() != base.intent_hash()
