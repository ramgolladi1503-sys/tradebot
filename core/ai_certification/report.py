from __future__ import annotations

from pathlib import Path

from .bundle import canonical_json_bytes, resolve_under_root
from .contracts import CertificationReport


def render_markdown(report: CertificationReport) -> str:
    rows = []
    for gate in report.gates:
        rows.append(
            f"| `{gate.gate}` | `{gate.status.value}` | `{gate.reason_code}` | {gate.summary} |"
        )
    blockers = "\n".join(f"- `{item}`" for item in report.blockers) or "- None"
    warnings = "\n".join(f"- {item}" for item in report.warnings) or "- None"
    refs = "\n".join(f"- `{item}`" for item in report.knowledge_refs) or "- None"
    return "\n".join(
        [
            "# TradeBot AI QA Certification Report",
            "",
            f"- Run ID: `{report.run_id}`",
            f"- Strategy: `{report.strategy_id}`",
            f"- Evidence certification: **`{report.evidence_certification.value}`**",
            f"- Strategy verdict: **`{report.strategy_verdict.value}`**",
            f"- Policy: `{report.policy_version}`",
            f"- Repository commit: `{report.repository_commit}`",
            f"- Bundle digest: `{report.bundle_digest}`",
            f"- Trace ID: `{report.trace_id}`",
            "",
            "## Gate results",
            "",
            "| Gate | Status | Reason | Summary |",
            "|---|---|---|---|",
            *rows,
            "",
            "## Blockers",
            "",
            blockers,
            "",
            "## Warnings",
            "",
            warnings,
            "",
            "## Curated knowledge references",
            "",
            refs,
            "",
            "## Safety boundary",
            "",
            "This report was produced from read-only evidence. The certification module has no broker, order, risk-override, or strategy-mutation capability.",
        ]
    ) + "\n"


def write_report(
    report: CertificationReport,
    output_root: str | Path,
) -> dict[str, str]:
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    normalized = "".join(
        char for char in report.run_id if char.isalnum() or char in ("-", "_")
    )
    safe_name = normalized[:96].strip("-_") or f"report-{report.trace_id[:12]}"
    json_path = resolve_under_root(root, f"{safe_name}.json")
    markdown_path = resolve_under_root(root, f"{safe_name}.md")
    json_path.write_bytes(canonical_json_bytes(report.to_dict()) + b"\n")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}
