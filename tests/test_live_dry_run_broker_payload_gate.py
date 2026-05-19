from __future__ import annotations

from core.live_dry_run_broker_payload_gate import (
    BROKER_PAYLOAD_DRY_RUN_APPROVED,
    BROKER_PAYLOAD_DRY_RUN_BLOCKED,
    build_live_dry_run_broker_payload_gate_report,
)


def _payload(**overrides):
    payload = {
        "payload_id": "dry-run-1",
        "dry_run": True,
        "read_only": True,
        "broker_order_action": False,
        "live_order_action": False,
        "is_order_action": False,
        "append": False,
        "exchange": "NFO",
        "tradingsymbol": "NIFTY26MAY22500CE",
        "transaction_type": "BUY",
        "order_type": "MARKET",
        "product": "MIS",
        "variety": "regular",
        "validity": "DAY",
        "quantity": 75,
        "price": 0.0,
        "trigger_price": None,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_valid_market_dry_run_payload_is_approved_without_order_action():
    report = build_live_dry_run_broker_payload_gate_report(_payload())

    assert report.state == BROKER_PAYLOAD_DRY_RUN_APPROVED
    assert report.read_only is True
    assert report.dry_run is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.broker_order_action is False
    assert report.live_order_action is False
    assert report.payload_id == "dry-run-1"
    assert report.exchange == "NFO"
    assert report.order_type == "MARKET"
    assert report.quantity == 75
    assert report.blockers == ()
    assert report.normalized_payload["is_order_action"] is False


def test_valid_limit_dry_run_payload_requires_positive_price():
    report = build_live_dry_run_broker_payload_gate_report(_payload(order_type="LIMIT", price=101.25))

    assert report.state == BROKER_PAYLOAD_DRY_RUN_APPROVED
    assert report.price == 101.25
    assert report.blockers == ()


def test_valid_stoploss_payload_requires_trigger_price():
    report = build_live_dry_run_broker_payload_gate_report(_payload(order_type="SL-M", trigger_price=95.5))

    assert report.state == BROKER_PAYLOAD_DRY_RUN_APPROVED
    assert report.trigger_price == 95.5


def test_missing_payload_fails_closed():
    report = build_live_dry_run_broker_payload_gate_report(None)

    assert report.state == BROKER_PAYLOAD_DRY_RUN_BLOCKED
    assert "BROKER_PAYLOAD_MISSING" in report.blockers
    assert "DRY_RUN_REQUIRED" in report.blockers
    assert "PAYLOAD_ID_MISSING" in report.blockers
    assert "EXCHANGE_MISSING" in report.blockers
    assert "TRADINGSYMBOL_MISSING" in report.blockers
    assert "QUANTITY_MISSING" in report.blockers


def test_live_or_order_action_flags_are_rejected():
    report = build_live_dry_run_broker_payload_gate_report(
        _payload(
            broker_order_action=True,
            live_order_action=True,
            is_order_action=True,
            append=True,
        )
    )

    assert report.state == BROKER_PAYLOAD_DRY_RUN_BLOCKED
    assert "BROKER_ORDER_ACTION_REJECTED" in report.blockers
    assert "LIVE_ORDER_ACTION_REJECTED" in report.blockers
    assert "ORDER_ACTION_REJECTED" in report.blockers
    assert "APPEND_TRUE_REJECTED" in report.blockers


def test_non_dry_run_payload_is_rejected():
    report = build_live_dry_run_broker_payload_gate_report(_payload(dry_run=False))

    assert report.state == BROKER_PAYLOAD_DRY_RUN_BLOCKED
    assert "DRY_RUN_REQUIRED" in report.blockers


def test_invalid_required_broker_fields_fail_closed():
    report = build_live_dry_run_broker_payload_gate_report(
        _payload(
            exchange="NSE",
            transaction_type="HOLD",
            order_type="BOGUS",
            product="CNC",
            variety="co",
            validity="GTC",
            quantity=0,
        )
    )

    assert report.state == BROKER_PAYLOAD_DRY_RUN_BLOCKED
    assert "EXCHANGE_UNSUPPORTED" in report.blockers
    assert "TRANSACTION_TYPE_UNSUPPORTED" in report.blockers
    assert "ORDER_TYPE_UNSUPPORTED" in report.blockers
    assert "PRODUCT_UNSUPPORTED" in report.blockers
    assert "VARIETY_UNSUPPORTED" in report.blockers
    assert "VALIDITY_UNSUPPORTED" in report.blockers
    assert "QUANTITY_NON_POSITIVE" in report.blockers


def test_market_price_must_not_be_positive():
    report = build_live_dry_run_broker_payload_gate_report(_payload(order_type="MARKET", price=100.0))

    assert report.state == BROKER_PAYLOAD_DRY_RUN_BLOCKED
    assert "MARKET_PRICE_MUST_BE_EMPTY_OR_ZERO" in report.blockers


def test_limit_price_is_required():
    report = build_live_dry_run_broker_payload_gate_report(_payload(order_type="LIMIT", price=0.0))

    assert report.state == BROKER_PAYLOAD_DRY_RUN_BLOCKED
    assert "LIMIT_PRICE_REQUIRED" in report.blockers


def test_stoploss_trigger_price_is_required():
    report = build_live_dry_run_broker_payload_gate_report(_payload(order_type="SL", trigger_price=0.0))

    assert report.state == BROKER_PAYLOAD_DRY_RUN_BLOCKED
    assert "STOPLOSS_TRIGGER_PRICE_REQUIRED" in report.blockers


def test_upstream_blockers_are_preserved():
    report = build_live_dry_run_broker_payload_gate_report(_payload(blockers=["risk_gate_blocked"]))

    assert report.state == BROKER_PAYLOAD_DRY_RUN_BLOCKED
    assert "RISK_GATE_BLOCKED" in report.blockers


def test_to_dict_is_json_friendly_and_stable():
    payload = build_live_dry_run_broker_payload_gate_report(_payload()).to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == BROKER_PAYLOAD_DRY_RUN_APPROVED
    assert payload["read_only"] is True
    assert payload["dry_run"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["broker_order_action"] is False
    assert payload["live_order_action"] is False
    assert payload["normalized_payload"]["broker_order_action"] is False
    assert payload["metadata"]["gate"] == "live_dry_run_broker_payload_gate_v1"
    assert payload["metadata"]["scope"] == "read_only_no_broker_calls_no_order_submission_no_runtime_wiring"
