"""Pure, mock-only GTT stop safety contract tests.
No live dispatcher or order-action branch is exercised.
"""

from core.orders.gtt_stop_dispatcher import GTTStopDispatcher


def test_stop_reservation_blocks_duplicate_symbol_before_transport():
    dispatcher = GTTStopDispatcher()
    reserved, key = dispatcher._reserve_stop("NIFTY 25450 CE", "parent-1")
    assert reserved is True
    assert dispatcher._stop_reservations[key]["state"] == "RESERVED"
    duplicate, reason = dispatcher._reserve_stop("NIFTY 25450 CE", "parent-2")
    assert duplicate is False
    assert "reserved" in reason


def test_ambiguous_stop_reservation_is_not_released():
    dispatcher = GTTStopDispatcher()
    reserved, key = dispatcher._reserve_stop("NIFTY 25450 CE", "parent-1")
    assert reserved
    dispatcher._set_stop_reservation_state(key, "UNKNOWN", "broker-order-1")
    again, _ = dispatcher._reserve_stop("NIFTY 25450 CE", "parent-1")
    assert again is False


def test_generic_order_ack_is_never_classified_as_active_gtt():
    classify = GTTStopDispatcher._classify_submission_state
    assert classify("SUBMITTED", dedicated_gtt_interface=False) == "UNKNOWN"
    assert classify("ACTIVE", dedicated_gtt_interface=False) == "UNKNOWN"
    assert classify("ACTIVE", dedicated_gtt_interface=True) == "ACTIVE"
def test_stop_trigger_calculation():
    dispatcher = GTTStopDispatcher()
    # Buy entry at 20.0, stop loss 3.12 pts -> 16.88 -> tick rounded to 16.90
    trigger = dispatcher.calculate_stop_trigger(entry_price=20.0, sl_pts=3.12, side="BUY")
    assert trigger == 16.90

    # Sell entry at 20.0, stop loss 3.12 pts -> 23.12 -> tick rounded to 23.10
    trigger_sell = dispatcher.calculate_stop_trigger(entry_price=20.0, sl_pts=3.12, side="SELL")
    assert trigger_sell == 23.10

    # Deep stop cannot be <= 0
    trigger_floor = dispatcher.calculate_stop_trigger(entry_price=5.0, sl_pts=10.0, side="BUY")
    assert trigger_floor == 0.05

def test_cancel_race_with_filled_or_triggered_stop_blocks_target():
    from types import SimpleNamespace
    for update in (
        SimpleNamespace(status="COMPLETE", filled_qty=75),
        SimpleNamespace(status="CANCELLED", filled_qty=1),
        SimpleNamespace(status="TRIGGER_PENDING", filled_qty=0),
    ):
        permitted, reason = GTTStopDispatcher.validate_cancelled_stop_update(update)
        assert permitted is False
        assert "blocked" in reason.lower() or "reconcile" in reason.lower()


def test_only_explicit_cancelled_zero_fill_is_acceptable():
    from types import SimpleNamespace
    permitted, reason = GTTStopDispatcher.validate_cancelled_stop_update(
        SimpleNamespace(status="CANCELLED", filled_qty=0)
    )
    assert permitted is True
    assert "zero-fill" in reason.lower()


def test_missing_unknown_partial_and_malformed_stop_status_fail_closed():
    from types import SimpleNamespace
    for update in (
        None,
        SimpleNamespace(status="UNKNOWN", filled_qty=0),
        SimpleNamespace(status="CANCELLED", filled_qty=None),
        SimpleNamespace(status="CANCELLED", filled_qty=0.5),
    ):
        permitted, _ = GTTStopDispatcher.validate_cancelled_stop_update(update)
        assert permitted is False
