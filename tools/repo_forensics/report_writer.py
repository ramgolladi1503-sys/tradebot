from __future__ import annotations

from pathlib import Path

from tools.repo_forensics.critical_module_checker import CriticalModuleReport, CriticalModuleStatus
from tools.repo_forensics.repo_cartographer import PathStatus, RepoMap
from tools.repo_forensics.runtime_wiring import FlowStepStatus, RuntimeFlowReport
from tools.repo_forensics.test_reality import TEST_CLASSES, TestRealityReport, TestRealityStatus


def write_repo_map_report(
    repo_map: RepoMap,
    output_path: str | Path,
    runtime_report: RuntimeFlowReport | None = None,
    critical_report: CriticalModuleReport | None = None,
    test_reality_report: TestRealityReport | None = None,
) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        render_repo_map_report(repo_map, runtime_report, critical_report, test_reality_report),
        encoding="utf-8",
    )
    return target


def render_repo_map_report(
    repo_map: RepoMap,
    runtime_report: RuntimeFlowReport | None = None,
    critical_report: CriticalModuleReport | None = None,
    test_reality_report: TestRealityReport | None = None,
) -> str:
    inventory = repo_map.inventory
    lines: list[str] = []
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
    lines.append(f"- Missing required entrypoints: {len(missing_entrypoints)}")
    lines.append(f"- Missing critical modules: {len(missing_critical)}")
    lines.append(f"- Runtime flow failures: {len(flow_failures)}")
    lines.append(f"- Runtime flow unknowns: {len(flow_unknowns)}")
    lines.append(f"- Critical modules missing caller proof: {len(critical_test_only) + len(critical_unreferenced)}")
    lines.append(f"- Fake-confidence tests: {len(fake_confidence)}")
    lines.append(f"- Unknown test files: {len(unknown_tests)}")
    lines.append("")
    if (
        missing_entrypoints
        or missing_critical
        or flow_failures
        or flow_unknowns
        or critical_test_only
        or critical_unreferenced
        or fake_confidence
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
        lines.append("")
    lines.append("## Verdict")
    lines.append("")
    if missing_entrypoints or missing_critical or flow_failures or critical_missing or critical_test_only:
        lines.append("FAIL — configured paths, runtime flow steps, or critical module caller proof failed.")
    elif flow_unknowns or critical_unreferenced:
        lines.append("UNKNOWN — configured paths exist, but one or more runtime/caller relationships are unproven.")
    elif fake_confidence:
        lines.append("PASS_WITH_WARNINGS — static structure passed, but fake-confidence test signals need review.")
    else:
        lines.append("PASS — configured entrypoints, critical modules, runtime flow references, caller proof, and test reality scan completed. This is still static proof only.")
    lines.append("")
    return "\n".join(lines)


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
