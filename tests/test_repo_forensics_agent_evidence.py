from __future__ import annotations

from pathlib import Path

from tools.repo_forensics.agent_evidence import render_agent_gate_evidence, render_pr_body_agent_summary
from tools.repo_forensics.unified_runner import ForensicsCounts, ForensicsRunResult


def _result(counts: ForensicsCounts, verdict: str = "PASS", exit_code: int = 0) -> ForensicsRunResult:
    return ForensicsRunResult(
        report_path=Path("docs/repo_forensics/reports/repo_map_latest.md"),
        counts=counts,
        verdict=verdict,
        exit_code=exit_code,
        skipped_checks=[],
    )


def test_agent_gate_evidence_contains_required_sections():
    result = _result(ForensicsCounts(total_files=10))

    evidence = render_agent_gate_evidence(result)

    assert "## 3-Agent Evidence Gate" in evidence
    assert "### Grill Me Review" in evidence
    assert "### Hermes Review" in evidence
    assert "### GSD Review" in evidence
    assert "### Scope Guard" in evidence
    assert "No broker calls" in evidence
    assert "No live order actions" in evidence


def test_agent_gate_evidence_blocks_on_hard_failures():
    result = _result(
        ForensicsCounts(
            total_files=10,
            missing_required_entrypoints=1,
            safety_critical=1,
        ),
        verdict="FAIL",
        exit_code=1,
    )

    evidence = render_agent_gate_evidence(result)

    assert "Verdict: `BLOCKED`" in evidence
    assert "Safety critical: `1`" in evidence
    assert "Hard failures | 2" in evidence


def test_pr_body_summary_is_compact_and_pr_friendly():
    result = _result(
        ForensicsCounts(
            total_files=10,
            runtime_flow_unknowns=2,
            fake_confidence_tests=3,
        ),
        verdict="UNKNOWN",
        exit_code=0,
    )

    summary = render_pr_body_agent_summary(result)

    assert summary.startswith("---")
    assert "## 3-Agent Evidence Summary" in summary
    assert "- Verdict: `UNKNOWN`" in summary
    assert "- Unknowns: `2`" in summary
    assert "- Warnings: `3`" in summary
    assert "Grill Me / Hermes / GSD" in summary
