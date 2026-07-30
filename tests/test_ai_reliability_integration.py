import json
from pathlib import Path

import pytest

from core.ai_reliability_agent.contracts import AgentActionType, AgentMode, CertificationLevel
from core.ai_reliability_agent.openai_reasoner import OpenAIReasoner
from core.ai_reliability_agent.runtime import (
    build_session_manifest,
    build_tools,
    default_artifact_paths,
    finalize_session,
    read_jsonl,
    render_markdown,
)


class FakeResponse:
    def __init__(self, data):
        self.data = data
        self.status_checked = False

    def raise_for_status(self):
        self.status_checked = True

    def json(self):
        return self.data


def test_openai_reasoner_parses_strict_stop_action():
    response = FakeResponse({"output_text": json.dumps({
        "action_type": "STOP", "tool_request": None, "finding": None, "stop_reason": "enough",
    })})
    captured = {}

    def post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return response

    action = OpenAIReasoner(api_key="test-key", model="test-model", post=post).next_action({"tool_schemas": []})
    assert action.action_type == AgentActionType.STOP
    assert captured["json"]["store"] is False
    assert captured["json"]["text"]["format"]["strict"] is True
    assert "test-key" not in json.dumps(captured["json"])


def test_openai_reasoner_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY_missing"):
        OpenAIReasoner(api_key="")


def test_read_jsonl_marks_invalid_rows(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"x":1}\ninvalid\n')
    rows = read_jsonl(path)
    assert rows[0]["x"] == 1
    assert rows[1]["_invalid_json"] is True


def test_manifest_is_read_only_and_redacted(tmp_path):
    manifest = build_session_manifest(
        session_id="S", mode=AgentMode.LIVE_OBSERVE, repo_root=tmp_path,
        config={"api_key": "secret", "safe": 1},
    )
    assert manifest["read_only"] is True
    assert manifest["order_authority"] is False
    assert manifest["config"]["api_key"] == "[REDACTED]"


def test_default_paths_match_existing_tradebot_layout(tmp_path):
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    assert paths["events"] == tmp_path / ".runtime" / "logs" / "events.jsonl"
    assert paths["candidate_lineage"].name == "candidate_funnel_20260731.jsonl"


def test_tool_registry_reads_artifact_health(tmp_path):
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["events"].parent.mkdir(parents=True)
    paths["events"].write_text('{"type":"x"}\n')
    registry = build_tools(tmp_path, session_date="20260731")
    assert "get_artifact_health" in registry.names()


def test_finalize_session_creates_json_and_markdown(tmp_path):
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    rows = [
        {"candidate_id": "A", "stage": "selected", "stage_status": "selected", "execution_ok": True, "permission": "EXECUTE"},
        {"candidate_id": "A", "stage": "closed", "outcome": "target"},
    ]
    paths["candidate_lineage"].write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    result = finalize_session(
        session_id="S", repo_root=tmp_path, output_dir=tmp_path / "reports", session_date="20260731",
    )
    assert Path(result["json_path"]).exists()
    assert Path(result["markdown_path"]).exists()
    assert result["certification_level"] == CertificationLevel.LIVE_CERTIFICATION_PENDING.value
    assert result["analytics"]["candidate_count"] == 1


def test_finalize_fails_session_when_lineage_missing(tmp_path):
    result = finalize_session(
        session_id="S", repo_root=tmp_path, output_dir=tmp_path / "reports", session_date="20260731",
    )
    assert result["session_verdict"] == "LIVE_SESSION_INVALID"


def test_finalize_flags_approved_fallback_candidate(tmp_path):
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    rows = [
        {"candidate_id": "A", "stage": "selected", "stage_status": "selected", "fallback_used": True},
        {"candidate_id": "A", "stage": "closed", "outcome": "target"},
    ]
    paths["candidate_lineage"].write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    result = finalize_session(
        session_id="S", repo_root=tmp_path, output_dir=tmp_path / "reports", session_date="20260731",
    )
    assert result["session_verdict"] == "PIPELINE_EMITTED_UNTRUSTWORTHY_CANDIDATES"


def test_markdown_uses_observed_contributor_language():
    markdown = render_markdown({
        "session_id": "S", "session_verdict": "X", "certification_level": "Y", "limitations": [],
        "analytics": {"candidate_count": 1, "pipeline_funnel": {}, "rejection_breakdown": {}, "autopsies": [{
            "candidate_id": "C", "strategy_name": "S", "approved": True, "executed": True,
            "outcome": "STOP", "decision_outcome_class": "GOOD_DECISION_BAD_OUTCOME", "rejection_verdict": None,
            "observed_contributors": [{"factor": "NORMAL_VARIANCE", "claim_kind": "UNVERIFIED_HYPOTHESIS", "confidence": 0.3, "explanation": "hypothesis"}],
        }]},
    })
    assert "Contributor" in markdown
    assert "UNVERIFIED_HYPOTHESIS" in markdown


def test_component_certification_passes(tmp_path):
    from core.ai_reliability_agent.certification import run_component_certification
    result = run_component_certification(tmp_path)
    assert result["passed"] is True
    assert result["certification_level"] == "SIMULATION_CERTIFIED"
    assert result["live_certification"] == "LIVE_CERTIFICATION_PENDING"


def test_detect_triggers_missing_lineage(tmp_path):
    from core.ai_reliability_agent.supervisor import detect_triggers
    triggers = detect_triggers(tmp_path, session_date="20260731")
    assert triggers[0].trigger_type == "CANDIDATE_LINEAGE_MISSING"


def test_detect_triggers_untrustworthy_selected_candidate(tmp_path):
    from core.ai_reliability_agent.supervisor import detect_triggers
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    paths["candidate_lineage"].write_text(json.dumps({
        "candidate_id": "C", "stage_status": "selected", "fallback_used": True,
    }) + "\n")
    triggers = detect_triggers(tmp_path, session_date="20260731")
    assert {trigger.trigger_type for trigger in triggers} == {"UNTRUSTWORTHY_EXECUTABLE_CANDIDATE"}


def test_detect_triggers_blocked_without_reason(tmp_path):
    from core.ai_reliability_agent.supervisor import detect_triggers
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    paths["candidate_lineage"].write_text(json.dumps({
        "candidate_id": "C", "stage_status": "blocked",
    }) + "\n")
    triggers = detect_triggers(tmp_path, session_date="20260731")
    assert {trigger.trigger_type for trigger in triggers} == {"BLOCKED_CANDIDATE_WITHOUT_REASON"}


def test_supervisor_rejects_subsecond_polling(tmp_path):
    from core.ai_reliability_agent.supervisor import LiveAgentSupervisor
    with pytest.raises(ValueError, match="interval_sec_below_minimum"):
        LiveAgentSupervisor(
            session_id="S", repo_root=tmp_path, evidence_path=tmp_path / "evidence.jsonl",
            interval_sec=0.5, reasoner_factory=lambda: None,
        )


def test_merge_trade_outcome_matches_candidate_by_trade_id():
    from core.ai_reliability_agent.runtime import merge_trade_outcomes
    rows, stats = merge_trade_outcomes(
        [{"candidate_id": "C1", "trade_id": "T1", "stage": "selected"}],
        [{"trade_id": "T1", "status": "closed", "outcome": "target"}],
    )
    assert rows[-1]["candidate_id"] == "C1"
    assert rows[-1]["outcome_scope"] == "ACTUAL"
    assert rows[-1]["lineage_match"] is True
    assert stats["matched_trade_rows"] == 1


def test_merge_trade_outcome_retains_unmatched_trade_as_observability_evidence():
    from core.ai_reliability_agent.runtime import merge_trade_outcomes
    rows, stats = merge_trade_outcomes([], [{"trade_id": "T2", "status": "filled"}])
    assert rows[0]["candidate_id"] == "T2"
    assert rows[0]["lineage_match"] is False
    assert stats["unmatched_trade_rows"] == 1


def test_merge_trade_outcome_does_not_promote_rejected_candidate():
    from core.ai_reliability_agent.runtime import merge_trade_outcomes
    rows, _ = merge_trade_outcomes(
        [{"candidate_id": "C", "stage_status": "blocked", "block_reason": "WIDE_SPREAD"}],
        [],
    )
    assert rows == [{"candidate_id": "C", "stage_status": "blocked", "block_reason": "WIDE_SPREAD"}]


def test_assess_session_evidence_flags_unmatched_trade(tmp_path):
    from core.ai_reliability_agent.analytics import analyze_candidates
    from core.ai_reliability_agent.runtime import assess_session_evidence, merge_trade_outcomes
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    paths["candidate_lineage"].write_text("", encoding="utf-8")
    rows, _ = merge_trade_outcomes([], [{"trade_id": "T", "status": "closed", "outcome": "target"}])
    quality = assess_session_evidence(paths=paths, rows=rows, analytics=analyze_candidates(rows))
    assert quality["unmatched_trade_rows"] == 1
    assert quality["observability_gaps"] >= 1


def test_assess_session_evidence_detects_generated_candidate_disappearance(tmp_path):
    from core.ai_reliability_agent.analytics import analyze_candidates
    from core.ai_reliability_agent.runtime import assess_session_evidence
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    paths["candidate_lineage"].write_text(json.dumps({"candidate_id": "C1", "stage": "generated"}) + "\n")
    paths["candidate_summary"].write_text(json.dumps({"generated_total": 3}) + "\n")
    rows = read_jsonl(paths["candidate_lineage"])
    quality = assess_session_evidence(paths=paths, rows=rows, analytics=analyze_candidates(rows))
    assert quality["unexplained_disappearances"] == 2


def test_finalize_uses_actual_trade_log_outcome(tmp_path):
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    paths["candidate_lineage"].write_text(json.dumps({
        "candidate_id": "C", "trade_id": "T", "stage": "selected", "stage_status": "selected",
        "execution_ok": True, "spread_pct": 0.3,
    }) + "\n")
    paths["trade_log"].parent.mkdir(parents=True, exist_ok=True)
    paths["trade_log"].write_text(json.dumps({"trade_id": "T", "status": "closed", "outcome": "stop"}) + "\n")
    result = finalize_session(session_id="S", repo_root=tmp_path, output_dir=tmp_path / "r", session_date="20260731")
    autopsy = result["analytics"]["autopsies"][0]
    assert autopsy["outcome"] == "STOP"
    assert autopsy["outcome_scope"] == "ACTUAL"
    assert autopsy["executed"] is True


def test_finalize_marks_approved_unexecuted_outcome_hypothetical(tmp_path):
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    paths["candidate_lineage"].write_text("\n".join([
        json.dumps({"candidate_id": "C", "stage": "selected", "stage_status": "selected", "execution_ok": True, "spread_pct": 0.3}),
        json.dumps({"candidate_id": "C", "stage": "shadow_outcome", "outcome": "target"}),
    ]) + "\n")
    result = finalize_session(session_id="S", repo_root=tmp_path, output_dir=tmp_path / "r", session_date="20260731")
    assert result["analytics"]["autopsies"][0]["outcome_scope"] == "HYPOTHETICAL"


def test_finalize_marks_rejected_outcome_counterfactual(tmp_path):
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    paths["candidate_lineage"].write_text("\n".join([
        json.dumps({"candidate_id": "C", "stage_status": "blocked", "block_reason": "WIDE_SPREAD"}),
        json.dumps({"candidate_id": "C", "stage": "shadow_outcome", "outcome": "stop"}),
    ]) + "\n")
    result = finalize_session(session_id="S", repo_root=tmp_path, output_dir=tmp_path / "r", session_date="20260731")
    assert result["analytics"]["autopsies"][0]["outcome_scope"] == "COUNTERFACTUAL"


def test_query_candidate_tool_includes_trade_rows(tmp_path):
    paths = default_artifact_paths(tmp_path, session_date="20260731")
    paths["candidate_lineage"].parent.mkdir(parents=True)
    paths["candidate_lineage"].write_text(json.dumps({"candidate_id": "C", "trade_id": "T"}) + "\n")
    paths["trade_log"].parent.mkdir(parents=True, exist_ok=True)
    paths["trade_log"].write_text(json.dumps({"trade_id": "T", "status": "filled"}) + "\n")
    registry = build_tools(tmp_path, session_date="20260731")
    from core.ai_reliability_agent.evidence import EvidenceLedger
    from core.ai_reliability_agent.contracts import ToolRequest
    result = registry.execute(
        ToolRequest("query_candidate_lineage", {"candidate_id": "C"}),
        mode=AgentMode.POST_MARKET_ANALYZE,
        ledger=EvidenceLedger(tmp_path / "evidence.jsonl"),
        session_id="S",
    )
    assert result.success is True
    assert result.payload["row_count"] == 2


def test_markdown_displays_outcome_scope():
    markdown = render_markdown({
        "session_id": "S", "session_verdict": "X", "certification_level": "Y", "limitations": [],
        "evidence_quality": {},
        "analytics": {"candidate_count": 1, "pipeline_funnel": {}, "rejection_breakdown": {}, "autopsies": [{
            "candidate_id": "C", "strategy_name": "S", "approved": False, "executed": False,
            "outcome": "TARGET", "outcome_scope": "COUNTERFACTUAL",
            "decision_outcome_class": "UNVERIFIABLE", "rejection_verdict": "UNVERIFIABLE",
            "observed_contributors": [],
        }]},
    })
    assert "`COUNTERFACTUAL`" in markdown
