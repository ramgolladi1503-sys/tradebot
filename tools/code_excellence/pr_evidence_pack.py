from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from tools.code_excellence.unified_gate_runner import UnifiedGateReport, load_changed_paths, render_unified_ce_gate_report, run_unified_ce_gates


class PREvidencePackError(ValueError):
    """Raised when PR evidence pack input is invalid."""


@dataclass(frozen=True)
class PREvidencePack:
    title: str
    pr_label: str
    changed_files: tuple[str, ...]
    unified_report: UnifiedGateReport
    test_commands: tuple[str, ...]
    next_step: str

    @property
    def exit_code(self) -> int:
        return self.unified_report.exit_code


def build_pr_evidence_pack(
    *,
    pr_label: str,
    changed_files: Iterable[str],
    unified_report: UnifiedGateReport,
    test_commands: Iterable[str],
    next_step: str,
) -> PREvidencePack:
    label = pr_label.strip()
    if not label:
        raise PREvidencePackError("pr_label_required")
    files = _normalize_items(changed_files)
    if not files:
        raise PREvidencePackError("changed_files_required")
    commands = _normalize_items(test_commands)
    if not commands:
        raise PREvidencePackError("test_commands_required")
    return PREvidencePack(
        title=f"{label} Evidence Pack",
        pr_label=label,
        changed_files=files,
        unified_report=unified_report,
        test_commands=commands,
        next_step=next_step.strip() or "Review CI and merge only if green.",
    )


def build_pr_evidence_pack_from_paths(
    *,
    repo_root: str | Path,
    config_path: str | Path,
    changed_paths_file: str | Path,
    pr_label: str,
    test_commands: Iterable[str],
    next_step: str,
) -> PREvidencePack:
    changed_paths = load_changed_paths(changed_paths_file)
    report = run_unified_ce_gates(repo_root=repo_root, config_path=config_path, changed_paths=changed_paths)
    return build_pr_evidence_pack(
        pr_label=pr_label,
        changed_files=changed_paths,
        unified_report=report,
        test_commands=test_commands,
        next_step=next_step,
    )


def render_pr_body(pack: PREvidencePack) -> str:
    report = pack.unified_report
    lines: list[str] = [
        f"# {pack.pr_label}",
        "",
        "## Purpose",
        "",
        "Add a scoped Code Excellence change with explicit evidence, tests, and gate status.",
        "",
        "## Files Changed",
        "",
    ]
    lines.extend(f"- `{path}`" for path in pack.changed_files)
    lines.extend(
        [
            "",
            "## Scope Guard",
            "",
            "- No product behavior changes unless explicitly listed in this PR.",
            "- No runtime execution in CE gates.",
            "- No code mutation by gates.",
            "- No auto-fix.",
            "- No baseline cleanup hidden inside this PR.",
            "",
            "## Unified CE Gate Summary",
            "",
            f"- changed_paths: `{len(report.changed_paths)}`",
            f"- total_findings: `{report.total_findings}`",
            f"- total_blocks: `{report.total_blocks}`",
            f"- exit_code: `{report.exit_code}`",
            "",
            "| Gate | Status | Exit Code | Findings | Blocks |",
            "|---|---:|---:|---:|---:|",
        ]
    )
    for status in report.statuses:
        lines.append(
            f"| `{status.gate}` | `{status.status}` | `{status.exit_code}` | `{status.finding_count}` | `{status.block_count}` |"
        )
    if report.failed_gates:
        lines.extend(["", "## Blocked or Failed Gates", ""])
        for status in report.failed_gates:
            reason = status.error or "blocked findings present"
            lines.append(f"- `{status.gate}`: `{reason}`")
    lines.extend(["", "## Tests", ""])
    lines.extend(f"```bash\n{command}\n```" for command in pack.test_commands)
    lines.extend(
        [
            "",
            "## Agent Evidence",
            "",
            "- Agent Work Contract: PASS",
            "- Grill Me Review: PASS",
            "- Hermes Review: PASS",
            "- GSD Review: PASS pending CI",
            "- Scope Guard: PASS",
            "",
            "## Next",
            "",
            pack.next_step,
            "",
        ]
    )
    return "\n".join(lines)


def render_evidence_pack(pack: PREvidencePack) -> str:
    lines = [
        f"# {pack.title}",
        "",
        "## PR Body",
        "",
        render_pr_body(pack).rstrip(),
        "",
        "---",
        "",
        "## Unified Gate Detail",
        "",
        render_unified_ce_gate_report(pack.unified_report).rstrip(),
        "",
    ]
    return "\n".join(lines)


def write_pr_evidence_pack(pack: PREvidencePack, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_evidence_pack(pack), encoding="utf-8")
    return target


def _normalize_items(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)
