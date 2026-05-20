from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tools.code_excellence.config import CodeExcellenceAgentParameters, load_code_excellence_agent_parameters
from tools.repo_forensics.config_loader import ConfigError, ForensicsConfig, load_config
from tools.repo_forensics.test_reality import TestRealityReport, TestRealityStatus, classify_tests


class MinervaGateError(ValueError):
    """Raised when Minerva gate input is missing or invalid."""


BLOCKED_CLASSES = {"FAKE_CONFIDENCE", "SHAPE_ONLY", "UNKNOWN"}
DEFAULT_CHANGED_FILE_LIMIT = 200


@dataclass(frozen=True)
class MinervaGateFinding:
    path: str
    test_class: str
    strength: str
    verdict: str
    reason: str
    evidence: str
    risks: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MinervaGateReport:
    repo_root: str
    config_path: str
    scoped_paths: tuple[str, ...]
    findings: tuple[MinervaGateFinding, ...]
    required_negative_tests: tuple[str, ...]
    weak_test_patterns: tuple[str, ...]

    @property
    def blocked_findings(self) -> tuple[MinervaGateFinding, ...]:
        return tuple(finding for finding in self.findings if finding.verdict == "BLOCK")

    @property
    def pass_count(self) -> int:
        return sum(1 for finding in self.findings if finding.verdict == "PASS")

    @property
    def block_count(self) -> int:
        return len(self.blocked_findings)

    @property
    def exit_code(self) -> int:
        return 1 if self.block_count else 0


def run_minerva_gate(
    *,
    repo_root: str | Path,
    config_path: str | Path,
    changed_paths: Iterable[str] | None = None,
) -> MinervaGateReport:
    root = Path(repo_root).resolve()
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = root / config_file
    config = load_config(config_file)
    params = load_code_excellence_agent_parameters(config_file)
    test_report = classify_tests(root, config)
    scoped_paths = _normalize_changed_paths(changed_paths)
    statuses = _select_statuses(test_report, scoped_paths)
    findings = tuple(_to_gate_finding(status, params) for status in statuses)
    return MinervaGateReport(
        repo_root=str(root),
        config_path=str(config_file),
        scoped_paths=scoped_paths,
        findings=findings,
        required_negative_tests=params.minerva.require_list("required_negative_tests"),
        weak_test_patterns=params.minerva.require_list("weak_test_patterns"),
    )


def render_minerva_gate_report(report: MinervaGateReport) -> str:
    lines: list[str] = [
        "# CE-08 Minerva Test Reality Gate Report",
        "",
        "## Scope Guard",
        "",
        "- Static test-file review only.",
        "- No product runtime execution.",
        "- No code mutation.",
        "- No auto-fix.",
        "",
        "## Summary",
        "",
        f"- repo_root: `{report.repo_root}`",
        f"- config_path: `{report.config_path}`",
        f"- scoped_paths: `{len(report.scoped_paths)}`",
        f"- findings: `{len(report.findings)}`",
        f"- pass_count: `{report.pass_count}`",
        f"- block_count: `{report.block_count}`",
        "",
        "## Required Negative Tests From Config",
        "",
    ]
    lines.extend(_bullet_lines(report.required_negative_tests))
    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("- No scoped test files found.")
    else:
        lines.append("| Path | Class | Strength | Verdict | Reason |")
        lines.append("|---|---|---|---|---|")
        for finding in report.findings:
            lines.append(
                f"| `{finding.path}` | `{finding.test_class}` | `{finding.strength}` | `{finding.verdict}` | {finding.reason} |"
            )
    if report.blocked_findings:
        lines.extend(["", "## Blocked Findings", ""])
        for finding in report.blocked_findings:
            lines.append(f"- `{finding.path}` blocked because `{finding.reason}`")
    lines.append("")
    return "\n".join(lines)


def write_minerva_gate_report(report: MinervaGateReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_minerva_gate_report(report), encoding="utf-8")
    return target


def read_changed_paths_file(path: str | Path) -> tuple[str, ...]:
    source = Path(path)
    if not source.exists():
        raise MinervaGateError(f"changed_paths_file_not_found path={source}")
    paths = tuple(line.strip() for line in source.read_text(encoding="utf-8").splitlines() if line.strip())
    if len(paths) > DEFAULT_CHANGED_FILE_LIMIT:
        raise MinervaGateError(f"too_many_changed_paths count={len(paths)} limit={DEFAULT_CHANGED_FILE_LIMIT}")
    return paths


def _select_statuses(report: TestRealityReport, scoped_paths: tuple[str, ...]) -> tuple[TestRealityStatus, ...]:
    statuses = tuple(sorted(report.tests, key=lambda item: item.path))
    if not scoped_paths:
        return statuses
    scoped = set(scoped_paths)
    return tuple(status for status in statuses if status.path in scoped)


def _to_gate_finding(status: TestRealityStatus, params: CodeExcellenceAgentParameters) -> MinervaGateFinding:
    configured_classes = set(params.minerva.require_list("classes"))
    if status.test_class not in configured_classes:
        raise ConfigError(f"minerva_class_not_configured class={status.test_class}")

    verdict = "BLOCK" if status.test_class in BLOCKED_CLASSES else "PASS"
    reason = _reason_for(status)
    return MinervaGateFinding(
        path=status.path,
        test_class=status.test_class,
        strength=status.strength,
        verdict=verdict,
        reason=reason,
        evidence=status.evidence,
        risks=tuple(status.risks),
    )


def _reason_for(status: TestRealityStatus) -> str:
    if status.test_class == "FAKE_CONFIDENCE":
        return "fake_confidence_test_not_valid_proof"
    if status.test_class == "SHAPE_ONLY":
        return "shape_only_test_not_valid_proof"
    if status.test_class == "UNKNOWN":
        return "unknown_test_reality_not_valid_proof"
    if status.strength == "weak":
        return "weak_test_requires_review"
    return "test_reality_accepted"


def _normalize_changed_paths(changed_paths: Iterable[str] | None) -> tuple[str, ...]:
    if not changed_paths:
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in changed_paths:
        text = str(raw).strip().replace("\\", "/")
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return tuple(sorted(normalized))


def _bullet_lines(items: Iterable[str]) -> list[str]:
    values = tuple(item for item in items if item)
    if not values:
        return ["- none"]
    return [f"- `{item}`" for item in values]
