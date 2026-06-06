from __future__ import annotations

from core.agents.contracts import AgentEvidenceRef, AgentFinding, build_read_only_agent_report


def test_agent_contracts_are_read_only_and_no_order():
    ref = AgentEvidenceRef(source_path="/tmp/example.log", line_number=3, event="FEED", excerpt="example")
    finding = AgentFinding(
        code="EXAMPLE",
        severity="WARN",
        layer="feed",
        message="example",
        confidence="HIGH",
        evidence_refs=(ref,),
        recommended_action="inspect",
        files_likely_involved=("core/kite_depth_ws.py",),
        tests_needed=("tests/test_agent_contracts.py",),
    )
    report = build_read_only_agent_report(
        agent_name="live_rca",
        verdict="WARN",
        confidence="HIGH",
        first_failing_event="FEED",
        findings=(finding,),
        not_root_cause=("downstream not blamed",),
        next_fix_recommendation="inspect the feed",
        metrics={"sample": 1},
    )

    payload = report.to_dict()
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_allowed"] is False
    assert payload["no_order_action"] is True
    assert payload["findings"][0]["evidence_refs"][0]["source_path"] == "/tmp/example.log"
