"""Mock-only contract coverage for Upstox submission and fill status mapping."""

import math

from core.broker.upstox_broker_adapter import UpstoxBrokerAdapter
from core.broker_interface import BrokerOrderRequest
from core.sentinel_automated_order_dispatcher import SentinelAutomatedOrderDispatcher


def test_order_type_mapping_rejects_unsupported_gtt_instead_of_market():
    assert UpstoxBrokerAdapter._map_order_type("LIMIT") == "LIMIT"
    assert UpstoxBrokerAdapter._map_order_type("SL_M") == "SL-M"
    try:
        UpstoxBrokerAdapter._map_order_type("GTT")
    except ValueError as exc:
        assert "Unsupported Upstox order type" in str(exc)
    else:
        raise AssertionError("unsupported GTT must not be silently mapped to MARKET")


def test_dispatch_fill_classification_requires_consistent_broker_status_and_quantity():
    classify = SentinelAutomatedOrderDispatcher._classify_fill_status
    assert classify("SUBMITTED", 0, 25) == "SUBMITTED"
    assert classify("PARTIAL", 10, 25) == "PARTIAL"
    assert classify("COMPLETE", 25, 25) == "FILLED"
    assert classify("COMPLETE", 0, 25) == "UNKNOWN"
    assert classify("COMPLETE", 10, 25) == "UNKNOWN"
    assert classify("PARTIAL", 25, 25) == "UNKNOWN"
    assert classify("OPEN", 1, 25) == "UNKNOWN"
    assert classify("PARTIAL", 1.5, 25) == "UNKNOWN"
    assert classify("PARTIAL", True, 25) == "UNKNOWN"


def test_payload_builder_validates_required_order_fields_without_transport():
    req = BrokerOrderRequest(symbol="NSE_FO|123", side="BUY", qty=25,
                             order_type="LIMIT", limit_price=101.25)
    payload = UpstoxBrokerAdapter.build_order_payload(req)
    assert payload["instrument_token"] == "NSE_FO|123"
    assert payload["transaction_type"] == "BUY"
    assert payload["quantity"] == 25
    assert payload["price"] == 101.25

    for changes in (
        {"symbol": ""}, {"symbol": "NSE FO|123"}, {"side": "HOLD"},
        {"qty": 0}, {"qty": True}, {"qty": 1.5}, {"limit_price": None},
        {"limit_price": math.inf}, {"limit_price": 0}, {"order_type": "GTT"},
    ):
        values = {"symbol": "NSE_FO|123", "side": "BUY", "qty": 25,
                  "order_type": "LIMIT", "limit_price": 101.25}
        values.update(changes)
        try:
            UpstoxBrokerAdapter.build_order_payload(BrokerOrderRequest(**values))
        except ValueError:
            pass
        else:
            raise AssertionError(f"invalid request accepted: {changes!r}")


def test_payload_builder_requires_stop_prices_for_stop_types():
    for order_type, limit_price in (("SL", 99.0), ("SL-M", None)):
        req = BrokerOrderRequest(symbol="NSE_FO|123", side="SELL", qty=25,
                                 order_type=order_type, limit_price=limit_price)
        try:
            UpstoxBrokerAdapter.build_order_payload(req)
        except ValueError as exc:
            assert "stop_price" in str(exc)
        else:
            raise AssertionError(f"{order_type} without trigger must be rejected")

    sl = BrokerOrderRequest(symbol="NSE_FO|123", side="SELL", qty=25,
                            order_type="SL", limit_price=99.0, stop_price=100.0)
    payload = UpstoxBrokerAdapter.build_order_payload(sl)
    assert payload["price"] == 99.0
    assert payload["trigger_price"] == 100.0
