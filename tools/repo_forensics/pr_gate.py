from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tools.repo_forensics.unified_runner import (
    EXIT_POLICY_REPORT_ONLY,
    ForensicsCheckToggles,
    ForensicsCounts,
    ForensicsRunResult,
    run_forensics,
)


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
    return PRGateResult(current, baseline_counts, deltas, verdict, report_file)


def parse_baseline_counts(text: str) -> ForensicsCounts:
    values = _extract_counts(text)
    hard_extra = _remainder(
        values,
        "hard_failures",
        (
            "missing_required_entrypoints",
            "missing_critical_modules",
            "runtime_flow_failures",
            "critical_caller_missing",
            "critical_caller_test_only",
            "safety_critical",
            "evidence_high",
            "drift_high",
        ),
    )
    unknown_extra = _remainder(
        values,
        "unknowns",
        (
            "runtime_flow_unknowns",
            "critical_caller_unreferenced",
            "unknown_tests",
            "safety_high",
            "safety_unknown",
            "evidence_unknown",
            "drift_unknown",
        ),
    )
    warning_extra = _remainder(values, "warnings", ("fake_confidence_tests", "evidence_medium", "drift_medium"))
    return ForensicsCounts(
        missing_required_entrypoints=values.get("missing_required_entrypoints", 0) + hard_extra,
        missing_critical_modules=values.get("missing_critical_modules", 0),
        runtime_flow_failures=values.get("runtime_flow_failures", 0),
        runtime_flow_unknowns=values.get("runtime_flow_unknowns", 0) + unknown_extra,
        critical_caller_missing=values.get("critical_caller_missing", 0),
        critical_caller_test_only=values.get("critical_caller_test_only", 0),
        critical_caller_unreferenced=values.get("critical_caller_unreferenced", 0),
        fake_confidence_tests=values.get("fake_confidence_tests", 0) + warning_extra,
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


def render_pr_gate_report(current: ForensicsRunResult, baseline: ForensicsCounts, deltas: list[GateDelta], verdict: str) -> str:
    lines = [
        "# Repo Forensics — PR Gate",
        "",
        "## Purpose",
        "",
        "Compare current static repo-forensics output against the committed baseline.",
        "Existing baseline debt is not treated as a new regression. Increases are flagged.",
        "",
        "## Verdict",
        "",
        f"`{verdict}`",
        "",
        "## Baseline Summary",
        "",
        f"- Hard failures: `{baseline.hard_failures}`",
        f"- Unknowns: `{baseline.unknowns}`",
        f"- Warnings: `{baseline.warnings}`",
        "",
        "## Current Summary",
        "",
        f"- Hard failures: `{current.counts.hard_failures}`",
        f"- Unknowns: `{current.counts.unknowns}`",
        f"- Warnings: `{current.counts.warnings}`",
        f"- Full report: `{current.report_path}`",
        "",
        "## Delta Table",
        "",
        "| Metric | Baseline | Current | Delta |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(f"| {item.metric} | {item.baseline} | {item.current} | {item.delta} |" for item in deltas)
    lines.extend(
        [
            "",
            "## Gate Policy",
            "",
            "- New hard failures: `FAIL`.",
            "- New unknowns without new hard failures: `UNKNOWN`.",
            "- New warnings only: `PASS_WITH_WARNINGS`.",
            "- Same or improved counts: `PASS`.",
            "",
            "## Scope Guard",
            "",
            "- Static scan only.",
            "- No target runtime execution.",
            "- No broker calls.",
            "- No live order actions.",
            "- No auto-fix.",
            "- No auto-PR.",
            "",
        ]
    )
    return "\n".join(lines)


def _extract_counts(text: str) -> dict[str, int]:
    labels = {
        "hard failures": "hard_failures",
        "unknowns": "unknowns",
        "warnings": "warnings",
        "missing required entrypoints": "missing_required_entrypoints",
        "missing critical modules": "missing_critical_modules",
        "runtime flow failures": "runtime_flow_failures",
        "runtime flow unknowns": "runtime_flow_unknowns",
        "critical caller missing": "critical_caller_missing",
        "critical caller test only": "critical_caller_test_only",
        "critical caller unreferenced": "critical_caller_unreferenced",
        "fake confidence tests": "fake_confidence_tests",
        "unknown tests": "unknown_tests",
        "safety critical": "safety_critical",
        "safety high": "safety_high",
        "safety unknown": "safety_unknown",
        "evidence high": "evidence_high",
        "evidence medium": "evidence_medium",
        "evidence unknown": "evidence_unknown",
        "drift high": "drift_high",
        "drift medium": "drift_medium",
        "drift unknown": "drift_unknown",
    }
    values: dict[str, int] = {}
    for label, key in labels.items():
        match = re.search(rf"{re.escape(label)}:\s*`?(\d+)`?", text, flags=re.IGNORECASE)
        if match:
            values[key] = int(match.group(1))
    return values


def _remainder(values: dict[str, int], aggregate_key: str, component_keys: tuple[str, ...]) -> int:
    if aggregate_key not in values:
        return 0
    known = sum(values.get(key, 0) for key in component_keys)
    return max(0, values[aggregate_key] - known)


def _resolve(repo_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else repo_root / candidate
