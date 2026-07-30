import pytest

from core.ai_reliability_agent.agent import AssertionVerifier, ReliabilityAgent, ScriptedReasoner, ToolRegistry
from core.ai_reliability_agent.contracts import (
    AgentAction,
    AgentActionType,
    AgentMode,
    Assertion,
    ClaimKind,
    FindingProposal,
    FindingStatus,
    Severity,
    ToolRequest,
)
from core.ai_reliability_agent.evidence import EvidenceLedger


def _proposal(ref, assertion):
    return FindingProposal(
        title="finding",
        stage="feed",
        severity=Severity.P1,
        claim_kind=ClaimKind.DETERMINISTIC_FACT,
        narrative="machine verified",
        assertions=(assertion,),
        evidence_ids=(ref.evidence_id,),
    )


@pytest.mark.parametrize(
    "operator,actual,expected,confirmed",
    [
        ("eq", 2, 2, True),
        ("ne", 2, 3, True),
        ("gt", 3, 2, True),
        ("ge", 2, 2, True),
        ("lt", 1, 2, True),
        ("le", 2, 2, True),
        ("contains", [1, 2], 2, True),
        ("not_contains", [1, 2], 3, True),
        ("truthy", 1, True, True),
        ("is_none", None, True, True),
        ("eq", 2, 3, False),
        ("gt", 1, 2, False),
    ],
)
def test_assertion_verifier_operators(tmp_path, operator, actual, expected, confirmed):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ref = ledger.append("tool_result", {"payload": {"value": actual}}, session_id="S")
    proposal = _proposal(ref, Assertion(ref.evidence_id, "payload.value", operator, expected))
    result = AssertionVerifier().verify(proposal, ledger)
    assert (result.status == FindingStatus.CONFIRMED) is confirmed


def test_verifier_rejects_missing_evidence_ids(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    proposal = FindingProposal("x", "feed", Severity.P1, ClaimKind.DETERMINISTIC_FACT, "x", (), ())
    assert AssertionVerifier().verify(proposal, ledger).status == FindingStatus.INSUFFICIENT_EVIDENCE


def test_verifier_rejects_missing_evidence_row(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    proposal = FindingProposal(
        "x", "feed", Severity.P1, ClaimKind.DETERMINISTIC_FACT, "x",
        (Assertion("missing", "x", "eq", 1),), ("missing",),
    )
    assert AssertionVerifier().verify(proposal, ledger).status == FindingStatus.INSUFFICIENT_EVIDENCE


def test_verifier_requires_assertions_for_deterministic_fact(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ref = ledger.append("x", {}, session_id="S")
    proposal = FindingProposal("x", "feed", Severity.P1, ClaimKind.DETERMINISTIC_FACT, "x", (), (ref.evidence_id,))
    result = AssertionVerifier().verify(proposal, ledger)
    assert result.reasons == ("deterministic_fact_requires_assertions",)


def test_verifier_rejects_missing_path(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ref = ledger.append("x", {"a": 1}, session_id="S")
    proposal = _proposal(ref, Assertion(ref.evidence_id, "missing", "eq", 1))
    assert AssertionVerifier().verify(proposal, ledger).status == FindingStatus.REJECTED


def test_verifier_rejects_unknown_operator(tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ref = ledger.append("x", {"a": 1}, session_id="S")
    proposal = _proposal(ref, Assertion(ref.evidence_id, "a", "unsupported", 1))
    assert AssertionVerifier().verify(proposal, ledger).status == FindingStatus.REJECTED


def test_registry_rejects_empty_tool_name():
    with pytest.raises(ValueError, match="tool_name_required"):
        ToolRegistry().register("", lambda args: {})


def test_registry_rejects_duplicate_tool():
    registry = ToolRegistry()
    registry.register("x", lambda args: {})
    with pytest.raises(ValueError, match="tool_already_registered"):
        registry.register("x", lambda args: {})


def test_unknown_tool_fails_closed(tmp_path):
    result = ToolRegistry().execute(
        ToolRequest("missing"), mode=AgentMode.LIVE_OBSERVE,
        ledger=EvidenceLedger(tmp_path / "evidence.jsonl"), session_id="S",
    )
    assert result.success is False
    assert result.error_code == "UNKNOWN_TOOL"


def test_live_mode_blocks_write_tool(tmp_path):
    registry = ToolRegistry()
    registry.register("write", lambda args: {"ok": True}, read_only=False)
    result = registry.execute(
        ToolRequest("write"), mode=AgentMode.LIVE_OBSERVE,
        ledger=EvidenceLedger(tmp_path / "evidence.jsonl"), session_id="S",
    )
    assert result.error_code == "LIVE_MODE_WRITE_TOOL_BLOCKED"


def test_post_market_allows_registered_write_tool(tmp_path):
    registry = ToolRegistry()
    registry.register("write", lambda args: {"ok": True}, read_only=False)
    result = registry.execute(
        ToolRequest("write"), mode=AgentMode.POST_MARKET_ANALYZE,
        ledger=EvidenceLedger(tmp_path / "evidence.jsonl"), session_id="S",
    )
    assert result.success is True


def test_tool_exception_is_recorded(tmp_path):
    registry = ToolRegistry()
    registry.register("bad", lambda args: 1 / 0)
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    result = registry.execute(ToolRequest("bad"), mode=AgentMode.LIVE_OBSERVE, ledger=ledger, session_id="S")
    assert result.error_code == "TOOL_EXECUTION_FAILED"
    assert ledger.verify().valid is True


def test_agent_executes_tool_then_stops(tmp_path):
    registry = ToolRegistry()
    registry.register("health", lambda args: {"healthy": True})
    reasoner = ScriptedReasoner([
        AgentAction(AgentActionType.TOOL, tool_request=ToolRequest("health")),
        AgentAction(AgentActionType.STOP, stop_reason="done"),
    ])
    result = ReliabilityAgent(
        session_id="S", mode=AgentMode.LIVE_OBSERVE, reasoner=reasoner,
        tools=registry, ledger=EvidenceLedger(tmp_path / "evidence.jsonl"),
    ).run("check")
    assert result["tool_calls"] == 1
    assert result["stop_reason"] == "done"
    assert result["evidence_chain_valid"] is True


def test_agent_confirms_machine_verifiable_finding(tmp_path):
    registry = ToolRegistry()
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ref = ledger.append("tool_result", {"payload": {"stale": True}}, session_id="S")
    proposal = _proposal(ref, Assertion(ref.evidence_id, "payload.stale", "eq", True))
    reasoner = ScriptedReasoner([
        AgentAction(AgentActionType.PROPOSE_FINDING, finding=proposal),
        AgentAction(AgentActionType.STOP, stop_reason="done"),
    ])
    result = ReliabilityAgent(
        session_id="S", mode=AgentMode.LIVE_OBSERVE, reasoner=reasoner,
        tools=registry, ledger=ledger,
    ).run("check")
    assert result["findings"][0]["verification"]["status"] == "CONFIRMED"
    assert result["rejected_findings"] == []


def test_agent_rejects_untrue_finding(tmp_path):
    registry = ToolRegistry()
    ledger = EvidenceLedger(tmp_path / "evidence.jsonl")
    ref = ledger.append("tool_result", {"payload": {"stale": False}}, session_id="S")
    proposal = _proposal(ref, Assertion(ref.evidence_id, "payload.stale", "eq", True))
    reasoner = ScriptedReasoner([
        AgentAction(AgentActionType.PROPOSE_FINDING, finding=proposal),
        AgentAction(AgentActionType.STOP, stop_reason="done"),
    ])
    result = ReliabilityAgent(
        session_id="S", mode=AgentMode.LIVE_OBSERVE, reasoner=reasoner,
        tools=registry, ledger=ledger,
    ).run("check")
    assert result["findings"] == []
    assert result["rejected_findings"][0]["verification"]["status"] == "REJECTED"


def test_agent_enforces_tool_budget(tmp_path):
    registry = ToolRegistry()
    registry.register("x", lambda args: {})
    reasoner = ScriptedReasoner([AgentAction(AgentActionType.TOOL, tool_request=ToolRequest("x"))] * 5)
    result = ReliabilityAgent(
        session_id="S", mode=AgentMode.LIVE_OBSERVE, reasoner=reasoner,
        tools=registry, ledger=EvidenceLedger(tmp_path / "evidence.jsonl"), max_steps=5, max_tool_calls=2,
    ).run("check")
    assert result["tool_calls"] == 2
    assert result["stop_reason"] == "tool_budget_exhausted"


def test_agent_rejects_invalid_budget(tmp_path):
    with pytest.raises(ValueError, match="invalid_agent_budget"):
        ReliabilityAgent(
            session_id="S", mode=AgentMode.LIVE_OBSERVE, reasoner=ScriptedReasoner([]),
            tools=ToolRegistry(), ledger=EvidenceLedger(tmp_path / "x"), max_steps=0,
        )


def test_scripted_reasoner_stops_when_exhausted():
    action = ScriptedReasoner([]).next_action({})
    assert action.action_type == AgentActionType.STOP
    assert action.stop_reason == "script_exhausted"
