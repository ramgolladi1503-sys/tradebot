from __future__ import annotations

from pathlib import Path

from core.candidate_outcome_report_writer import build_candidate_outcome_report
from .contracts import AgentFinding, AgentReport, build_read_only_agent_report


def analyze_edge_measurement(
    *,
    runtime_dir: Path,
    logs_dir: Path,
    session_dir: Path | None = None,
    tail_lines: int = 5000,
    offline_fixtures: Path | None = None,
) -> AgentReport:
    metrics = {
        "candidate_count": 0,
        "target_hit_count": 0,
        "stop_hit_count": 0,
        "timeout_count": 0,
        "invalid_count": 0,
        "avg_mfe": None,
        "avg_mae": None,
        "avg_gross_r": None,
        "avg_cost_adjusted_r": None,
        "expectancy_by_strategy": {},
        "expectancy_by_symbol": {},
        "expectancy_by_regime": {},
        "sample_size_by_bucket": {},
    }
    findings: list[AgentFinding] = []
    verdict = "NOT_EVALUABLE"
    confidence = "LOW"
    if offline_fixtures is not None and offline_fixtures.exists():
        report = build_candidate_outcome_report(offline_fixtures)
        rows = list(report.results)
        metrics["candidate_count"] = report.fixture_count
        metrics["sample_size_by_bucket"] = {"fixture_count": report.fixture_count}
        verdict = "OFFLINE_ONLY_NOT_EDGE" if report.fixture_count > 0 else "NOT_EVALUABLE"
        confidence = "MEDIUM" if report.fixture_count > 0 else "LOW"
        findings.append(
            AgentFinding(
                code="OFFLINE_ONLY_NOT_EDGE",
                severity="WARN",
                layer="edge_measurement",
                message="Offline fixtures exist but do not prove live trading edge.",
                confidence="HIGH",
                recommended_action="Collect executable paper/live outcome samples before claiming edge.",
                files_likely_involved=("core/candidate_outcome_truth.py", "core/candidate_outcome_report_writer.py"),
                tests_needed=("tests/test_edge_measurement_agent.py",),
            )
        )
    else:
        findings.append(
            AgentFinding(
                code="NOT_EVALUABLE",
                severity="WARN",
                layer="edge_measurement",
                message="No executable outcome set is available for edge measurement.",
                confidence="HIGH",
                recommended_action="Use candidate outcome fixtures or paper/replay outcomes to collect samples.",
                files_likely_involved=("core/candidate_outcome_truth.py",),
                tests_needed=("tests/test_edge_measurement_agent.py",),
            )
        )
    return build_read_only_agent_report(
        agent_name="edge_measurement",
        verdict=verdict,
        confidence=confidence,
        first_failing_event=None,
        findings=tuple(findings),
        not_root_cause=("Offline fixtures and missing samples do not prove market edge.",),
        next_fix_recommendation="Collect sufficient paper or replay outcomes before making any edge claim.",
        metrics=metrics,
    )
