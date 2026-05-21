from __future__ import annotations

import json
from pathlib import Path

from core.debug_forensics.models import ForensicsReport, Severity
from core.paths import reports_dir


REPORT_SCHEMA_VERSION = 1


def _report_dir(base_dir: str | Path | None = None) -> Path:
    base = Path(base_dir).expanduser() if base_dir is not None else reports_dir()
    target = base / "debug_forensics"
    target.mkdir(parents=True, exist_ok=True)
    return target


def report_exit_code(report: ForensicsReport) -> int:
    blocking = {Severity.BLOCKER, Severity.SAFETY_VIOLATION, Severity.INSUFFICIENT_EVIDENCE}
    return 1 if any(finding.severity in blocking for finding in report.findings) else 0


def render_markdown(report: ForensicsReport) -> str:
    lines = [
        f"# Debug Forensics Report — {report.profile}",
        "",
        "## Contract",
        "",
        f"- schema_version: {REPORT_SCHEMA_VERSION}",
        f"- profile: {report.profile}",
        f"- selected_run_id: {report.selected_run_id or 'UNKNOWN'}",
        f"- evidence_valid: {str(report.evidence_valid).lower()}",
        "- is_order_action: false",
        "- mode: READ_ONLY_FORENSICS",
        "",
        "## Flow Position",
        "",
        f"- last_confirmed_event: {report.last_confirmed_event or 'NONE'}",
        f"- first_missing_event: {report.first_missing_event or 'NONE'}",
        "",
        "## Findings",
        "",
    ]
    for finding in report.findings:
        lines.extend([
            f"### {finding.severity.value} — {finding.code}",
            "",
            finding.message,
            "",
        ])
        if finding.evidence:
            lines.extend([
                "```json",
                json.dumps(finding.evidence, indent=2, sort_keys=True, default=str),
                "```",
                "",
            ])

    lines.extend(["## Killed Hypotheses", ""])
    for item in report.killed_hypotheses:
        lines.append(f"- {item}")
    lines.extend(["", "## Next Diagnostic Scope", "", report.next_diagnostic_scope, "", "## Forbidden Distractions", ""])
    for item in report.forbidden_distractions:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## Report Boundary",
        "",
        "- Diagnostic artifact only.",
        "- No automatic runtime mutation.",
        "- No strategy-quality claim.",
    ])
    return "\n".join(lines) + "\n"


def write_reports(report: ForensicsReport, *, base_dir: str | Path | None = None) -> tuple[Path, Path]:
    target = _report_dir(base_dir)
    json_path = target / f"{report.profile}_latest.json"
    md_path = target / f"{report.profile}_{report.selected_run_id or 'unknown'}.md"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path
