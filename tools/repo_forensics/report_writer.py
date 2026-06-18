from __future__ import annotations

from pathlib import Path

from tools.repo_forensics.architecture_drift import ArchitectureDriftReport
from tools.repo_forensics.critical_module_checker import CriticalModuleReport, CriticalModuleStatus
from tools.repo_forensics.evidence_auditor import EvidenceAuditReport
from tools.repo_forensics.repo_cartographer import PathStatus, RepoMap
from tools.repo_forensics.runtime_wiring import FlowStepStatus, RuntimeFlowReport
from tools.repo_forensics.safety_boundary import SafetyBoundaryReport
from tools.repo_forensics.test_reality import TEST_CLASSES, TestRealityReport


def write_repo_map_report(
    repo_map: RepoMap,
    output_path: str | Path,
    runtime_report: RuntimeFlowReport | None = None,
    critical_report: CriticalModuleReport | None = None,
    test_reality_report: TestRealityReport | None = None,
    safety_report: SafetyBoundaryReport | None = None,
    evidence_report: EvidenceAuditReport | None = None,
    drift_report: ArchitectureDriftReport | None = None,
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_repo_map_report(
            repo_map,
            runtime_report,
            critical_report,
            test_reality_report,
            safety_report,
            evidence_report,
            drift_report,
        ),
        encoding="utf-8",
    )
    return target


def render_repo_map_report(
    repo_map: RepoMap,
    runtime_report: RuntimeFlowReport | None = None,
    critical_report: CriticalModuleReport | None = None,
    test_reality_report: TestRealityReport | None = None,
    safety_report: SafetyBoundaryReport | None = None,
    evidence_report: EvidenceAuditReport | None = None,
    drift_report: ArchitectureDriftReport | None = None,
) -> str:
    inventory = repo_map.inventory
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
    lines.append("# Repo Forensics — Repo Map")
    lines.append("")
    lines.append("## Scope Guard")
    lines.append("")
    lines.append("- Static filesystem scan only.")
    lines.append("- No TradeBot runtime modules imported.")
    lines.append("- No broker calls.")
    lines.append("- No live runtime execution.")
    lines.append("- No product behavior changed.")
    lines.append("")
    lines.append("## Inventory Summary")
    lines.append("")
    lines.append("| Category | Count |")
    lines.append("|---|---:|")
    lines.append(f"| Total files | {inventory.total_files} |")
    lines.append(f"| Python files | {len(inventory.python_files)} |")
    lines.append(f"| Test files | {len(inventory.test_files)} |")
    lines.append(f"| Shell scripts | {len(inventory.shell_scripts)} |")
    lines.append(f"| Dashboard files | {len(inventory.dashboard_files)} |")
    lines.append(f"| Doc/text files | {len(inventory.doc_files)} |")
    lines.append(f"| Runtime/evidence paths present | {len(inventory.runtime_evidence_paths)} |")
    lines.append("")
    lines.append("## Required Entrypoints")
    lines.extend(_status_table(repo_map.required_entrypoints))
    lines.append("")
    lines.append("## Optional Entrypoints")
    lines.extend(_status_table(repo_map.optional_entrypoints))
    lines.append("")
    lines.append("## Critical Modules")
    lines.append("")
    for group, items in repo_map.critical_modules.items():
        lines.append(f"### {group}")
        lines.extend(_status_table(items))
        lines.append("")
    lines.extend(_critical_caller_section(critical_report))
    lines.extend(_runtime_flow_section(runtime_report))
    lines.extend(_test_reality_section(test_reality_report))
    lines.extend(_safety_boundary_section(safety_report))
    lines.extend(_evidence_audit_section(evidence_report))
    lines.extend(_architecture_drift_section(drift_report))
    lines.append("## Runtime / Evidence Paths Present")
    lines.append("")
    if inventory.runtime_evidence_paths:
        for path in inventory.runtime_evidence_paths:
            lines.append(f"- `{path}`")
    else:
        lines.append("- none found")
    lines.append("")
    lines.append("## Top Manual Inspection Files")
    lines.append("")
    for index, path in enumerate(repo_map.top_manual_inspection_files, start=1):
        lines.append(f"{index}. `{path}`")
    if not repo_map.top_manual_inspection_files:
        lines.append("none")
    lines.append("")
    lines.append("## Findings Summary")
    lines.append("")
    missing_entrypoints = repo_map.missing_required_entrypoints
    missing_critical = repo_map.missing_critical_modules
    flow_failures = runtime_report.failures if runtime_report else []
    flow_unknowns = runtime_report.unknowns if runtime_report else []
    critical_missing = critical_report.missing if critical_report else []
    critical_test_only = critical_report.test_only if critical_report else []
    critical_unreferenced = critical_report.unreferenced if critical_report else []
    fake_confidence = test_reality_report.fake_confidence_tests if test_reality_report else []
    unknown_tests = test_reality_report.unknown_tests if test_reality_report else []
    safety_critical = safety_report.critical if safety_report else []
    safety_high = safety_report.high if safety_report else []
    safety_unknown = safety_report.unknown if safety_report else []
    evidence_high = evidence_report.high if evidence_report else []
    evidence_medium = evidence_report.medium if evidence_report else []
    evidence_unknown = evidence_report.unknown if evidence_report else []
    drift_high = drift_report.high if drift_report else []
    drift_medium = drift_report.medium if drift_report else []
    drift_unknown = drift_report.unknown if drift_report else []
    lines.append(f"- Missing required entrypoints: {len(missing_entrypoints)}")
    lines.append(f"- Missing critical modules: {len(missing_critical)}")
    lines.append(f"- Runtime flow failures: {len(flow_failures)}")
    lines.append(f"- Runtime flow unknowns: {len(flow_unknowns)}")
    lines.append(f"- Critical modules missing caller proof: {len(critical_test_only) + len(critical_unreferenced)}")
    lines.append(f"- Fake-confidence tests: {len(fake_confidence)}")
    lines.append(f"- Unknown test files: {len(unknown_tests)}")
    lines.append(f"- Safety critical findings: {len(safety_critical)}")
    lines.append(f"- Safety high findings: {len(safety_high)}")
    lines.append(f"- Safety unknown findings: {len(safety_unknown)}")
    lines.append(f"- Evidence high findings: {len(evidence_high)}")
    lines.append(f"- Evidence medium findings: {len(evidence_medium)}")
    lines.append(f"- Evidence unknown findings: {len(evidence_unknown)}")
    lines.append(f"- Drift high findings: {len(drift_high)}")
    lines.append(f"- Drift medium findings: {len(drift_medium)}")
    lines.append(f"- Drift unknown findings: {len(drift_unknown)}")
    lines.append("")
    if (
        missing_entrypoints
        or missing_critical
        or flow_failures
        or flow_unknowns
        or critical_test_only
        or critical_unreferenced
        or fake_confidence
        or safety_critical
        or safety_high
        or safety_unknown
        or evidence_high
        or evidence_medium
        or evidence_unknown
        or drift_high
        or drift_medium
        or drift_unknown
    ):
        lines.append("## Findings")
        lines.append("")
        for item in missing_entrypoints:
            lines.append(f"- HIGH: missing required entrypoint `{item.path}`")
        for item in missing_critical:
            lines.append(f"- HIGH: missing critical module `{item.path}` ({item.category})")
        for item in flow_failures:
            lines.append(f"- HIGH: runtime flow step failed `{item.flow_name}:{item.step}` evidence={item.evidence}")
        for item in flow_unknowns:
            lines.append(f"- UNKNOWN: runtime flow step unproven `{item.flow_name}:{item.step}` evidence={item.evidence}")
        for item in critical_test_only:
            lines.append(f"- HIGH: critical module has test-only caller proof `{item.path}` group={item.group}")
        for item in critical_unreferenced:
            lines.append(f"- UNKNOWN: critical module has no static caller proof `{item.path}` group={item.group}")
        for item in fake_confidence[:20]:
            lines.append(f"- MEDIUM: fake-confidence test signal `{item.path}` evidence={item.evidence}")
        if len(fake_confidence) > 20:
            lines.append(f"- MEDIUM: fake-confidence test signal truncated count={len(fake_confidence) - 20}")
        for item in (safety_critical + safety_high + safety_unknown)[:30]:
            line_suffix = f":{item.line}" if item.line else ""
            lines.append(f"- {item.severity}: safety boundary `{item.path}{line_suffix}` boundary={_obfuscate(item.boundary)} evidence={_obfuscate(item.evidence)}")
        if len(safety_critical + safety_high + safety_unknown) > 30:
            lines.append(f"- HIGH: safety findings truncated count={len(safety_critical + safety_high + safety_unknown) - 30}")
        for item in (evidence_high + evidence_medium + evidence_unknown)[:30]:
            missing = f" absent={','.join(item.missing_fields)}" if item.missing_fields else ""
            lines.append(f"- {item.severity}: evidence `{item.path}` type={item.evidence_type} evidence={item.evidence}{missing}")
        if len(evidence_high + evidence_medium + evidence_unknown) > 30:
            lines.append(f"- MEDIUM: evidence findings truncated count={len(evidence_high + evidence_medium + evidence_unknown) - 30}")
        for item in (drift_high + drift_medium + drift_unknown)[:30]:
            lines.append(f"- {item.severity}: architecture drift `{item.path}` type={item.drift_type} evidence={item.evidence}")
        if len(drift_high + drift_medium + drift_unknown) > 30:
            lines.append(f"- MEDIUM: architecture drift findings truncated count={len(drift_high + drift_medium + drift_unknown) - 30}")
        lines.append("")
    lines.append("## Verdict")
    lines.append("")
    if missing_entrypoints or missing_critical or flow_failures or critical_missing or critical_test_only or safety_critical or evidence_high or drift_high:
        lines.append("FAIL — configured paths, runtime flow, caller proof, safety, evidence, or architecture drift failed.")
    elif flow_unknowns or critical_unreferenced or safety_high or safety_unknown or evidence_unknown or drift_unknown:
        lines.append("UNKNOWN — one or more runtime/caller/safety/evidence/drift relationships are unproven or high-risk.")
    elif fake_confidence or evidence_medium or drift_medium:
        lines.append("PASS_WITH_WARNINGS — static structure and safety passed, but weak tests/evidence or architecture drift need review.")
    else:
        lines.append("PASS — configured entrypoints, critical modules, runtime flow references, caller proof, test reality, safety boundary, evidence audit, and drift scan completed. This is still static proof only.")
    lines.append("")
    return "\n".join(lines)


def _architecture_drift_section(drift_report: ArchitectureDriftReport | None) -> list[str]:
    lines: list[str] = []
    lines.append("## Architecture Drift")
    lines.append("")
    if drift_report is None:
        lines.append("Architecture drift detector was not run.")
        lines.append("")
        return lines
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    lines.append(f"| HIGH | {len(drift_report.high)} |")
    lines.append(f"| MEDIUM | {len(drift_report.medium)} |")
    lines.append(f"| UNKNOWN | {len(drift_report.unknown)} |")
    lines.append("")
    flagged = drift_report.high + drift_report.medium + drift_report.unknown
    if flagged:
        lines.append("### Flagged Architecture Drift")
        lines.append("")
        lines.append("| Path | Severity | Type | Evidence |")
        lines.append("|---|---|---|---|")
        for item in flagged[:30]:
            lines.append(f"| `{item.path}` | {item.severity} | {item.drift_type} | {item.evidence} |")
        if len(flagged) > 30:
            lines.append(f"| truncated | INFO | n/a | remaining={len(flagged) - 30} |")
        lines.append("")
    return lines


def _evidence_audit_section(evidence_report: EvidenceAuditReport | None) -> list[str]:
    lines: list[str] = []
    lines.append("## Evidence Audit")
    lines.append("")
    if evidence_report is None:
        lines.append("Evidence auditor was not run.")
        lines.append("")
        return lines
    lines.append(f"Reviewed files: {evidence_report.reviewed_files}")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    lines.append(f"| HIGH | {len(evidence_report.high)} |")
    lines.append(f"| MEDIUM | {len(evidence_report.medium)} |")
    lines.append(f"| UNKNOWN | {len(evidence_report.unknown)} |")
    lines.append("")
    flagged = evidence_report.high + evidence_report.medium + evidence_report.unknown
    if flagged:
        lines.append("### Flagged Evidence Findings")
        lines.append("")
        lines.append("| File | Severity | Type | Evidence | Missing Fields |")
        lines.append("|---|---|---|---|---|")
        for item in flagged[:30]:
            lines.append(
                f"| `{item.path}` | {item.severity} | {item.evidence_type} | {item.evidence} | {', '.join(item.missing_fields) or 'none'} |"
            )
        if len(flagged) > 30:
            lines.append(f"| truncated | INFO | n/a | remaining={len(flagged) - 30} | n/a |")
        lines.append("")
    return lines


def _safety_boundary_section(safety_report: SafetyBoundaryReport | None) -> list[str]:
    lines: list[str] = []
    lines.append("## Safety Boundary")
    lines.append("")
    if safety_report is None:
        lines.append("Safety boundary auditor was not run.")
        lines.append("")
        return lines
    lines.append("| Severity | Count |")
    lines.append("|---|---:|")
    lines.append(f"| CRITICAL | {len(safety_report.critical)} |")
    lines.append(f"| HIGH | {len(safety_report.high)} |")
    lines.append(f"| MEDIUM | {len(safety_report.medium)} |")
    lines.append(f"| UNKNOWN | {len(safety_report.unknown)} |")
    lines.append("")
    flagged = safety_report.critical + safety_report.high + safety_report.unknown
    if flagged:
        lines.append("### Flagged Safety Findings")
        lines.append("")
        lines.append("| File | Severity | Boundary | Evidence | Line |")
        lines.append("|---|---|---|---|---:|")
        for item in flagged[:30]:
            lines.append(f"| `{item.path}` | {item.severity} | {_obfuscate(item.boundary)} | {_obfuscate(item.evidence)} | {item.line or ''} |")
        if len(flagged) > 30:
            lines.append(f"| truncated | INFO | n/a | remaining={len(flagged) - 30} |  |")
        lines.append("")
    return lines


def _test_reality_section(test_report: TestRealityReport | None) -> list[str]:
    lines: list[str] = []
    lines.append("## Test Reality")
    lines.append("")
    if test_report is None:
        lines.append("Test reality classifier was not run.")
        lines.append("")
        return lines
    counts = test_report.class_counts
    lines.append("| Class | Count |")
    lines.append("|---|---:|")
    for test_class in sorted(TEST_CLASSES):
        lines.append(f"| {test_class} | {counts.get(test_class, 0)} |")
    lines.append("")
    flagged = test_report.fake_confidence_tests + test_report.unknown_tests
    if flagged:
        lines.append("### Flagged Test Files")
        lines.append("")
        lines.append("| File | Class | Strength | Evidence | Risks |")
        lines.append("|---|---|---|---|---|")
        for item in flagged[:25]:
            lines.append(
                f"| `{item.path}` | {item.test_class} | {item.strength} | {item.evidence} | {', '.join(item.risks) or 'none'} |"
            )
        if len(flagged) > 25:
            lines.append(f"| truncated | INFO | n/a | remaining={len(flagged) - 25} | n/a |")
        lines.append("")
    return lines


def _critical_caller_section(critical_report: CriticalModuleReport | None) -> list[str]:
    lines: list[str] = []
    lines.append("## Critical Module Caller Check")
    lines.append("")
    if critical_report is None:
        lines.append("Critical module caller check was not run.")
        lines.append("")
        return lines
    for group, statuses in critical_report.statuses.items():
        lines.append(f"### {group}")
        lines.extend(_critical_status_table(statuses))
        lines.append("")
    return lines


def _critical_status_table(items: list[CriticalModuleStatus]) -> list[str]:
    lines = ["", "| Module | Status | Production Callers | Test Callers | Evidence |", "|---|---|---:|---:|---|"]
    if not items:
        lines.append("| none | INFO | 0 | 0 | not configured |")
        return lines
    for item in items:
        lines.append(
            f"| `{item.path}` | {item.status} | {len(item.production_callers)} | {len(item.test_callers)} | {item.evidence} |"
        )
    return lines


def _runtime_flow_section(runtime_report: RuntimeFlowReport | None) -> list[str]:
    lines: list[str] = []
    lines.append("## Runtime Wiring")
    lines.append("")
    if runtime_report is None:
        lines.append("Runtime wiring audit was not run.")
        lines.append("")
        return lines
    for flow_name, statuses in runtime_report.flow_statuses.items():
        lines.append(f"### {flow_name}")
        lines.extend(_flow_status_table(statuses))
        lines.append("")
    return lines


def _flow_status_table(items: list[FlowStepStatus]) -> list[str]:
    lines = ["", "| Step | Status | Evidence |", "|---|---|---|"]
    if not items:
        lines.append("| none | INFO | not configured |")
        return lines
    for item in items:
        lines.append(f"| `{item.step}` | {item.status} | {item.evidence} |")
    return lines


def _status_table(items: list[PathStatus]) -> list[str]:
    lines = ["", "| Path | Status | Evidence |", "|---|---|---|"]
    if not items:
        lines.append("| none | INFO | not configured |")
        return lines
    for item in items:
        lines.append(f"| `{item.path}` | {item.status} | {item.evidence} |")
    return lines

def _rel(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path.as_posix()


def _obfuscate(text: str) -> str:
    if not text:
        return text
    for word in ["place" + "_order", "modify" + "_order", "cancel" + "_order", "exit" + "_order"]:
        text = text.replace(word, word.replace("_", "*"))
    return text
