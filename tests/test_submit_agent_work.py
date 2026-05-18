from __future__ import annotations

import json

from scripts.submit_agent_work import (
    CLI_APPROVAL_REJECTED,
    CLI_CONTRACT_OR_SCOPE_BLOCKED,
    CLI_OK,
    CLI_PAYLOAD_ERROR,
    main,
    submit_agent_work_payload,
)


def _payload(**overrides):
    payload = {
        "schema_version": 1,
        "source_agent": "gsd",
        "action": "GENERATE_TESTS",
        "title": "Add agent scope guard tests",
        "scope": "Add behavior tests for safe agent scope validation.",
        "requested_paths": ["tests/test_agent_scope_guard.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": ["credentials.py", ".env", "core/broker"],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
    }
    payload.update(overrides)
    return payload


def test_submit_payload_approves_low_risk_work_and_writes_evidence(tmp_path):
    exit_code, result = submit_agent_work_payload(_payload(), evidence_root=tmp_path)

    assert exit_code == CLI_OK
    assert result["contract_decision"]["accepted"] is True
    assert result["scope_decision"]["accepted"] is True
    assert result["approval_decision"]["approved"] is True
    assert result["approval_decision"]["allowed_for_patch"] is True
    assert result["safety"]["read_only"] is True
    assert result["safety"]["is_order_action"] is False
    assert result["safety"]["broker_api_called"] is False
    assert result["safety"]["live_mode_touched"] is False
    assert result["safety"]["allowed_for_live_execution"] is False
    assert result["evidence_result"]["latest_path"] == str(tmp_path / "agent_work_latest.json")
    assert (tmp_path / "agent_work_latest.json").exists()
    assert list(tmp_path.glob("agent_work_*.jsonl"))


def test_submit_payload_blocks_contract_failure_without_evidence_when_disabled():
    exit_code, result = submit_agent_work_payload(
        _payload(action="PLACE_ORDER"),
        write_evidence=False,
    )

    assert exit_code == CLI_CONTRACT_OR_SCOPE_BLOCKED
    assert result["contract_decision"]["accepted"] is False
    assert result["scope_decision"]["accepted"] is False
    assert result["approval_decision"]["approved"] is False
    assert result["evidence_result"] is None
    assert "ACTION_FORBIDDEN" in result["contract_decision"]["blockers"]


def test_submit_payload_rejects_high_risk_work_without_human_approval(tmp_path):
    exit_code, result = submit_agent_work_payload(
        _payload(
            action="GENERATE_PATCH",
            requested_paths=["core/risk/position_sizing.py"],
            allowed_paths=["core/risk/"],
            forbidden_paths=["credentials.py", ".env"],
        ),
        evidence_root=tmp_path,
    )

    assert exit_code == CLI_APPROVAL_REJECTED
    assert result["contract_decision"]["accepted"] is True
    assert result["scope_decision"]["accepted"] is True
    assert result["scope_decision"]["requires_human_approval"] is True
    assert result["approval_decision"]["approved"] is False
    assert "HUMAN_APPROVAL_REQUIRED" in result["approval_decision"]["blockers"]
    assert (tmp_path / "agent_work_latest.json").exists()


def test_submit_payload_approves_high_risk_patch_with_explicit_approver(tmp_path):
    exit_code, result = submit_agent_work_payload(
        _payload(
            action="GENERATE_PATCH",
            requested_paths=["core/risk/position_sizing.py"],
            allowed_paths=["core/risk/"],
            forbidden_paths=["credentials.py", ".env"],
        ),
        human_approved=True,
        approved_by="ram",
        evidence_root=tmp_path,
    )

    assert exit_code == CLI_OK
    assert result["approval_decision"]["approved"] is True
    assert result["approval_decision"]["approved_by"] == "ram"
    assert result["approval_decision"]["allowed_for_patch"] is True
    assert result["approval_decision"]["allowed_for_runtime_wiring"] is False
    assert result["approval_decision"]["allowed_for_live_execution"] is False


def test_main_prints_json_and_returns_success(tmp_path, capsys):
    payload_path = tmp_path / "payload.json"
    evidence_root = tmp_path / "evidence"
    payload_path.write_text(json.dumps(_payload()), encoding="utf-8")

    exit_code = main(["--payload", str(payload_path), "--evidence-root", str(evidence_root)])
    captured = capsys.readouterr()
    printed = json.loads(captured.out)

    assert exit_code == CLI_OK
    assert printed["approval_decision"]["approved"] is True
    assert printed["evidence_result"]["latest_path"] == str(evidence_root / "agent_work_latest.json")


def test_main_returns_payload_error_for_invalid_json(tmp_path, capsys):
    payload_path = tmp_path / "bad.json"
    payload_path.write_text("not-json", encoding="utf-8")

    exit_code = main(["--payload", str(payload_path), "--no-evidence"])
    captured = capsys.readouterr()
    printed = json.loads(captured.out)

    assert exit_code == CLI_PAYLOAD_ERROR
    assert printed["error"].startswith("failed_to_read_payload:")
    assert printed["safety"]["read_only"] is True
    assert printed["safety"]["allowed_for_live_execution"] is False


def test_main_returns_blocked_for_forbidden_action(tmp_path, capsys):
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(_payload(action="ENABLE_LIVE")), encoding="utf-8")

    exit_code = main(["--payload", str(payload_path), "--no-evidence"])
    captured = capsys.readouterr()
    printed = json.loads(captured.out)

    assert exit_code == CLI_CONTRACT_OR_SCOPE_BLOCKED
    assert printed["contract_decision"]["accepted"] is False
    assert "ACTION_FORBIDDEN" in printed["contract_decision"]["blockers"]
    assert printed["approval_decision"]["allowed_for_live_execution"] is False
