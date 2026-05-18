from __future__ import annotations

from datetime import datetime, timezone
import json

from core.agent_approval import approve_agent_scope
from core.agent_evidence import (
    AGENT_EVIDENCE_SCHEMA_VERSION,
    build_agent_evidence_payload,
    write_agent_evidence,
)
from core.agent_scope_guard import assess_agent_scope
from core.agent_work_contract import AGENT_WORK_SCHEMA_VERSION, normalize_agent_work_request


def _request(**overrides):
    payload = {
        "schema_version": AGENT_WORK_SCHEMA_VERSION,
        "source_agent": "gsd",
        "action": "GENERATE_TESTS",
        "title": "Add scope guard tests",
        "scope": "Add behavior tests for agent scope validation.",
        "requested_paths": ["tests/test_agent_scope_guard.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": ["credentials.py", ".env", "core/broker"],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
    }
    payload.update(overrides)
    return normalize_agent_work_request(payload)


def _decisions():
    request = _request()
    scope_decision = assess_agent_scope(request)
    approval_decision = approve_agent_scope(scope_decision)
    return request, scope_decision, approval_decision


def test_build_evidence_payload_is_json_safe_and_read_only():
    request, scope_decision, approval_decision = _decisions()
    payload = build_agent_evidence_payload(
        request=request,
        scope_decision=scope_decision,
        approval_decision=approval_decision,
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
    )

    assert payload["schema_version"] == AGENT_EVIDENCE_SCHEMA_VERSION
    assert payload["created_at"] == "2026-05-18T12:00:00Z"
    assert payload["request"]["source_agent"] == "gsd"
    assert payload["scope_decision"]["read_only"] is True
    assert payload["approval_decision"]["allowed_for_patch"] is True
    assert payload["safety"] == {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "live_mode_touched": False,
        "allowed_for_live_execution": False,
    }
    json.dumps(payload, sort_keys=True)


def test_write_agent_evidence_writes_latest_and_journal(tmp_path):
    request, scope_decision, approval_decision = _decisions()
    result = write_agent_evidence(
        request=request,
        scope_decision=scope_decision,
        approval_decision=approval_decision,
        root_dir=tmp_path,
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
    )

    latest_path = tmp_path / "agent_work_latest.json"
    journal_path = tmp_path / "agent_work_2026-05-18.jsonl"

    assert result.latest_path == str(latest_path)
    assert result.journal_path == str(journal_path)
    assert result.read_only is True
    assert result.is_order_action is False
    assert result.broker_api_called is False
    assert result.live_mode_touched is False
    assert result.allowed_for_live_execution is False

    latest_payload = json.loads(latest_path.read_text(encoding="utf-8"))
    journal_lines = journal_path.read_text(encoding="utf-8").splitlines()

    assert len(journal_lines) == 1
    assert json.loads(journal_lines[0]) == latest_payload
    assert latest_payload["request"]["title"] == "Add scope guard tests"
    assert latest_payload["approval_decision"]["approved"] is True
    assert latest_payload["safety"]["read_only"] is True


def test_write_agent_evidence_appends_journal_and_replaces_latest(tmp_path):
    request, scope_decision, approval_decision = _decisions()

    write_agent_evidence(
        request=request,
        scope_decision=scope_decision,
        approval_decision=approval_decision,
        root_dir=tmp_path,
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
    )
    second_request = _request(title="Second agent request")
    second_scope = assess_agent_scope(second_request)
    second_approval = approve_agent_scope(second_scope)
    write_agent_evidence(
        request=second_request,
        scope_decision=second_scope,
        approval_decision=second_approval,
        root_dir=tmp_path,
        created_at=datetime(2026, 5, 18, 12, 1, tzinfo=timezone.utc),
    )

    latest_payload = json.loads((tmp_path / "agent_work_latest.json").read_text(encoding="utf-8"))
    journal_lines = (tmp_path / "agent_work_2026-05-18.jsonl").read_text(encoding="utf-8").splitlines()

    assert len(journal_lines) == 2
    assert latest_payload["request"]["title"] == "Second agent request"
    assert json.loads(journal_lines[0])["request"]["title"] == "Add scope guard tests"
    assert json.loads(journal_lines[1])["request"]["title"] == "Second agent request"


def test_write_agent_evidence_can_record_rejected_approval(tmp_path):
    request = _request(source_agent="grill_me", action="GENERATE_PATCH")
    scope_decision = assess_agent_scope(request)
    approval_decision = approve_agent_scope(scope_decision, human_approved=True, approved_by="ram")

    result = write_agent_evidence(
        request=request,
        scope_decision=scope_decision,
        approval_decision=approval_decision,
        root_dir=tmp_path,
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
    )

    payload = json.loads((tmp_path / "agent_work_latest.json").read_text(encoding="utf-8"))
    assert approval_decision.approved is False
    assert payload["scope_decision"]["accepted"] is False
    assert payload["approval_decision"]["approved"] is False
    assert result.allowed_for_live_execution is False


def test_result_to_dict_is_json_friendly(tmp_path):
    request, scope_decision, approval_decision = _decisions()
    result = write_agent_evidence(
        request=request,
        scope_decision=scope_decision,
        approval_decision=approval_decision,
        root_dir=tmp_path,
        created_at=datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc),
    )
    payload = result.to_dict()

    assert payload["schema_version"] == AGENT_EVIDENCE_SCHEMA_VERSION
    assert payload["read_only"] is True
    assert payload["allowed_for_live_execution"] is False
    assert payload["metadata"]["contract"] == "agent_evidence_write_result_v1"
    json.dumps(payload, sort_keys=True)
