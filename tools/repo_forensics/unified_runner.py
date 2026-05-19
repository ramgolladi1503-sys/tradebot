from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tools.repo_forensics.architecture_drift import ArchitectureDriftReport, detect_architecture_drift
from tools.repo_forensics.config_loader import ForensicsConfig, load_config
from tools.repo_forensics.critical_module_checker import CriticalModuleReport, check_critical_modules
from tools.repo_forensics.evidence_auditor import EvidenceAuditReport, audit_evidence
from tools.repo_forensics.repo_cartographer import RepoMap, build_repo_map
from tools.repo_forensics.report_writer import write_repo_map_report
from tools.repo_forensics.runtime_wiring import RuntimeFlowReport, audit_runtime_wiring
from tools.repo_forensics.safety_boundary import SafetyBoundaryReport, audit_safety_boundaries
from tools.repo_forensics.test_reality import TestRealityReport, classify_tests


EXIT_POLICY_STRICT = "strict"
EXIT_POLICY_REPORT_ONLY = "report-only"
VALID_EXIT_POLICIES = {EXIT_POLICY_STRICT, EXIT_POLICY_REPORT_ONLY}


@dataclass(frozen=True)
class ForensicsCheckToggles:
    runtime_wiring: bool = True
    critical_callers: bool = True
    test_reality: bool = True
    safety_boundary: bool = True
    evidence_audit: bool = True
    architecture_drift: bool = True

    @property
    def skipped(self) -> list[str]:
        skipped: list[str] = []
        if not self.runtime_wiring:
            skipped.append("runtime_wiring")
        if not self.critical_callers:
            skipped.append("critical_callers")
        if not self.test_reality:
            skipped.append("test_reality")
        if not self.safety_boundary:
            skipped.append("safety_boundary")
        if not self.evidence_audit:
            skipped.append("evidence_audit")
        if not self.architecture_drift:
            skipped.append("architecture_drift")
        return skipped


@dataclass(frozen=True)
class ForensicsCounts:
    total_files: int = 0
    missing_required_entrypoints: int = 0
    missing_critical_modules: int = 0
    runtime_flow_failures: int = 0
    runtime_flow_unknowns: int = 0
    critical_caller_missing: int = 0
    critical_caller_test_only: int = 0
    critical_caller_unreferenced: int = 0
    fake_confidence_tests: int = 0
    unknown_tests: int = 0
    safety_critical: int = 0
    safety_high: int = 0
    safety_unknown: int = 0
    evidence_high: int = 0
    evidence_medium: int = 0
    evidence_unknown: int = 0
    drift_high: int = 0
    drift_medium: int = 0
    drift_unknown: int = 0

    @property
    def hard_failures(self) -> int:
        return sum(
            [
                self.missing_required_entrypoints,
                self.missing_critical_modules,
                self.runtime_flow_failures,
                self.critical_caller_missing,
                self.critical_caller_test_only,
                self.safety_critical,
                self.evidence_high,
                self.drift_high,
            ]
        )

    @property
    def unknowns(self) -> int:
        return sum(
            [
                self.runtime_flow_unknowns,
                self.critical_caller_unreferenced,
                self.unknown_tests,
                self.safety_high,
                self.safety_unknown,
                self.evidence_unknown,
                self.drift_unknown,
            ]
        )

    @property
    def warnings(self) -> int:
        return sum([self.fake_confidence_tests, self.evidence_medium, self.drift_medium])


@dataclass(frozen=True)
class ForensicsRunResult:
    report_path: Path
    counts: ForensicsCounts
    verdict: str
    exit_code: int
    skipped_checks: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ForensicsReports:
    config: ForensicsConfig
    repo_map: RepoMap
    runtime_report: RuntimeFlowReport | None = None
    critical_report: CriticalModuleReport | None = None
    test_reality_report: TestRealityReport | None = None
    safety_report: SafetyBoundaryReport | None = None
    evidence_report: EvidenceAuditReport | None = None
    drift_report: ArchitectureDriftReport | None = None


def run_forensics(
    repo_root: str | Path,
    config_path: str | Path,
    output_path: str | Path,
    *,
    toggles: ForensicsCheckToggles | None = None,
    exit_policy: str = EXIT_POLICY_STRICT,
) -> ForensicsRunResult:
    if exit_policy not in VALID_EXIT_POLICIES:
        raise ValueError(f"invalid_exit_policy policy={exit_policy}")

    root = Path(repo_root).resolve()
    config_file = _resolve_path(root, config_path)
    report_file = _resolve_path(root, output_path)
    enabled = toggles or ForensicsCheckToggles()

    reports = _run_reports(root, config_file, enabled)
    written_path = write_repo_map_report(
        reports.repo_map,
        report_file,
        runtime_report=reports.runtime_report,
        critical_report=reports.critical_report,
        test_reality_report=reports.test_reality_report,
        safety_report=reports.safety_report,
        evidence_report=reports.evidence_report,
        drift_report=reports.drift_report,
    )
    counts = _counts_from_reports(reports)
    verdict = _verdict_from_counts(counts)
    exit_code = _exit_code_from_counts(counts, exit_policy)
    return ForensicsRunResult(
        report_path=written_path,
        counts=counts,
        verdict=verdict,
        exit_code=exit_code,
        skipped_checks=enabled.skipped,
    )


def render_pr_summary(result: ForensicsRunResult) -> str:
    counts = result.counts
    lines = [
        "[repo-forensics] summary",
        f"[repo-forensics] verdict={result.verdict}",
        f"[repo-forensics] exit_code={result.exit_code}",
        f"[repo-forensics] report={result.report_path}",
        f"[repo-forensics] files={counts.total_files}",
        f"[repo-forensics] hard_failures={counts.hard_failures}",
        f"[repo-forensics] unknowns={counts.unknowns}",
        f"[repo-forensics] warnings={counts.warnings}",
        f"[repo-forensics] skipped_checks={','.join(result.skipped_checks) if result.skipped_checks else 'none'}",
        f"[repo-forensics] missing_required_entrypoints={counts.missing_required_entrypoints}",
        f"[repo-forensics] missing_critical_modules={counts.missing_critical_modules}",
        f"[repo-forensics] runtime_flow_failures={counts.runtime_flow_failures}",
        f"[repo-forensics] runtime_flow_unknowns={counts.runtime_flow_unknowns}",
        f"[repo-forensics] critical_caller_missing={counts.critical_caller_missing}",
        f"[repo-forensics] critical_caller_test_only={counts.critical_caller_test_only}",
        f"[repo-forensics] critical_caller_unreferenced={counts.critical_caller_unreferenced}",
        f"[repo-forensics] fake_confidence_tests={counts.fake_confidence_tests}",
        f"[repo-forensics] unknown_tests={counts.unknown_tests}",
        f"[repo-forensics] safety_critical={counts.safety_critical}",
        f"[repo-forensics] safety_high={counts.safety_high}",
        f"[repo-forensics] safety_unknown={counts.safety_unknown}",
        f"[repo-forensics] evidence_high={counts.evidence_high}",
        f"[repo-forensics] evidence_medium={counts.evidence_medium}",
        f"[repo-forensics] evidence_unknown={counts.evidence_unknown}",
        f"[repo-forensics] drift_high={counts.drift_high}",
        f"[repo-forensics] drift_medium={counts.drift_medium}",
        f"[repo-forensics] drift_unknown={counts.drift_unknown}",
    ]
    return "\n".join(lines)


def _run_reports(repo_root: Path, config_path: Path, toggles: ForensicsCheckToggles) -> ForensicsReports:
    config = load_config(config_path)
    repo_map = build_repo_map(repo_root, config)
    runtime_report = audit_runtime_wiring(repo_root, config) if toggles.runtime_wiring else None
    critical_report = check_critical_modules(repo_root, config) if toggles.critical_callers else None
    test_reality_report = classify_tests(repo_root, config) if toggles.test_reality else None
    safety_report = audit_safety_boundaries(repo_root, config) if toggles.safety_boundary else None
    evidence_report = audit_evidence(repo_root, config) if toggles.evidence_audit else None
    drift_report = detect_architecture_drift(repo_root, config) if toggles.architecture_drift else None
    return ForensicsReports(
        config=config,
        repo_map=repo_map,
        runtime_report=runtime_report,
        critical_report=critical_report,
        test_reality_report=test_reality_report,
        safety_report=safety_report,
        evidence_report=evidence_report,
        drift_report=drift_report,
    )


def _counts_from_reports(reports: ForensicsReports) -> ForensicsCounts:
    repo_map = reports.repo_map
    runtime_report = reports.runtime_report
    critical_report = reports.critical_report
    test_reality_report = reports.test_reality_report
    safety_report = reports.safety_report
    evidence_report = reports.evidence_report
    drift_report = reports.drift_report
    return ForensicsCounts(
        total_files=repo_map.inventory.total_files,
        missing_required_entrypoints=len(repo_map.missing_required_entrypoints),
        missing_critical_modules=len(repo_map.missing_critical_modules),
        runtime_flow_failures=len(runtime_report.failures) if runtime_report else 0,
        runtime_flow_unknowns=len(runtime_report.unknowns) if runtime_report else 0,
        critical_caller_missing=len(critical_report.missing) if critical_report else 0,
        critical_caller_test_only=len(critical_report.test_only) if critical_report else 0,
        critical_caller_unreferenced=len(critical_report.unreferenced) if critical_report else 0,
        fake_confidence_tests=len(test_reality_report.fake_confidence_tests) if test_reality_report else 0,
        unknown_tests=len(test_reality_report.unknown_tests) if test_reality_report else 0,
        safety_critical=len(safety_report.critical) if safety_report else 0,
        safety_high=len(safety_report.high) if safety_report else 0,
        safety_unknown=len(safety_report.unknown) if safety_report else 0,
        evidence_high=len(evidence_report.high) if evidence_report else 0,
        evidence_medium=len(evidence_report.medium) if evidence_report else 0,
        evidence_unknown=len(evidence_report.unknown) if evidence_report else 0,
        drift_high=len(drift_report.high) if drift_report else 0,
        drift_medium=len(drift_report.medium) if drift_report else 0,
        drift_unknown=len(drift_report.unknown) if drift_report else 0,
    )


def _verdict_from_counts(counts: ForensicsCounts) -> str:
    if counts.hard_failures:
        return "FAIL"
    if counts.unknowns:
        return "UNKNOWN"
    if counts.warnings:
        return "PASS_WITH_WARNINGS"
    return "PASS"


def _exit_code_from_counts(counts: ForensicsCounts, exit_policy: str) -> int:
    if exit_policy == EXIT_POLICY_REPORT_ONLY:
        return 0
    return 1 if counts.hard_failures else 0


def _resolve_path(repo_root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate
