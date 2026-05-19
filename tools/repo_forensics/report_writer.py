from __future__ import annotations

from pathlib import Path

from tools.repo_forensics.repo_cartographer import PathStatus, RepoMap


def write_repo_map_report(repo_map: RepoMap, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_repo_map_report(repo_map), encoding="utf-8")
    return target


def render_repo_map_report(repo_map: RepoMap) -> str:
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
    lines.append(f"- Missing required entrypoints: {len(missing_entrypoints)}")
    lines.append(f"- Missing critical modules: {len(missing_critical)}")
    lines.append("")
    if missing_entrypoints or missing_critical:
        lines.append("## Findings")
        lines.append("")
        for item in missing_entrypoints:
            lines.append(f"- HIGH: missing required entrypoint `{item.path}`")
        for item in missing_critical:
            lines.append(f"- HIGH: missing critical module `{item.path}` ({item.category})")
        lines.append("")
    lines.append("## Verdict")
    lines.append("")
    if missing_entrypoints or missing_critical:
        lines.append("FAIL — configured paths are missing.")
    else:
        lines.append("PASS — configured entrypoints and critical modules are present. Runtime wiring is not proven by this PR.")
    lines.append("")
    return "\n".join(lines)


def _status_table(items: list[PathStatus]) -> list[str]:
    lines = ["", "| Path | Status | Evidence |", "|---|---|---|"]
    if not items:
        lines.append("| none | INFO | not configured |")
        return lines
    for item in items:
        lines.append(f"| `{item.path}` | {item.status} | {item.evidence} |")
    return lines
