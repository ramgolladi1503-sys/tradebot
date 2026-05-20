from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tools.repo_forensics.unified_runner import EXIT_POLICY_REPORT_ONLY, ForensicsCheckToggles, ForensicsCounts, ForensicsRunResult, run_forensics


DEFAULT_BASELINE_SUMMARY = "docs/repo_forensics/reports/baseline_pr_summary.md"
DEFAULT_PR_GATE_REPORT = "docs/repo_forensics/reports/pr_gate_latest.md"


@dataclass(frozen=True)
class GateDelta:
    metric: str
    baseline: int
    current: int

    @property
    def delta(self) -> int:
        return self.current - self.baseline


@dataclass(frozen=True)
class PRGateResult:
    current: ForensicsRunResult
    baseline_counts: ForensicsCounts
    deltas: list[GateDelta]
    verdict: str
    report_path: Path

    @property
    def exit_code(self) -> int:
        return 1 if self.verdict == "FAIL" else 0


def run_pr_gate(
    repo_root: str | Path,
    config_path: str | Path = ".gsd-forensics.yaml",
    *,
    baseline_summary_path: str | Path = DEFAULT_BASELINE_SUMMARY,
    current_report_path: str | Path = DEFAULT_PR_GATE_REPORT,
    gate_report_path: str | Path = DEFAULT_PR_GATE_REPORT,
    toggles: ForensicsCheckToggles | None = None,
) -> PRGateResult:
    root = Path(repo_root).resolve()
    baseline_file = _resolve(root, baseline_summary_path)
    baseline_counts = parse_baseline_counts(baseline_file.read_text(encoding="utf-8"))
    current = run_forensics(
        root,
        config_path,
        current_report_path,
        toggles=toggles or ForensicsCheckToggles(),
        exit_policy=EXIT_POLICY_REPORT_ONLY,
    )
    deltas = compare_counts(baseline_counts, current.counts)
    verdict = gate_verdict(deltas)
    report_file = _resolve(root, gate_report_path)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(render_pr_gate_report(current, baseline_counts, deltas, verdict), encoding="utf-8")
    return PRGateResult(
        current=current,
        baseline_counts=baseline_counts,
        deltas=deltas,
        verdict=verdict,
        report_path=report_file,
    )


def parse_baseline_counts(text: str) -> ForensicsCounts:
    values = _extract_counts(text)
    return ForensicsCounts(
        missing_required_entrypoints=values.get("missing_required_entrypoints", 0),
        missing_critical_modules=values.get("missing_critical_modules", 0),
        runtime_flow_failures=values.get("runtime_flow_failures", 0),
        runtime_flow_unknowns=values.get("runtime_flow_unknowns", 0),
        critical_caller_missing=values.get("critical_caller_missing", 0),
        critical_caller_test_only=values.get("critical_caller_test_only", 0),
        critical_caller_unreferenced=values.get("critical_caller_unreferenced", 0),
        fake_confidence_tests=values.get("fake_confidence_tests", 0),
        unknown_tests=values.get("unknown_tests", 0),
        safety_critical=values.get("safety_critical", 0),
        safety_high=values.get("safety_high", 0),
        safety_unknown=values.get("safety_unknown", 0),
        evidence_high=values.get("evidence_high", 0),
        evidence_medium=values.get("evidence_medium", 0),
        evidence_unknown=values.get("evidence_unknown", 0),
        drift_high=values.get("drift_high", 0),
        drift_medium=values.get("drift_medium", 0),
        drift_unknown=values.get("drift_unknown", 0),
    )


def compare_counts(baseline: ForensicsCounts, current: ForensicsCounts) -> list[GateDelta]:
    metrics = [
        "hard_failures",
        "unknowns",
        "warnings",
        "missing_required_entrypoints",
        "missing_critical_modules",
        "runtime_flow_failures",
        "runtime_flow_unknowns",
        "critical_caller_missing",
        "critical_caller_test_only",
        "critical_caller_unreferenced",
        "fake_confidence_tests",
        "unknown_tests",
        "safety_critical",
        "safety_high",
        "safety_unknown",
        "evidence_high",
        "evidence_medium",
        "evidence_unknown",
        "drift_high",
        "drift_medium",
        "drift_unknown",
    ]
    return [GateDelta(metric, int(getattr(baseline, metric)), int(getattr(current, metric))) for metric in metrics]


def gate_verdict(deltas: list[GateDelta]) -> str:
    by_metric = {item.metric: item for item in deltas}
    if by_metric["hard_failures"].delta > 0:
        return "FAIL"
    if by_metric["unknowns"].delta > 0:
        return "UNKNOWN"
    if by_metric["warnings"].delta > 0:
        return "PASS_WITH_WARNINGS"
    return "PASS"


def render_pr_gate_report(
    current: ForensicsRunResult,
    baseline: ForensicsCounts,
    deltas: list[GateDelta],
    verdict: str,
) -> str:
    lines: list[str] = []
    lines.append("# Repo Forensics — PR Gate")
    lines.append("")
    lines.append("## Purpose")
    lines.append("")
    lines.append("Compare current static repo-forensics output against the committed baseline.")
    lines.append("Existing baseline debt is not treated as a new regression. Increases are flagged.")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"`{verdict}`")
    lines.append("")
    lines.append("## Baseline Summary")
    lines.append("")
    lines.append(f"- Hard failures: `{baseline.hard_failures}`")
    lines.append(f"- Unknowns: `{baseline.unknowns}`")
    lines.append(f"- Warnings: `{baseline.warnings}`")
    lines.append("")
    lines.append("## Current Summary")
    lines.append("")
    lines.append(f"- Hard failures: `{current.counts.hard_failures}`")
    lines.append(f"- Unknowns: `{current.counts.unknowns}`")
    lines.append(f"- Warnings: `{current.counts.warnings}`")
    lines.append(f"- Full report: `{current.report_path}`")
    lines.append("")
    lines.append("## Delta Table")
    lines.append("")
    lines.append("| Metric | Baseline | Current | Delta |")
    lines.append("|---|---:|---:|---:|")
    for item in deltas:
        lines.append(f"| {item.metric} | {item.baseline} | {item.current} | {item.delta} |")
    lines.append("")
    lines.append("## Gate Policy")
    lines.append("")
    lines.append("- New hard failures: `FAIL`.")
    lines.append("- New unknowns without new hard failures: `UNKNOWN`.")
    lines.append("- New warnings only: `PASS_WITH_WARNINGS`.")
    lines.append("- Same or improved counts: `PASS`.")
    lines.append("")
    lines.append("## Scope Guard")
    lines.append("")
    lines.append("- Static scan only.")
    lines.append("- No target runtime execution.")
    lines.append("- No broker calls.")
    lines.append("- No live order actions.")
    lines.append("- No auto-fix.")
    lines.append("- No auto-PR.")
    lines.append("")
    return "\n".join(lines)


def _extract_counts(text: str) -> dict[str, int]:
    mapping: dict[str, str] = {
        "Hard failures": "hard_failures",
        "Unknowns": "unknowns",
        "Warnings": "warnings",
        "Safety critical": "safety_critical",
        "Evidence high": "evidence_high",
        "Drift high": "drift_high",
    }
    values: dict[str, int] = {}
    for label, key in mapping.items():
        pattern = rf"{re.escape(label)}:\s*`?(\d+)`?"
        match = re.search(pattern, text)
        if match:
            values[key] = int(match.group(1))
    # Baseline summary may not include every granular metric. Aggregate metrics
    # still protect the PR gate. Missing granular values default to zero.
    return values


def _resolve(repo_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate
