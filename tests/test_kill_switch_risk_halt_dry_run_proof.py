from __future__ import annotations

from core.broker_reconciliation_dry_run_proof import build_broker_reconciliation_dry_run_proof
from core.kill_switch_risk_halt_dry_run_proof import (
    KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED,
    KILL_SWITCH_RISK_HALT_DRY_RUN_PROVEN,
    build_kill_switch_risk_halt_dry_run_proof,
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


def _recon(**payload_overrides):
    gate = build_live_dry_run_broker_payload_gate_report(_payload(**payload_overrides)).to_dict()
    return build_broker_reconciliation_dry_run_proof(
        gate_report=gate,
        broker_receipt=_receipt(**payload_overrides),
    ).to_dict()


def _safety(**overrides):
    payload = {
        "payload_id": "dry-run-1",
        "read_only": True,
        "dry_run": True,
        "broker_order_action": False,
        "live_order_action": False,
        "is_order_action": False,
        "append": False,
        "kill_switch_active": True,
        "risk_halt_active": False,
        "halt_reason": "manual_kill_switch",
        "proof_mode": "ASSERT_BLOCKED",
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_kill_switch_active_assert_blocked_is_proven_without_order_action():
    proof = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=_recon(),
        safety_evidence=_safety(kill_switch_active=True, risk_halt_active=False),
    )

    assert proof.state == KILL_SWITCH_RISK_HALT_DRY_RUN_PROVEN
    assert proof.read_only is True
    assert proof.dry_run is True
    assert proof.is_order_action is False
    assert proof.append is False
    assert proof.broker_order_action is False
    assert proof.live_order_action is False
    assert proof.payload_id == "dry-run-1"
    assert proof.kill_switch_active is True
    assert proof.risk_halt_active is False
    assert proof.halt_reason == "manual_kill_switch"
    assert proof.blockers == ()


def test_risk_halt_active_assert_blocked_is_proven():
    proof = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=_recon(),
        safety_evidence=_safety(kill_switch_active=False, risk_halt_active=True, halt_reason="risk_limit_hit"),
    )

    assert proof.state == KILL_SWITCH_RISK_HALT_DRY_RUN_PROVEN
    assert proof.kill_switch_active is False
    assert proof.risk_halt_active is True
    assert proof.halt_reason == "risk_limit_hit"


def test_clear_state_assert_clear_is_proven():
    proof = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=_recon(),
        safety_evidence=_safety(
            kill_switch_active=False,
            risk_halt_active=False,
            halt_reason=None,
            proof_mode="ASSERT_CLEAR",
        ),
    )

    assert proof.state == KILL_SWITCH_RISK_HALT_DRY_RUN_PROVEN
    assert proof.proof_mode == "ASSERT_CLEAR"
    assert proof.kill_switch_active is False
    assert proof.risk_halt_active is False
    assert proof.blockers == ()


def test_assert_blocked_fails_when_no_halt_is_active():
    proof = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=_recon(),
        safety_evidence=_safety(kill_switch_active=False, risk_halt_active=False, halt_reason="manual_kill_switch"),
    )

    assert proof.state == KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED
    assert "EXPECTED_HALT_NOT_ACTIVE" in proof.blockers


def test_assert_clear_fails_when_halt_is_active():
    proof = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=_recon(),
        safety_evidence=_safety(kill_switch_active=True, risk_halt_active=False, proof_mode="ASSERT_CLEAR"),
    )

    assert proof.state == KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED
    assert "EXPECTED_CLEAR_BUT_HALT_ACTIVE" in proof.blockers


def test_missing_safety_signals_fail_closed():
    safety = _safety()
    safety.pop("kill_switch_active")
    safety.pop("risk_halt_active")

    proof = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=_recon(),
        safety_evidence=safety,
    )

    assert proof.state == KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED
    assert "KILL_SWITCH_SIGNAL_MISSING" in proof.blockers
    assert "RISK_HALT_SIGNAL_MISSING" in proof.blockers


def test_blocked_reconciliation_proof_blocks_halt_proof():
    recon = _recon(dry_run=False)
    proof = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=recon,
        safety_evidence=_safety(),
    )

    assert proof.state == KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED
    assert "RECONCILIATION_PROOF_NOT_PROVEN" in proof.blockers
    assert "DRY_RUN_REQUIRED" in proof.blockers


def test_safety_action_flags_are_rejected():
    proof = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=_recon(),
        safety_evidence=_safety(
            broker_order_action=True,
            live_order_action=True,
            is_order_action=True,
            append=True,
        ),
    )

    assert proof.state == KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED
    assert "SAFETY_EVIDENCE_BROKER_ORDER_ACTION_REJECTED" in proof.blockers
    assert "SAFETY_EVIDENCE_LIVE_ORDER_ACTION_REJECTED" in proof.blockers
    assert "SAFETY_EVIDENCE_ORDER_ACTION_REJECTED" in proof.blockers
    assert "SAFETY_EVIDENCE_APPEND_TRUE_REJECTED" in proof.blockers


def test_payload_id_mismatch_blocks_proof():
    proof = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=_recon(),
        safety_evidence=_safety(payload_id="other-payload"),
    )

    assert proof.state == KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED
    assert "PAYLOAD_ID_MISMATCH" in proof.blockers


def test_to_dict_is_json_friendly_and_stable():
    payload = build_kill_switch_risk_halt_dry_run_proof(
        reconciliation_proof=_recon(),
        safety_evidence=_safety(),
    ).to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == KILL_SWITCH_RISK_HALT_DRY_RUN_PROVEN
    assert payload["read_only"] is True
    assert payload["dry_run"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["broker_order_action"] is False
    assert payload["live_order_action"] is False
    assert payload["metadata"]["proof"] == "kill_switch_risk_halt_dry_run_proof_v1"
    assert payload["metadata"]["scope"] == "read_only_no_broker_calls_no_order_submission_no_runtime_wiring"
