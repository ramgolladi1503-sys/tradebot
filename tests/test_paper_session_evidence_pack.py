from __future__ import annotations

import pytest

from core.paper_session_evidence_pack import (
    EVIDENCE_PACK_BLOCKED,
    EVIDENCE_PACK_READY,
    PaperSessionEvidencePackError,
    build_paper_session_evidence_pack,
)


def _gate(**overrides):
    payload = {
        "schema_version": 1,
        "state": "SESSION_GATE_PASS",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "broker_order_action": False,
        "live_order_action": False,
        "session_id": "paper-session-1",
        "evidence_complete": True,
        "paper_order_count": 2,
        "paper_fill_count": 1,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _ledger(**overrides):
    payload = {
        "schema_version": 1,
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "broker_order_action": False,
        "live_order_action": False,
        "risk_halt_active": False,
        "daily_realized_pnl": 25.0,
        "daily_trade_count": 1,
        "open_position_count": 0,
        "current_exposure": 0.0,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def _decision(**overrides):
    payload = {
        "schema_version": 1,
        "state": "PAPER_DECISION_APPROVED",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "allowed_for_paper_order": True,
        "allowed_for_live_execution": False,
        "paper_intent_id": "intent-1",
    }
    payload.update(overrides)
    return payload


def _order(**overrides):
    payload = {
        "schema_version": 1,
        "paper_order_id": "paper-1",
        "paper_intent_id": "intent-1",
        "broker_order_action": False,
        "live_order_action": False,
        "state": "FILLED",
    }
    payload.update(overrides)
    return payload


def _fill(**overrides):
    payload = {
        "schema_version": 1,
        "state": "FILL_APPROVED",
        "approved": True,
        "broker_order_action": False,
        "live_order_action": False,
        "is_order_action": False,
        "append": False,
        "fill_price": 101.0,
    }
    payload.update(overrides)
    return payload


def test_ready_evidence_pack_includes_all_supplied_sections():
    pack = build_paper_session_evidence_pack(
        session_gate_report=_gate(),
        risk_ledger_snapshot=_ledger(),
        paper_decision_reports=[_decision()],
        paper_order_records=[_order()],
        fill_decisions=[_fill()],
        extra_artifacts={"run_notes": {"summary": "clean paper session"}},
    )

    assert pack.state == EVIDENCE_PACK_READY
    assert pack.read_only is True
    assert pack.is_order_action is False
    assert pack.append is False
    assert pack.broker_order_action is False
    assert pack.live_order_action is False
    assert pack.session_id == "paper-session-1"
    assert pack.evidence_complete is True
    assert pack.artifact_count == 6
    assert pack.blockers == ()
    assert "session_gate_report" in pack.evidence
    assert "risk_ledger_snapshot" in pack.evidence
    assert pack.evidence["paper_decision_reports"][0]["paper_intent_id"] == "intent-1"


def test_gate_failure_blocks_evidence_pack():
    pack = build_paper_session_evidence_pack(
        session_gate_report=_gate(state="SESSION_GATE_FAIL", blockers=["FALLBACK_PAPER_FILLS_PRESENT"]),
        risk_ledger_snapshot=_ledger(),
    )

    assert pack.state == EVIDENCE_PACK_BLOCKED
    assert pack.evidence_complete is False
    assert "SESSION_GATE_NOT_PASS" in pack.blockers
    assert "FALLBACK_PAPER_FILLS_PRESENT" in pack.blockers


def test_missing_ledger_blocks_evidence_pack():
    pack = build_paper_session_evidence_pack(session_gate_report=_gate(), risk_ledger_snapshot=None)

    assert pack.state == EVIDENCE_PACK_BLOCKED
    assert "RISK_LEDGER_SNAPSHOT_MISSING" in pack.blockers


def test_risk_halt_blocks_evidence_pack():
    pack = build_paper_session_evidence_pack(
        session_gate_report=_gate(),
        risk_ledger_snapshot=_ledger(risk_halt_active=True),
    )

    assert pack.state == EVIDENCE_PACK_BLOCKED
    assert "RISK_LEDGER_HALT_ACTIVE" in pack.blockers


def test_unsafe_flags_in_nested_reports_are_rejected():
    pack = build_paper_session_evidence_pack(
        session_gate_report=_gate(),
        risk_ledger_snapshot=_ledger(),
        paper_decision_reports=[_decision(is_order_action=True, append=True)],
        paper_order_records=[_order(broker_order_action=True)],
        fill_decisions=[_fill(live_order_action=True)],
    )

    assert pack.state == EVIDENCE_PACK_BLOCKED
    assert "PAPER_DECISION_REPORTS_0_ORDER_ACTION_REJECTED" in pack.blockers
    assert "PAPER_DECISION_REPORTS_0_APPEND_TRUE_REJECTED" in pack.blockers
    assert "PAPER_ORDER_RECORDS_0_BROKER_ORDER_ACTION_REJECTED" in pack.blockers
    assert "FILL_DECISIONS_0_LIVE_ORDER_ACTION_REJECTED" in pack.blockers


def test_count_mismatches_block_pack():
    pack = build_paper_session_evidence_pack(
        session_gate_report=_gate(paper_order_count=1, paper_fill_count=0),
        risk_ledger_snapshot=_ledger(),
        paper_order_records=[_order(paper_order_id="paper-1"), _order(paper_order_id="paper-2")],
        fill_decisions=[_fill()],
    )

    assert pack.state == EVIDENCE_PACK_BLOCKED
    assert "EVIDENCE_ORDERS_EXCEED_GATE_ORDER_COUNT" in pack.blockers
    assert "EVIDENCE_FILLS_EXCEED_GATE_FILL_COUNT" in pack.blockers


def test_optional_sections_must_be_lists():
    pack = build_paper_session_evidence_pack(
        session_gate_report=_gate(),
        risk_ledger_snapshot=_ledger(),
        paper_decision_reports={"not": "a-list"},
    )

    assert pack.state == EVIDENCE_PACK_BLOCKED
    assert "PAPER_DECISION_REPORTS_NOT_A_LIST" in pack.blockers


def test_extra_artifacts_must_be_mapping():
    with pytest.raises(PaperSessionEvidencePackError) as exc_info:
        build_paper_session_evidence_pack(
            session_gate_report=_gate(),
            risk_ledger_snapshot=_ledger(),
            extra_artifacts=["bad"],
        )

    assert "extra_artifacts_must_be_mapping" in str(exc_info.value)


def test_to_dict_is_json_friendly_and_stable():
    pack = build_paper_session_evidence_pack(
        session_gate_report=_gate(),
        risk_ledger_snapshot=_ledger(),
        paper_decision_reports=[_decision()],
    )
    payload = pack.to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == EVIDENCE_PACK_READY
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["broker_order_action"] is False
    assert payload["live_order_action"] is False
    assert payload["section_names"] == [
        "extra_artifacts",
        "fill_decisions",
        "paper_decision_reports",
        "paper_order_records",
        "risk_ledger_snapshot",
        "session_gate_report",
    ]
    assert payload["metadata"]["evidence_pack"] == "paper_session_evidence_pack_v1"
    assert payload["metadata"]["scope"] == "read_only_no_runtime_wiring_no_broker_calls_no_order_mutation_no_persistence"
