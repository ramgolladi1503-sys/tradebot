from __future__ import annotations

from core.broker_reconciliation_dry_run_proof import (
    BROKER_RECON_DRY_RUN_BLOCKED,
    BROKER_RECON_DRY_RUN_PROVEN,
    build_broker_reconciliation_dry_run_proof,
)
from core.live_dry_run_broker_payload_gate import build_live_dry_run_broker_payload_gate_report


def _payload(**overrides):
    payload = {
        "payload_id": "dry-run-1",
        "dry_run": True,
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


def _gate_report(**overrides):
    return build_live_dry_run_broker_payload_gate_report(_payload(**overrides)).to_dict()


def _receipt(**overrides):
    payload = {
        "payload_id": "dry-run-1",
        "dry_run": True,
        "broker_order_action": False,
        "live_order_action": False,
        "is_order_action": False,
        "append": False,
        "submitted": False,
        "broker_order_id": None,
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


def test_matching_approved_gate_and_dry_run_receipt_are_proven():
    proof = build_broker_reconciliation_dry_run_proof(
        gate_report=_gate_report(),
        broker_receipt=_receipt(),
    )

    assert proof.state == BROKER_RECON_DRY_RUN_PROVEN
    assert proof.read_only is True
    assert proof.dry_run is True
    assert proof.is_order_action is False
    assert proof.append is False
    assert proof.broker_order_action is False
    assert proof.live_order_action is False
    assert proof.payload_id == "dry-run-1"
    assert proof.blockers == ()
    assert proof.mismatched_fields == ()
    assert proof.missing_receipt_fields == ()
    assert proof.field_comparison["tradingsymbol"]["matched"] is True


def test_blocked_gate_blocks_reconciliation_proof():
    proof = build_broker_reconciliation_dry_run_proof(
        gate_report=_gate_report(dry_run=False),
        broker_receipt=_receipt(),
    )

    assert proof.state == BROKER_RECON_DRY_RUN_BLOCKED
    assert "GATE_REPORT_NOT_APPROVED" in proof.blockers
    assert "DRY_RUN_REQUIRED" in proof.blockers


def test_missing_receipt_blocks_reconciliation_proof():
    proof = build_broker_reconciliation_dry_run_proof(
        gate_report=_gate_report(),
        broker_receipt=None,
    )

    assert proof.state == BROKER_RECON_DRY_RUN_BLOCKED
    assert "BROKER_RECEIPT_MISSING" in proof.blockers
    assert "BROKER_RECEIPT_FIELDS_MISSING" in proof.blockers
    assert "tradingsymbol" in proof.missing_receipt_fields


def test_receipt_mismatch_blocks_reconciliation_proof():
    proof = build_broker_reconciliation_dry_run_proof(
        gate_report=_gate_report(),
        broker_receipt=_receipt(tradingsymbol="BANKNIFTY26MAY50000CE", quantity=25),
    )

    assert proof.state == BROKER_RECON_DRY_RUN_BLOCKED
    assert "BROKER_RECEIPT_FIELD_MISMATCH" in proof.blockers
    assert proof.mismatched_fields == ("quantity", "tradingsymbol")
    assert proof.field_comparison["quantity"]["expected"] == 75
    assert proof.field_comparison["quantity"]["actual"] == 25


def test_receipt_missing_required_field_blocks_reconciliation_proof():
    receipt = _receipt()
    receipt.pop("validity")

    proof = build_broker_reconciliation_dry_run_proof(
        gate_report=_gate_report(),
        broker_receipt=receipt,
    )

    assert proof.state == BROKER_RECON_DRY_RUN_BLOCKED
    assert "BROKER_RECEIPT_FIELDS_MISSING" in proof.blockers
    assert proof.missing_receipt_fields == ("validity",)


def test_real_order_indicators_are_rejected():
    proof = build_broker_reconciliation_dry_run_proof(
        gate_report=_gate_report(),
        broker_receipt=_receipt(
            broker_order_action=True,
            live_order_action=True,
            is_order_action=True,
            append=True,
            submitted=True,
            broker_order_id="REAL-ORDER-1",
        ),
    )

    assert proof.state == BROKER_RECON_DRY_RUN_BLOCKED
    assert "BROKER_RECEIPT_BROKER_ORDER_ACTION_REJECTED" in proof.blockers
    assert "BROKER_RECEIPT_LIVE_ORDER_ACTION_REJECTED" in proof.blockers
    assert "BROKER_RECEIPT_ORDER_ACTION_REJECTED" in proof.blockers
    assert "BROKER_RECEIPT_APPEND_TRUE_REJECTED" in proof.blockers
    assert "BROKER_RECEIPT_SUBMITTED_TRUE_REJECTED" in proof.blockers
    assert "BROKER_RECEIPT_ORDER_ID_PRESENT" in proof.blockers


def test_gate_action_flags_are_rejected_even_if_receipt_matches():
    gate = _gate_report()
    gate["broker_order_action"] = True
    gate["live_order_action"] = True
    gate["is_order_action"] = True
    gate["append"] = True

    proof = build_broker_reconciliation_dry_run_proof(gate_report=gate, broker_receipt=_receipt())

    assert proof.state == BROKER_RECON_DRY_RUN_BLOCKED
    assert "GATE_REPORT_BROKER_ORDER_ACTION_REJECTED" in proof.blockers
    assert "GATE_REPORT_LIVE_ORDER_ACTION_REJECTED" in proof.blockers
    assert "GATE_REPORT_ORDER_ACTION_REJECTED" in proof.blockers
    assert "GATE_REPORT_APPEND_TRUE_REJECTED" in proof.blockers


def test_to_dict_is_json_friendly_and_stable():
    payload = build_broker_reconciliation_dry_run_proof(
        gate_report=_gate_report(),
        broker_receipt=_receipt(),
    ).to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == BROKER_RECON_DRY_RUN_PROVEN
    assert payload["read_only"] is True
    assert payload["dry_run"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["broker_order_action"] is False
    assert payload["live_order_action"] is False
    assert "tradingsymbol" in payload["reconciled_fields"]
    assert payload["metadata"]["proof"] == "broker_reconciliation_dry_run_proof_v1"
    assert payload["metadata"]["scope"] == "read_only_no_broker_calls_no_order_submission_no_runtime_wiring"
