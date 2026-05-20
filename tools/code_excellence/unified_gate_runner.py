from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tools.code_excellence.cerberus_gate import (
    CerberusGateError,
    CerberusGateReport,
    run_cerberus_gate,
)
from tools.code_excellence.evidence_gate import (
    EvidenceGateError,
    EvidenceGateReport,
    run_evidence_gate,
)
from tools.code_excellence.minerva_gate import (
    MinervaGateError,
    MinervaGateReport,
    read_changed_paths_file,
    run_minerva_gate,
)
from tools.repo_forensics.config_loader import ConfigError


class UnifiedGateRunnerError(ValueError):
    """Raised when the unified CE gate runner input is invalid."""


@dataclass(frozen=True)
class GateRunStatus:
    gate: str
    status: str
    exit_code: int
    finding_count: int
    block_count: int
    error: str = ""


@dataclass(frozen=True)
class UnifiedGateReport:
    repo_root: str
    config_path: str
    changed_paths: tuple[str, ...]
    statuses: tuple[GateRunStatus, ...]
    minerva: MinervaGateReport | None
    cerberus: CerberusGateReport | None
    evidence: EvidenceGateReport | None

    @property
    def exit_code(self) -> int:
        return 1 if any(status.exit_code != 0 for status in self.statuses) else 0

    @property
    def failed_gates(self) -> tuple[GateRunStatus, ...]:
        return tuple(status for status in self.statuses if status.exit_code != 0)

    @property
    def total_findings(self) -> int:
        return sum(status.finding_count for status in self.statuses)

    @property
    def total_blocks(self) -> int:
        return sum(status.block_count for status in self.statuses)


def run_unified_ce_gates(
    *,
    repo_root: str | Path,
    config_path: str | Path,
    changed_paths: Iterable[str],
) -> UnifiedGateReport:
    root = Path(repo_root).resolve()
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = root / config_file
    scoped_paths = _normalize_changed_paths(changed_paths)
    if not scoped_paths:
        raise UnifiedGateRunnerError("changed_paths_required_for_unified_ce_gates")

    statuses: list[GateRunStatus] = []
    minerva_report: MinervaGateReport | None = None
    cerberus_report: CerberusGateReport | None = None
    evidence_report: EvidenceGateReport | None = None

    minerva_report, minerva_status = _run_gate(
        gate="minerva",
        fn=lambda: run_minerva_gate(repo_root=root, config_path=config_file, changed_paths=scoped_paths),
    )
    statuses.append(minerva_status)

    cerberus_report, cerberus_status = _run_gate(
        gate="cerberus",
        fn=lambda: run_cerberus_gate(repo_root=root, config_path=config_file, changed_paths=scoped_paths),
    )
    statuses.append(cerberus_status)

    evidence_report, evidence_status = _run_gate(
        gate="evidence",
        fn=lambda: run_evidence_gate(repo_root=root, config_path=config_file, changed_paths=scoped_paths),
    )
    statuses.append(evidence_status)

    return UnifiedGateReport(
        repo_root=str(root),
        config_path=str(config_file),
        changed_paths=scoped_paths,
        statuses=tuple(statuses),
        minerva=minerva_report,
        cerberus=cerberus_report,
        evidence=evidence_report,
    )


def render_unified_ce_gate_report(report: UnifiedGateReport) -> str:
    lines: list[str] = [
        "# CE-11 Unified Code Excellence Gate Report",
        "",
        "## Scope Guard",
        "",
        "- Runs CE gates on scoped changed paths only.",
        "- No product runtime execution.",
        "- No code mutation.",
        "- No auto-fix.",
        "",
        "## Summary",
        "",
        f"- repo_root: `{report.repo_root}`",
        f"- config_path: `{report.config_path}`",
        f"- changed_paths: `{len(report.changed_paths)}`",
        f"- total_findings: `{report.total_findings}`",
        f"- total_blocks: `{report.total_blocks}`",
        f"- exit_code: `{report.exit_code}`",
        "",
        "## Gate Status",
        "",
        "| Gate | Status | Exit Code | Findings | Blocks | Error |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for status in report.statuses:
        lines.append(
            f"| `{status.gate}` | `{status.status}` | `{status.exit_code}` | `{status.finding_count}` | `{status.block_count}` | {status.error or ''} |"
        )
    lines.extend(["", "## Changed Paths", ""])
    lines.extend(f"- `{path}`" for path in report.changed_paths)
    lines.extend(_render_gate_details("Minerva", report.minerva))
    lines.extend(_render_gate_details("Cerberus", report.cerberus))
    lines.extend(_render_gate_details("Evidence", report.evidence))
    if report.failed_gates:
        lines.extend(["", "## Failed Gates", ""])
        for status in report.failed_gates:
            lines.append(f"- `{status.gate}` failed with exit_code `{status.exit_code}`: {status.error or 'blocked findings present'}")
    lines.append("")
    return "\n".join(lines)


def write_unified_ce_gate_report(report: UnifiedGateReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_unified_ce_gate_report(report), encoding="utf-8")
    return target


def load_changed_paths(path: str | Path) -> tuple[str, ...]:
    return read_changed_paths_file(path)


def _run_gate(gate: str, fn):
    try:
        report = fn()
    except (ConfigError, MinervaGateError, CerberusGateError, EvidenceGateError, ValueError) as exc:
        return None, GateRunStatus(
            gate=gate,
            status="ERROR",
            exit_code=2,
            finding_count=0,
            block_count=0,
            error=str(exc),
        )
    return report, GateRunStatus(
        gate=gate,
        status="BLOCK" if report.exit_code else "PASS",
        exit_code=report.exit_code,
        finding_count=len(report.findings),
        block_count=report.block_count,
        error="",
    )


def _render_gate_details(title: str, report) -> list[str]:
    lines = ["", f"## {title} Findings", ""]
    if report is None:
        lines.append("- Gate did not produce a report.")
        return lines
    if not report.findings:
        lines.append("- No findings.")
        return lines
    lines.append("| Path | Verdict | Reason |")
    lines.append("|---|---|---|")
    for finding in report.findings:
        lines.append(f"| `{finding.path}` | `{finding.verdict}` | `{finding.reason}` |")
    return lines


def _normalize_changed_paths(changed_paths: Iterable[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in changed_paths:
        text = str(raw).strip().replace("\\", "/")
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(sorted(normalized))
