from __future__ import annotations

from tools.repo_forensics.candidate_trace import (
    REQUIRED_CANDIDATE_STAGES,
    build_candidate_lifecycle_trace_report,
    normalize_candidate_stage,
    render_candidate_lifecycle_trace_report,
)


def _complete_records(candidate_id: str = "CAND-1") -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for stage in REQUIRED_CANDIDATE_STAGES:
        record: dict[str, object] = {"candidate_id": candidate_id, "stage": stage}
        if stage == "final_decision":
            record["rank_consumed"] = True
            record["reason"] = "accepted_after_rank_and_risk"
        records.append(record)
    return records


def test_normalize_candidate_stage_accepts_tradebot_flow_aliases():
    assert normalize_candidate_stage("candidate_generation") == "candidate_generated"
    assert normalize_candidate_stage("candidate_finalization") == "candidate_finalized"
    assert normalize_candidate_stage("opportunity_scoring") == "scored"
    assert normalize_candidate_stage("ranking") == "ranked"
    assert normalize_candidate_stage("data_quality_gate") == "data_quality_checked"
    assert normalize_candidate_stage("no_trade_or_gatekeeper") == "gatekeeper_checked"
    assert normalize_candidate_stage("risk_evaluation") == "risk_evaluated"
    assert normalize_candidate_stage("review_queue_or_evidence") == "evidence_output"


def test_candidate_lifecycle_trace_passes_for_complete_candidate_records():
    report = build_candidate_lifecycle_trace_report(_complete_records())

    assert report.failures == []
    assert report.unknowns == []
    assert [trace.candidate_id for trace in report.traces] == ["CAND-1"]
    trace = report.traces[0]
    assert trace.complete is True
    assert trace.missing_stages == ()


def test_candidate_lifecycle_trace_flags_absent_identity_as_hard_failure():
    records = _complete_records()
    records.append({"stage": "candidate_generated"})

    report = build_candidate_lifecycle_trace_report(records)

    assert [finding.finding_type for finding in report.failures] == ["candidate_id_missing"]
    assert [finding.evidence for finding in report.failures] == ["record_index:9"]


def test_candidate_lifecycle_trace_reports_non_unsafe_missing_stage_as_unknown():
    records = [record for record in _complete_records() if record["stage"] != "evidence_output"]

    report = build_candidate_lifecycle_trace_report(records)

    assert report.failures == []
    assert [finding.finding_type for finding in report.unknowns] == ["candidate_lifecycle_incomplete"]
    trace = report.traces[0]
    assert "evidence_output" in trace.missing_stages
    assert trace.complete is False


def test_candidate_lifecycle_trace_flags_ranking_not_consumed():
    records = _complete_records()
    for record in records:
        if record["stage"] == "final_decision":
            record.pop("rank_consumed", None)

    report = build_candidate_lifecycle_trace_report(records)

    assert [finding.finding_type for finding in report.failures] == ["ranking_not_consumed"]


def test_candidate_lifecycle_trace_allows_final_decision_with_rank_reference():
    records = _complete_records()
    for record in records:
        if record["stage"] == "final_decision":
            record.pop("rank_consumed", None)
            record["final_rank"] = 1

    report = build_candidate_lifecycle_trace_report(records)

    assert report.failures == []
    assert report.traces[0].complete is True


def test_candidate_lifecycle_trace_flags_risk_not_proven_before_decision():
    records = [record for record in _complete_records() if record["stage"] != "risk_evaluated"]
    # Keep ranking consumption explicit so this test isolates risk-before-decision proof.
    for record in records:
        if record["stage"] == "final_decision":
            record["rank_consumed"] = True

    report = build_candidate_lifecycle_trace_report(records)

    assert [finding.finding_type for finding in report.failures] == ["risk_before_execution_not_proven"]
    assert "risk_evaluated" in report.traces[0].missing_stages


def test_candidate_lifecycle_trace_reports_unknown_stage_without_fake_pass():
    records = _complete_records()
    records.append({"candidate_id": "CAND-1", "stage": "mystery_stage"})

    report = build_candidate_lifecycle_trace_report(records)

    assert [finding.finding_type for finding in report.unknowns] == ["candidate_stage_unknown"]


def test_render_candidate_lifecycle_trace_report_includes_verdict():
    report = build_candidate_lifecycle_trace_report(_complete_records())

    rendered = render_candidate_lifecycle_trace_report(report)

    assert "# Candidate Lifecycle Trace Report" in rendered
    assert "Candidates reviewed: `1`" in rendered
    assert "PASS — candidate lifecycle trace is complete" in rendered
