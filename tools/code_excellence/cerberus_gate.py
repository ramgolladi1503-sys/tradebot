from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

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

    if file_path.suffix == ".py":
        findings = list(
            _scan_python_source(
                relative=relative,
                source=text,
                forbidden_markers=forbidden_markers,
                required_non_action_fields=required_non_action_fields,
            )
        )
    else:
        findings = list(
            _scan_text_source(
                relative=relative,
                text=text,
                forbidden_markers=forbidden_markers,
                required_non_action_fields=required_non_action_fields,
            )
        )

    if not findings:
        return (_pass_finding(relative),)
    return tuple(findings)


def _scan_python_source(
    *,
    relative: str,
    source: str,
    forbidden_markers: tuple[str, ...],
    required_non_action_fields: tuple[str, ...],
) -> Iterator[CerberusGateFinding]:
    """Inspect executable Python syntax and ignore vocabulary in strings/comments."""

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        yield CerberusGateFinding(
            path=relative,
            verdict="BLOCK",
            reason="python_source_unparseable",
            marker="syntax_error",
            line_number=exc.lineno or 0,
            evidence=str(exc),
            risks=("static_gate_blind_spot",),
        )
        return

    for name, line_number in _python_boundary_references(tree):
        for marker in forbidden_markers:
            if marker and _boundary_marker_matches(name, marker):
                yield CerberusGateFinding(
                    path=relative,
                    verdict="BLOCK",
                    reason="forbidden_boundary_marker_in_scoped_file",
                    marker=marker,
                    line_number=line_number,
                    evidence=name,
                    risks=("restricted_boundary_regression",),
                )

    required = [_split_required_field(field) for field in required_non_action_fields]
    for name, value, line_number, evidence in _python_field_assignments(tree):
        for required_name, expected in required:
            if name != required_name or not expected:
                continue
            if not _literal_matches_expected(value, expected):
                yield CerberusGateFinding(
                    path=relative,
                    verdict="BLOCK",
                    reason="non_action_field_not_explicitly_false",
                    marker=f"{required_name}={expected}",
                    line_number=line_number,
                    evidence=evidence,
                    risks=("actionability_evidence_regression",),
                )


def _scan_text_source(
    *,
    relative: str,
    text: str,
    forbidden_markers: tuple[str, ...],
    required_non_action_fields: tuple[str, ...],
) -> Iterator[CerberusGateFinding]:
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for marker in forbidden_markers:
            if marker and marker in stripped:
                yield CerberusGateFinding(
                    path=relative,
                    verdict="BLOCK",
                    reason="forbidden_boundary_marker_in_scoped_file",
                    marker=marker,
                    line_number=line_number,
                    evidence=stripped,
                    risks=("restricted_boundary_regression",),
                )
        for field in required_non_action_fields:
            name, expected = _split_required_field(field)
            if (
                name
                and expected
                and _line_contains_required_field_assignment(stripped, name)
                and not _line_matches_required_field(stripped, name, expected)
            ):
                yield CerberusGateFinding(
                    path=relative,
                    verdict="BLOCK",
                    reason="non_action_field_not_explicitly_false",
                    marker=field,
                    line_number=line_number,
                    evidence=stripped,
                    risks=("actionability_evidence_regression",),
                )


def _python_boundary_references(tree: ast.AST) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _qualified_name(node.func)
            if name:
                yield name, getattr(node, "lineno", 0)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, getattr(node, "lineno", 0)
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module, getattr(node, "lineno", 0)
            for alias in node.names:
                yield f"{node.module}.{alias.name}", getattr(node, "lineno", 0)


def _python_field_assignments(tree: ast.AST) -> Iterator[tuple[str, object, int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _literal_value(node.value)
            for target in node.targets:
                name = _assignment_target_name(target)
                if name:
                    yield name, value, getattr(node, "lineno", 0), ast.unparse(node)
        elif isinstance(node, ast.AnnAssign):
            name = _assignment_target_name(node.target)
            if name:
                yield name, _literal_value(node.value), getattr(node, "lineno", 0), ast.unparse(node)
        elif isinstance(node, ast.Dict):
            for key, value_node in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    yield (
                        key.value,
                        _literal_value(value_node),
                        getattr(key, "lineno", getattr(node, "lineno", 0)),
                        ast.unparse(node),
                    )
        elif isinstance(node, ast.keyword) and node.arg:
            yield node.arg, _literal_value(node.value), getattr(node, "lineno", 0), ast.unparse(node)


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _qualified_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _assignment_target_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _literal_value(node: ast.AST | None) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    return object()


def _literal_matches_expected(value: object, expected: str) -> bool:
    if expected == "false":
        return value is False
    if expected == "true":
        return value is True
    return str(value).strip().lower() == expected


def _boundary_marker_matches(reference: str, marker: str) -> bool:
    lowered_reference = reference.lower()
    lowered_marker = marker.lower()
    return lowered_reference == lowered_marker or lowered_reference.endswith(f".{lowered_marker}") or lowered_marker in lowered_reference


def _pass_finding(relative: str) -> CerberusGateFinding:
    return CerberusGateFinding(
        path=relative,
        verdict="PASS",
        reason="no_restricted_boundary_marker_found",
        marker="",
        line_number=0,
        evidence="static_scan_passed",
        risks=(),
    )


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


def _normalize_assignment_line(line: str) -> str:
    return line.replace(" ", "").replace('"', "").replace("'", "").lower()


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
