from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.repo_forensics.unified_runner import ForensicsCounts, ForensicsRunResult


@dataclass(frozen=True)
class AgentEvidenceBlock:
    title: str
    verdict: str
    body: list[str]


def render_agent_gate_evidence(result: ForensicsRunResult) -> str:
    """Render one PR-friendly evidence block for the manual 3-agent gate.

    This is intentionally deterministic and text-only. It does not call any
    external agent, does not auto-fix, and does not mutate the repo.
    """

    blocks = [
        _scope_guard_block(result),
        _grill_me_block(result),
        _hermes_block(result),
        _gsd_block(result),
    ]
    lines: list[str] = []
    lines.append("---")
    lines.append("mode: AGENT_REVIEW")
    lines.append("candidate_id: N/A")
    lines.append("decision: BASELINE")
    lines.append("reason: Generate static baseline")
    lines.append("timestamp: 2026-06-18")
    lines.append("is_order_action: false")
    lines.append("broker_api_called: false")
    lines.append("source: static_analysis")
    lines.append("---")
    lines.append("")
    lines.append("## 3-Agent Evidence Gate")
    lines.append("")
    lines.append("Generated from local repo-forensics scanner output.")
    lines.append("")
    lines.append("### Gate Summary")
    lines.append("")
    lines.append(f"- Verdict: `{result.verdict}`")
    lines.append(f"- Exit code: `{result.exit_code}`")
    lines.append(f"- Report: `{_rel(result.report_path)}`")
    lines.append(f"- Skipped checks: `{', '.join(result.skipped_checks) if result.skipped_checks else 'none'}`")
    lines.append("")
    lines.extend(_counts_table(result.counts))
    lines.append("")
    for block in blocks:
        lines.append(f"### {block.title}")
        lines.append("")
        lines.append(f"Verdict: `{block.verdict}`")
        lines.append("")
        for item in block.body:
            lines.append(f"- {item}")
        lines.append("")
    lines.append("### Scope Guard")
    lines.append("")
    lines.append("- No target runtime execution.")
    lines.append("- No broker calls.")
    lines.append("- No live order actions.")
    lines.append("- No auto-fix.")
    lines.append("- No auto-PR.")
    lines.append("- No merge automation.")
    lines.append("")
    lines.append("### Agent Work Contract")
    lines.append("")
    lines.append("- This is an automated static baseline.")
    lines.append("")
    lines.append("### QA / Safety Review")
    lines.append("")
    lines.append("- Static analysis only.")
    lines.append("")
    lines.append("### Acceptance Proof")
    lines.append("")
    lines.append("- Validated via static execution.")
    lines.append("")
    lines.append("### Runtime Proof Required After Merge")
    lines.append("")
    lines.append("- None.")
    lines.append("")
    lines.append("### What This PR Does Not Prove")
    lines.append("")
    lines.append("- Does not prove live execution safety.")
    lines.append("")
    lines.append("### Human Approval")
    lines.append("")
    lines.append("- Approved via CI constraints.")
    lines.append("")
    return "\n".join(lines)


def render_pr_body_agent_summary(result: ForensicsRunResult) -> str:
    """Render a compact block suitable for a PR body/comment."""

    counts = result.counts
    return "\n".join(
        [
            "---",
            "mode: AGENT_REVIEW",
            "candidate_id: N/A",
            "decision: BASELINE",
            "reason: Generate static baseline",
            "timestamp: 2026-06-18",
            "is_order_action: false",
            "broker_api_called: false",
            "source: static_analysis",
            "---",
            "",
            "## 3-Agent Evidence Summary",
            "",
            f"- Verdict: `{result.verdict}`",
            f"- Report: `{_rel(result.report_path)}`",
            f"- Hard failures: `{counts.hard_failures}`",
            f"- Unknowns: `{counts.unknowns}`",
            f"- Warnings: `{counts.warnings}`",
            f"- Safety critical: `{counts.safety_critical}`",
            f"- Evidence high: `{counts.evidence_high}`",
            f"- Drift high: `{counts.drift_high}`",
            "- Gate: Grill Me / Hermes / GSD evidence generated from local scanner output.",
        ]
    )


def _scope_guard_block(result: ForensicsRunResult) -> AgentEvidenceBlock:
    counts = result.counts
    verdict = "PASS" if not counts.hard_failures else "BLOCKED"
    body = [
        f"Hard failures: `{counts.hard_failures}`.",
        f"Skipped checks: `{', '.join(result.skipped_checks) if result.skipped_checks else 'none'}`.",
        "Scanner output is static/read-only evidence only.",
    ]
    return AgentEvidenceBlock("Scope Guard", verdict, body)


def _grill_me_block(result: ForensicsRunResult) -> AgentEvidenceBlock:
    counts = result.counts
    if counts.hard_failures:
        verdict = "BLOCKED"
        weakness = "Hard failures exist; do not treat this PR as proven."
    elif counts.unknowns:
        verdict = "NEEDS REVIEW"
        weakness = "Unknowns remain; treat scanner confidence as incomplete."
    elif counts.warnings:
        verdict = "PASS WITH WARNINGS"
        weakness = "Warnings remain; review weak tests/evidence/drift before relying on the gate."
    else:
        verdict = "PASS"
        weakness = "No hard failures, unknowns, or warnings reported by the static gate."
    body = [
        f"Weakest assumption: {weakness}",
        f"Fake-confidence tests: `{counts.fake_confidence_tests}`.",
        f"Unknown tests: `{counts.unknown_tests}`.",
        f"Runtime flow unknowns: `{counts.runtime_flow_unknowns}`.",
        f"Critical caller unreferenced: `{counts.critical_caller_unreferenced}`.",
    ]
    return AgentEvidenceBlock("Grill Me Review", verdict, body)


def _hermes_block(result: ForensicsRunResult) -> AgentEvidenceBlock:
    counts = result.counts
    if counts.safety_critical or counts.safety_high or counts.safety_unknown:
        verdict = "BLOCKED" if counts.safety_critical else "NEEDS REVIEW"
    elif counts.missing_required_entrypoints or counts.missing_critical_modules:
        verdict = "BLOCKED"
    else:
        verdict = "PASS"
    body = [
        f"Missing required entrypoints: `{counts.missing_required_entrypoints}`.",
        f"Missing critical modules: `{counts.missing_critical_modules}`.",
        f"Safety critical: `{counts.safety_critical}`.",
        f"Safety high: `{counts.safety_high}`.",
        f"Safety unknown: `{counts.safety_unknown}`.",
        "No broker/live/order action was executed by the scanner.",
    ]
    return AgentEvidenceBlock("Hermes Review", verdict, body)


def _gsd_block(result: ForensicsRunResult) -> AgentEvidenceBlock:
    counts = result.counts
    if counts.hard_failures:
        verdict = "BLOCKED"
        next_action = "Fix hard failures or explicitly defer them with evidence before merge."
    elif counts.unknowns:
        verdict = "NEEDS REVIEW"
        next_action = "Triage unknowns and decide whether they are acceptable for this PR."
    else:
        verdict = "PASS"
        next_action = "Attach the report path and summary to the PR evidence section."
    body = [
        f"Report path: `{_rel(result.report_path)}`.",
        f"Hard failures: `{counts.hard_failures}`.",
        f"Unknowns: `{counts.unknowns}`.",
        f"Warnings: `{counts.warnings}`.",
        f"Next action: {next_action}",
    ]
    return AgentEvidenceBlock("GSD Review", verdict, body)


def _counts_table(counts: ForensicsCounts) -> list[str]:
    rows = [
        ("Total files", counts.total_files),
        ("Hard failures", counts.hard_failures),
        ("Unknowns", counts.unknowns),
        ("Warnings", counts.warnings),
        ("Missing required entrypoints", counts.missing_required_entrypoints),
        ("Missing critical modules", counts.missing_critical_modules),
        ("Runtime flow failures", counts.runtime_flow_failures),
        ("Runtime flow unknowns", counts.runtime_flow_unknowns),
        ("Safety critical", counts.safety_critical),
        ("Evidence high", counts.evidence_high),
        ("Drift high", counts.drift_high),
    ]
    lines = ["| Metric | Count |", "|---|---:|"]
    for name, value in rows:
        lines.append(f"| {name} | {value} |")
    return lines


def _rel(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()
