from __future__ import annotations

from core.agent_work_contract import (
    AGENT_WORK_CONTRACT_BLOCKED,
    AGENT_WORK_CONTRACT_VALID,
    AGENT_WORK_SCHEMA_VERSION,
    build_agent_work_id,
    normalize_agent_work_request,
    validate_agent_work_contract,
)


def _payload(**overrides):
    payload = {
        "schema_version": AGENT_WORK_SCHEMA_VERSION,
        "source_agent": "gsd",
        "action": "GENERATE_TESTS",
        "title": "Add agent scope guard tests",
        "scope": "Add behavior tests proving forbidden actions and unsafe paths are blocked.",
        "requested_paths": ["tests/test_agent_scope_guard.py"],
        "allowed_paths": ["tests/"],
        "forbidden_paths": ["credentials.py", ".env", "core/broker"],
        "requires_human_approval": False,
        "metadata": {"project": "tradebot"},
    }
    payload.update(overrides)
    return payload


def test_valid_gsd_test_generation_contract_is_accepted_but_not_approved_for_patch():
    request = normalize_agent_work_request(_payload())
    decision = validate_agent_work_contract(request)

    assert decision.state == AGENT_WORK_CONTRACT_VALID
    assert decision.accepted is True
    assert decision.work_id is not None
    assert len(decision.work_id) == 24
    assert decision.source_agent == "gsd"
    assert decision.action == "GENERATE_TESTS"
    assert decision.read_only is True
    assert decision.is_order_action is False
    assert decision.broker_api_called is False
    assert decision.live_mode_touched is False
    assert decision.allowed_for_patch is False
    assert decision.allowed_for_runtime_wiring is False
    assert decision.allowed_for_live_execution is False
    assert decision.requires_human_approval is True
    assert decision.blockers == ()
    assert "agent_work_contract_valid" in decision.reasons


def test_normalization_handles_source_and_action_spelling_variants():
    request = normalize_agent_work_request(
        _payload(source_agent="Grill-Me", action="critique scope", requires_human_approval="false")
    )

    assert request.source_agent == "grill_me"
    assert request.action == "CRITIQUE_SCOPE"
    assert request.requires_human_approval is False


def test_work_id_is_deterministic_for_same_identity_fields():
    first = normalize_agent_work_request(_payload(metadata={"trace": "first"}))
    second = normalize_agent_work_request(_payload(metadata={"trace": "second"}))

    assert build_agent_work_id(first) == build_agent_work_id(second)
    assert validate_agent_work_contract(first).work_id == validate_agent_work_contract(second).work_id


def test_unknown_source_blocks_contract():
    request = normalize_agent_work_request(_payload(source_agent="random_agent"))
    decision = validate_agent_work_contract(request)

    assert decision.state == AGENT_WORK_CONTRACT_BLOCKED
    assert decision.accepted is False
    assert decision.work_id is None
    assert "SOURCE_AGENT_UNKNOWN" in decision.blockers


def test_unknown_action_blocks_contract():
    request = normalize_agent_work_request(_payload(action="MAKE_ME_RICH"))
    decision = validate_agent_work_contract(request)

    assert decision.state == AGENT_WORK_CONTRACT_BLOCKED
    assert decision.accepted is False
    assert "ACTION_UNKNOWN" in decision.blockers


def test_forbidden_order_action_blocks_contract():
    request = normalize_agent_work_request(_payload(action="PLACE_ORDER"))
    decision = validate_agent_work_contract(request)

    assert decision.state == AGENT_WORK_CONTRACT_BLOCKED
    assert decision.accepted is False
    assert decision.work_id is None
    assert "ACTION_FORBIDDEN" in decision.blockers
    assert decision.is_order_action is False
    assert decision.broker_api_called is False
    assert decision.allowed_for_live_execution is False


def test_forbidden_live_and_risk_actions_block_contract():
    for action in (
        "ENABLE_LIVE",
        "DISABLE_RISK_GATE",
        "DISABLE_KILL_SWITCH",
        "DISABLE_FEED_FRESHNESS_GATE",
        "CHANGE_BROKER_CONFIG",
        "CHANGE_CREDENTIALS",
    ):
        decision = validate_agent_work_contract(normalize_agent_work_request(_payload(action=action)))

        assert decision.accepted is False
        assert "ACTION_FORBIDDEN" in decision.blockers
        assert decision.allowed_for_live_execution is False
        assert decision.broker_api_called is False


def test_missing_required_fields_block_contract():
    request = normalize_agent_work_request(
        _payload(
            source_agent="",
            action="",
            title="",
            scope="",
            requested_paths=[],
        )
    )
    decision = validate_agent_work_contract(request)

    assert decision.state == AGENT_WORK_CONTRACT_BLOCKED
    assert "SOURCE_AGENT_MISSING" in decision.blockers
    assert "ACTION_MISSING" in decision.blockers
    assert "TITLE_MISSING" in decision.blockers
    assert "SCOPE_MISSING" in decision.blockers
    assert "REQUESTED_PATHS_MISSING" in decision.blockers


def test_unsupported_schema_version_blocks_contract():
    request = normalize_agent_work_request(_payload(schema_version=999))
    decision = validate_agent_work_contract(request)

    assert decision.accepted is False
    assert "AGENT_WORK_SCHEMA_VERSION_UNSUPPORTED" in decision.blockers


def test_missing_path_policy_lists_warn_but_do_not_block_base_contract():
    request = normalize_agent_work_request(_payload(allowed_paths=[], forbidden_paths=[]))
    decision = validate_agent_work_contract(request)

    assert decision.accepted is True
    assert "ALLOWED_PATHS_EMPTY" in decision.warnings
    assert "FORBIDDEN_PATHS_EMPTY" in decision.warnings


def test_to_dict_is_json_friendly_and_stable():
    request = normalize_agent_work_request(_payload())
    decision = validate_agent_work_contract(request)
    request_payload = request.to_dict()
    decision_payload = decision.to_dict()

    assert request_payload["requested_paths"] == ["tests/test_agent_scope_guard.py"]
    assert request_payload["allowed_paths"] == ["tests/"]
    assert request_payload["forbidden_paths"] == ["credentials.py", ".env", "core/broker"]
    assert request_payload["metadata"] == {"project": "tradebot"}

    assert decision_payload["schema_version"] == AGENT_WORK_SCHEMA_VERSION
    assert decision_payload["state"] == AGENT_WORK_CONTRACT_VALID
    assert decision_payload["read_only"] is True
    assert decision_payload["is_order_action"] is False
    assert decision_payload["broker_api_called"] is False
    assert decision_payload["live_mode_touched"] is False
    assert decision_payload["allowed_for_patch"] is False
    assert decision_payload["allowed_for_live_execution"] is False
    assert decision_payload["blockers"] == []
    assert decision_payload["metadata"]["contract"] == "agent_work_contract_v1"
