from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.repo_forensics.config_loader import ConfigError, load_config


class EvidenceGateError(ValueError):
    """Raised when Evidence gate input is missing or invalid."""


DEFAULT_CHANGED_FILE_LIMIT = 2000
EVIDENCE_SUFFIXES = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"}


@dataclass(frozen=True)
class EvidenceGateFinding:
    path: str
    verdict: str
    reason: str
    field: str
    line_number: int
    evidence: str
    risks: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class EvidenceGateReport:
    repo_root: str
    config_path: str
    scoped_paths: tuple[str, ...]
    findings: tuple[EvidenceGateFinding, ...]
    required_fields: tuple[str, ...]
    weak_evidence_patterns: tuple[str, ...]
    evidence_paths: tuple[str, ...]
    output_required: tuple[str, ...]

    @property
    def blocked_findings(self) -> tuple[EvidenceGateFinding, ...]:
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


def run_evidence_gate(
    *,
    repo_root: str | Path,
    config_path: str | Path,
    changed_paths: Iterable[str] | None = None,
) -> EvidenceGateReport:
    root = Path(repo_root).resolve()
    config_file = Path(config_path)
    if not config_file.is_absolute():
        config_file = root / config_file
    config = load_config(config_file)
    auditor = _load_evidence_auditor(config.data)
    scoped_paths = _normalize_changed_paths(changed_paths)
    paths_to_scan = _paths_to_scan(root, scoped_paths)
    required_fields = _require_list(auditor, "required_fields")
    weak_patterns = _require_list(auditor, "weak_evidence_patterns")
    evidence_paths = _require_list(auditor, "evidence_paths")
    findings = tuple(
        finding
        for path in paths_to_scan
        for finding in _scan_evidence_file(
            repo_root=root,
            file_path=path,
            required_fields=required_fields,
            weak_patterns=weak_patterns,
            evidence_paths=evidence_paths,
        )
    )
    return EvidenceGateReport(
        repo_root=str(root),
        config_path=str(config_file),
        scoped_paths=scoped_paths,
        findings=findings,
        required_fields=required_fields,
        weak_evidence_patterns=weak_patterns,
        evidence_paths=evidence_paths,
        output_required=_require_list(auditor, "output_required"),
    )


def render_evidence_gate_report(report: EvidenceGateReport) -> str:
    lines: list[str] = [
        "# CE-10 Evidence Contract Gate Report",
        "",
        "## Scope Guard",
        "",
        "- Static scoped evidence-file review only.",
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
        "## Required Fields",
        "",
    ]
    lines.extend(_bullet_lines(report.required_fields))
    lines.extend(["", "## Weak Evidence Patterns", ""])
    lines.extend(_bullet_lines(report.weak_evidence_patterns))
    lines.extend(["", "## Findings", ""])
    if not report.findings:
        lines.append("- No scoped evidence findings.")
    else:
        lines.append("| Path | Line | Verdict | Reason | Field/Pattern |")
        lines.append("|---|---:|---|---|---|")
        for finding in report.findings:
            lines.append(
                f"| `{finding.path}` | `{finding.line_number}` | `{finding.verdict}` | `{finding.reason}` | `{finding.field}` |"
            )
    if report.blocked_findings:
        lines.extend(["", "## Blocked Findings", ""])
        for finding in report.blocked_findings:
            lines.append(f"- `{finding.path}:{finding.line_number}` blocked because `{finding.reason}`")
    lines.append("")
    return "\n".join(lines)


def write_evidence_gate_report(report: EvidenceGateReport, output_path: str | Path) -> Path:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_evidence_gate_report(report), encoding="utf-8")
    return target


def read_changed_paths_file(path: str | Path) -> tuple[str, ...]:
    source = Path(path)
    if not source.exists():
        raise EvidenceGateError(f"changed_paths_file_not_found path={source}")
    paths = tuple(line.strip() for line in source.read_text(encoding="utf-8").splitlines() if line.strip())
    if len(paths) > DEFAULT_CHANGED_FILE_LIMIT:
        raise EvidenceGateError(f"too_many_changed_paths count={len(paths)} limit={DEFAULT_CHANGED_FILE_LIMIT}")
    return paths


def _scan_evidence_file(
    *,
    repo_root: Path,
    file_path: Path,
    required_fields: tuple[str, ...],
    weak_patterns: tuple[str, ...],
    evidence_paths: tuple[str, ...],
) -> tuple[EvidenceGateFinding, ...]:
    relative = _relative_path(repo_root, file_path)
    if not _is_evidence_path(relative, evidence_paths):
        return ()
    if not file_path.exists() or not file_path.is_file() or file_path.suffix not in EVIDENCE_SUFFIXES:
        return ()
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceGateError(f"evidence_gate_cannot_read_text path={relative}") from exc

    findings: list[EvidenceGateFinding] = []
    field_values = _extract_field_values(file_path, text)
    for required_field in required_fields:
        if required_field not in field_values:
            findings.append(
                EvidenceGateFinding(
                    path=relative,
                    verdict="BLOCK",
                    reason="required_evidence_field_missing",
                    field=required_field,
                    line_number=0,
                    evidence="field not found",
                    risks=("traceability_gap",),
                )
            )
            continue
        value = str(field_values.get(required_field, "")).strip()
        if not value:
            findings.append(
                EvidenceGateFinding(
                    path=relative,
                    verdict="BLOCK",
                    reason="required_evidence_field_empty",
                    field=required_field,
                    line_number=0,
                    evidence="empty field",
                    risks=("traceability_gap",),
                )
            )
    if file_path.suffix == ".json":
        findings.extend(
            _scan_weak_patterns(
                relative=relative,
                fragments=_json_text_fragments(_load_json_object(text, file_path)),
                weak_patterns=weak_patterns,
            )
        )
    elif file_path.suffix == ".jsonl":
        fragments: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = _load_json_object(stripped, file_path)
            except EvidenceGateError:
                fragments.append(stripped)
                continue
            fragments.extend(_json_text_fragments(payload))
        findings.extend(
            _scan_weak_patterns(
                relative=relative,
                fragments=tuple(fragments),
                weak_patterns=weak_patterns,
            )
        )
    else:
        findings.extend(
            _scan_weak_patterns(
                relative=relative,
                fragments=tuple(text.splitlines()),
                weak_patterns=weak_patterns,
            )
        )
    if not findings:
        return (
            EvidenceGateFinding(
                path=relative,
                verdict="PASS",
                reason="evidence_contract_satisfied",
                field="",
                line_number=0,
                evidence="static_scan_passed",
                risks=(),
            ),
        )
    return tuple(findings)


def _extract_field_values(path: Path, text: str) -> dict[str, Any]:
    if path.suffix == ".json":
        payload = _load_json_object(text, path)
        return {str(key): value for key, value in payload.items()}
    if path.suffix == ".jsonl":
        values: dict[str, Any] = {}
        for line in text.splitlines():
            if not line.strip():
                continue
            payload = _load_json_object(line, path)
            values.update({str(key): value for key, value in payload.items()})
        return values
    return _extract_text_fields(text)


def _extract_text_fields(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip().strip("-*") .strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped:
            key, value = stripped.split(":", 1)
        elif "=" in stripped:
            key, value = stripped.split("=", 1)
        else:
            continue
        key = key.strip().strip("`\"'").lower()
        value = value.strip().strip("`\"'")
        if key:
            values[key] = value
    return values


def _scan_weak_patterns(
    *,
    relative: str,
    fragments: tuple[str, ...],
    weak_patterns: tuple[str, ...],
) -> list[EvidenceGateFinding]:
    findings: list[EvidenceGateFinding] = []
    for line_number, fragment in enumerate(fragments, start=1):
        lowered = fragment.lower()
        for pattern in weak_patterns:
            if _pattern_matches(lowered, pattern):
                findings.append(
                    EvidenceGateFinding(
                        path=relative,
                        verdict="BLOCK",
                        reason="weak_evidence_pattern_found",
                        field=pattern,
                        line_number=line_number,
                        evidence=fragment.strip(),
                        risks=("weak_evidence",),
                    )
                )
    return findings


def _json_text_fragments(payload: Any) -> tuple[str, ...]:
    fragments: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, str):
            fragments.append(value)
        elif isinstance(value, Mapping):
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    return tuple(fragments)


def _load_json_object(text: str, path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EvidenceGateError(f"evidence_gate_invalid_json path={path} error={exc.msg}") from exc
    if not isinstance(payload, Mapping):
        raise EvidenceGateError(f"evidence_gate_json_must_be_object path={path}")
    return payload


def _pattern_matches(lowered_line: str, pattern: str) -> bool:
    tokens = [token for token in pattern.lower().replace("_", " ").split() if token not in {"only", "field"}]
    if not tokens:
        return False
    return all(token in lowered_line for token in tokens)


def _paths_to_scan(repo_root: Path, scoped_paths: tuple[str, ...]) -> tuple[Path, ...]:
    if not scoped_paths:
        raise EvidenceGateError("changed_paths_required_for_evidence_gate")
    paths: list[Path] = []
    for relative in scoped_paths:
        path = (repo_root / relative).resolve()
        if not _is_relative_to(path, repo_root):
            raise EvidenceGateError(f"changed_path_outside_repo path={relative}")
        paths.append(path)
    return tuple(paths)


def _load_evidence_auditor(config_data: dict[str, Any]) -> dict[str, Any]:
    raw = config_data.get("agent_parameters", {}).get("evidence_auditor")
    if not isinstance(raw, dict):
        raise ConfigError("agent_parameters_missing agent=evidence_auditor")
    return raw


def _require_list(mapping: dict[str, Any], key: str) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list) or not value:
        raise ConfigError(f"evidence_auditor_list_required key={key}")
    return tuple(str(item) for item in value)


def _is_evidence_path(relative_path: str, evidence_paths: tuple[str, ...]) -> bool:
    normalized = relative_path.replace("\\", "/")
    return any(normalized == prefix.strip("/") or normalized.startswith(prefix.strip("/") + "/") for prefix in evidence_paths)


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
