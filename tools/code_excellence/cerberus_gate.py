from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
from typing import Iterable

from tools.code_excellence.config import load_code_excellence_agent_parameters
from tools.repo_forensics.config_loader import ConfigError


class CerberusGateError(ValueError):
    """Raised when Cerberus gate input is missing or invalid."""


DEFAULT_CHANGED_FILE_LIMIT = 2000
TEXT_FILE_SUFFIXES = {".py", ".md", ".txt", ".yaml", ".yml", ".json", ".sh"}


@dataclass(frozen=True)
class CerberusGateFinding:
    path: str
    verdict: str
    reason: str
    marker: str
    line_number: int
    evidence: str
    risks: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CerberusGateReport:
    repo_root: str
    config_path: str
    scoped_paths: tuple[str, ...]
    findings: tuple[CerberusGateFinding, ...]
    protected_modes: tuple[str, ...]
    forbidden_import_markers: tuple[str, ...]
    required_non_action_fields: tuple[str, ...]
    output_required: tuple[str, ...]

    @property
    def blocked_findings(self) -> tuple[CerberusGateFinding, ...]:
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


def run_cerberus_gate(
    *,
    repo_root: str | Path,
    config_path: str | Path,
    changed_paths: Iterable[str] | None = None,
) -> CerberusGateReport:
    root = Path(repo_root).resolve()
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = root / config_file
    params = load_code_excellence_agent_parameters(config_file)
    cerberus = params.cerberus
    scoped_paths = _normalize_changed_paths(changed_paths)
    paths_to_scan = _paths_to_scan(root, scoped_paths)
    forbidden_markers = cerberus.require_list("forbidden_import_markers")
    required_non_action_fields = cerberus.require_list("required_non_action_fields")
    findings = tuple(
        finding
        for path in paths_to_scan
        for finding in _scan_file(
            repo_root=root,
            file_path=path,
            forbidden_markers=forbidden_markers,
            required_non_action_fields=required_non_action_fields,
            line_numbers=_added_line_numbers(
                repo_root=root,
                relative=_relative_path(root, path),
            ),
        )
    )
    return CerberusGateReport(
        repo_root=str(root),
        config_path=str(config_file),
        scoped_paths=scoped_paths,
        findings=findings,
        protected_modes=cerberus.require_list("protected_modes"),
        forbidden_import_markers=forbidden_markers,
        required_non_action_fields=required_non_action_fields,
        output_required=cerberus.require_list("output_required"),
    )


def render_cerberus_gate_report(report: CerberusGateReport) -> str:
    lines: list[str] = [
        "# CE-09 Cerberus Safety Regression Gate Report",
        "",
        "## Scope Guard",
        "",
        "- Static scoped-file review only.",
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
        "## Protected Modes",
        "",
    ]
    lines.extend(_bullet_lines(report.protected_modes))
    lines.extend(["", "## Required Non-Action Fields", ""])
    lines.extend(_bullet_lines(report.required_non_action_fields))
    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("- No scoped safety boundary findings.")
    else:
        lines.append("| Path | Line | Verdict | Reason | Marker |")
        lines.append("|---|---:|---|---|---|")
        for finding in report.findings:
            lines.append(
                f"| `{finding.path}` | `{finding.line_number}` | `{finding.verdict}` | `{finding.reason}` | `{finding.marker}` |"
            )
    if report.blocked_findings:
        lines.extend(["", "## Blocked Findings", ""])
        for finding in report.blocked_findings:
            lines.append(f"- `{finding.path}:{finding.line_number}` blocked because `{finding.reason}`")
    lines.append("")
    return "\n".join(lines)


def write_cerberus_gate_report(report: CerberusGateReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_cerberus_gate_report(report), encoding="utf-8")
    return target


def read_changed_paths_file(path: str | Path) -> tuple[str, ...]:
    source = Path(path)
    if not source.exists():
        raise CerberusGateError(f"changed_paths_file_not_found path={source}")
    paths = tuple(line.strip() for line in source.read_text(encoding="utf-8").splitlines() if line.strip())
    if len(paths) > DEFAULT_CHANGED_FILE_LIMIT:
        raise CerberusGateError(f"too_many_changed_paths count={len(paths)} limit={DEFAULT_CHANGED_FILE_LIMIT}")
    return paths


def _scan_file(
    *,
    repo_root: Path,
    file_path: Path,
    forbidden_markers: tuple[str, ...],
    required_non_action_fields: tuple[str, ...],
    line_numbers: set[int] | None = None,
) -> tuple[CerberusGateFinding, ...]:
    relative = _relative_path(repo_root, file_path)
    if file_path.name == ".gsd-forensics.yaml":
        return ()
    if not file_path.exists() or not file_path.is_file() or file_path.suffix not in TEXT_FILE_SUFFIXES:
        return ()
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CerberusGateError(f"cerberus_gate_cannot_read_text path={relative}") from exc

    findings: list[CerberusGateFinding] = []
    is_test_file = "tests" in Path(relative).parts
    proven_false_fields = {
        name
        for field in required_non_action_fields
        for name, expected in (_split_required_field(field),)
        if is_test_file and name and expected == "false" and _file_proves_field_false(text, name)
    }
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line_numbers is not None and line_number not in line_numbers:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for marker in forbidden_markers:
            if marker and marker in stripped:
                findings.append(
                    CerberusGateFinding(
                        path=relative,
                        verdict="BLOCK",
                        reason="forbidden_boundary_marker_in_scoped_file",
                        marker=marker,
                        line_number=line_number,
                        evidence=stripped,
                        risks=("restricted_boundary_regression",),
                    )
                )
        for field in required_non_action_fields:
            name, expected = _split_required_field(field)
            if (
                name
                and expected
                and _line_contains_required_field_assignment(stripped, name)
                and not _line_matches_required_field(stripped, name, expected)
            ):
                if is_test_file and name in proven_false_fields:
                    continue
                findings.append(
                    CerberusGateFinding(
                        path=relative,
                        verdict="BLOCK",
                        reason="non_action_field_not_explicitly_false",
                        marker=field,
                        line_number=line_number,
                        evidence=stripped,
                        risks=("actionability_evidence_regression",),
                    )
                )
    if not findings:
        return (
            CerberusGateFinding(
                path=relative,
                verdict="PASS",
                reason="no_restricted_boundary_marker_found",
                marker="",
                line_number=0,
                evidence="static_scan_passed",
                risks=(),
            ),
        )
    return tuple(findings)


def _added_line_numbers(*, repo_root: Path, relative: str) -> set[int] | None:
    """Return added lines for a PR diff; None preserves the fail-closed fallback."""

    base_ref = str(os.getenv("CERBERUS_BASE_REF") or "").strip()
    if not base_ref:
        github_base = str(os.getenv("GITHUB_BASE_REF") or "").strip()
        base_ref = f"origin/{github_base}" if github_base else "origin/main"
    try:
        result = subprocess.run(
            ["git", "diff", "--unified=0", f"{base_ref}...HEAD", "--", relative],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    if not result.stdout.strip():
        return set()
    added: set[int] = set()
    for match in re.finditer(r"^@@ .* \+(\d+)(?:,(\d+))? @@", result.stdout, re.MULTILINE):
        start = int(match.group(1))
        count = int(match.group(2) or "1")
        added.update(range(start, start + count))
    return added


def _paths_to_scan(repo_root: Path, scoped_paths: tuple[str, ...]) -> tuple[Path, ...]:
    if not scoped_paths:
        raise CerberusGateError("changed_paths_required_for_cerberus_gate")
    paths: list[Path] = []
    for relative in scoped_paths:
        path = (repo_root / relative).resolve()
        if not _is_relative_to(path, repo_root):
            raise CerberusGateError(f"changed_path_outside_repo path={relative}")
        paths.append(path)
    return tuple(paths)


def _split_required_field(field: str) -> tuple[str, str]:
    if "=" not in field:
        return field.strip(), ""
    name, expected = field.split("=", 1)
    return name.strip(), expected.strip().lower()


def _line_contains_required_field_assignment(line: str, name: str) -> bool:
    stripped = line.strip()
    if _is_standalone_string_literal(stripped):
        return False
    normalized = _normalize_assignment_line(stripped)
    lowered_name = name.lower()
    return any(
        marker in normalized
        for marker in (
            f"{lowered_name}=",
            f"{lowered_name}:",
            f"{lowered_name}is",
        )
    )


def _line_matches_required_field(line: str, name: str, expected: str) -> bool:
    normalized = _normalize_assignment_line(line)
    expected_pairs = {
        f"{name.lower()}={expected}",
        f"{name.lower()}:{expected}",
    }
    if expected == "false":
        expected_pairs.update({
            f"{name.lower()}=false",
            f"{name.lower()}:false",
            f"{name.lower()}isfalse",
        })
    return any(pair in normalized for pair in expected_pairs)


def _file_proves_field_false(text: str, name: str) -> bool:
    lowered_name = name.lower()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("assert "):
            continue
        normalized = _normalize_assignment_line(stripped)
        if lowered_name in normalized and any(
            marker in normalized
            for marker in (
                f"{lowered_name}=false",
                f"{lowered_name}:false",
                f"{lowered_name}isfalse",
                f"[{lowered_name}]isfalse",
            )
        ):
            return True
    return False


def _normalize_assignment_line(line: str) -> str:
    return line.replace(" ", "").replace("\"", "").replace("'", "").lower()


def _is_standalone_string_literal(line: str) -> bool:
    candidate = line.rstrip(",").strip()
    if len(candidate) < 2:
        return False
    return (candidate[0] == candidate[-1]) and candidate[0] in {"'", '"'}


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


def _relative_path(repo_root: Path, file_path: Path) -> str:
    return str(file_path.resolve().relative_to(repo_root)).replace("\\", "/")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _bullet_lines(items: Iterable[str]) -> list[str]:
    values = tuple(item for item in items if item)
    if not values:
        return ["- none"]
    return [f"- `{item}`" for item in values]
