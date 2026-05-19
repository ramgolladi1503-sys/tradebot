from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from tools.repo_forensics.config_loader import ForensicsConfig


@dataclass(frozen=True)
class SafetyFinding:
    path: str
    severity: str
    boundary: str
    evidence: str
    line: int | None = None


@dataclass(frozen=True)
class SafetyBoundaryReport:
    findings: list[SafetyFinding] = field(default_factory=list)

    @property
    def critical(self) -> list[SafetyFinding]:
        return [item for item in self.findings if item.severity == "CRITICAL"]

    @property
    def high(self) -> list[SafetyFinding]:
        return [item for item in self.findings if item.severity == "HIGH"]

    @property
    def medium(self) -> list[SafetyFinding]:
        return [item for item in self.findings if item.severity == "MEDIUM"]

    @property
    def unknown(self) -> list[SafetyFinding]:
        return [item for item in self.findings if item.severity == "UNKNOWN"]


def audit_safety_boundaries(repo_root: str | Path, config: ForensicsConfig) -> SafetyBoundaryReport:
    root = Path(repo_root).resolve()
    findings: list[SafetyFinding] = []
    for path in sorted(root.rglob("*.py")):
        if _should_skip(path, root, config):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(SafetyFinding(rel, "UNKNOWN", "file_read", "unreadable_python_file"))
            continue
        findings.extend(_audit_python_file(rel, source))
    for path in sorted(root.rglob("*.sh")):
        if _should_skip(path, root, config):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(SafetyFinding(rel, "UNKNOWN", "file_read", "unreadable_shell_file"))
            continue
        findings.extend(_audit_shell_file(rel, source))
    return SafetyBoundaryReport(findings=findings)


def _audit_python_file(path: str, source: str) -> list[SafetyFinding]:
    lowered = source.lower()
    findings: list[SafetyFinding] = []
    if _is_repo_forensics_path(path):
        findings.extend(_repo_forensics_safety_findings(path, lowered))
        return findings

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [SafetyFinding(path, "UNKNOWN", "python_parse", "syntax_error_unparsed")]

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            finding = _import_finding(path, node)
            if finding:
                findings.append(finding)
        elif isinstance(node, ast.Call):
            finding = _call_finding(path, node)
            if finding:
                findings.append(finding)
        elif isinstance(node, ast.Assign):
            findings.extend(_assignment_findings(path, node))

    if _looks_read_only_path(path):
        findings.extend(_read_only_field_findings(path, source))
    if _looks_paper_or_sim_path(path) and _contains_order_action(lowered):
        findings.append(SafetyFinding(path, "HIGH", "paper_sim_order_action", "order_action_marker_in_paper_or_sim_path"))
    return findings


def _audit_shell_file(path: str, source: str) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    lowered = source.lower()
    for idx, line in enumerate(source.splitlines(), start=1):
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        if "execution_mode=live" in lowered and "run_live" not in path:
            findings.append(SafetyFinding(path, "HIGH", "live_mode_default", "EXECUTION_MODE=LIVE outside run_live", idx))
        if "trading_mode=live" in lowered and "run_live" not in path:
            findings.append(SafetyFinding(path, "HIGH", "live_mode_default", "TRADING_MODE=LIVE outside run_live", idx))
    return findings


def _repo_forensics_safety_findings(path: str, lowered: str) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    forbidden_runtime_modules = [
        "core.kite_client",
        "core.market_data",
        "core.orchestrator",
        "strategies.trade_builder",
    ]
    for module in forbidden_runtime_modules:
        if module in lowered:
            findings.append(SafetyFinding(path, "CRITICAL", "forensics_runtime_import", f"forensics_references_runtime_module:{module}"))
    if _contains_order_action(lowered):
        findings.append(SafetyFinding(path, "CRITICAL", "forensics_order_action", "forensics_contains_order_action_marker"))
    return findings


def _import_finding(path: str, node: ast.Import | ast.ImportFrom) -> SafetyFinding | None:
    modules: list[str] = []
    if isinstance(node, ast.Import):
        modules.extend(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        modules.append(node.module)
        modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
    joined = " ".join(modules).lower()
    if _looks_paper_or_sim_path(path) and any(marker in joined for marker in ["kite", "broker", "execution_engine"]):
        return SafetyFinding(path, "CRITICAL", "paper_sim_broker_import", f"broker_adjacent_import:{joined}", getattr(node, "lineno", None))
    if _looks_read_only_path(path) and any(marker in joined for marker in ["execution_engine", "kite_client"]):
        return SafetyFinding(path, "HIGH", "readonly_execution_import", f"execution_import_in_readonly_path:{joined}", getattr(node, "lineno", None))
    return None


def _call_finding(path: str, node: ast.Call) -> SafetyFinding | None:
    name = _call_name(node).lower()
    order_actions = {"place_order", "modify_order", "cancel_order", "exit_order"}
    if any(action in name for action in order_actions):
        severity = "CRITICAL" if _looks_paper_or_sim_path(path) or _looks_read_only_path(path) else "HIGH"
        return SafetyFinding(path, severity, "order_action_call", f"order_action_call:{name}", getattr(node, "lineno", None))
    return None


def _assignment_findings(path: str, node: ast.Assign) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    names = [_target_name(target) for target in node.targets]
    value = _literal_value(node.value)
    for name in names:
        lowered = name.lower()
        if lowered in {"is_order_action", "broker_api_called", "live_order_action", "broker_order_action"} and value is True:
            severity = "CRITICAL" if _looks_read_only_path(path) else "HIGH"
            findings.append(SafetyFinding(path, severity, "unsafe_action_field", f"{name}=true", getattr(node, "lineno", None)))
        if lowered in {"execution_mode", "trading_mode"} and isinstance(value, str) and value.upper() == "LIVE" and "run_live" not in path:
            findings.append(SafetyFinding(path, "HIGH", "live_mode_default", f"{name}=LIVE", getattr(node, "lineno", None)))
    return findings


def _read_only_field_findings(path: str, source: str) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    lowered = source.lower()
    for marker in ["is_order_action=true", "broker_api_called=true", "live_order_action=true", "broker_order_action=true"]:
        if marker in lowered.replace(" ", ""):
            findings.append(SafetyFinding(path, "CRITICAL", "readonly_action_field", marker))
    return findings


def _contains_order_action(lowered: str) -> bool:
    markers = ["place_order", "modify_order", "cancel_order", "exit_order", "broker_api_called=true", "is_order_action=true"]
    compact = lowered.replace(" ", "")
    return any(marker in lowered or marker in compact for marker in markers)


def _looks_paper_or_sim_path(path: str) -> bool:
    lowered = path.lower()
    return "paper" in lowered or "/sim" in lowered or "sim_" in lowered or "dry_run" in lowered


def _looks_read_only_path(path: str) -> bool:
    lowered = path.lower()
    markers = ["dashboard", "report", "replay", "repo_forensics", "audit", "evidence", "read_only", "snapshot"]
    return any(marker in lowered for marker in markers)


def _is_repo_forensics_path(path: str) -> bool:
    return path.startswith("tools/repo_forensics/") or path == "scripts/run_repo_forensics.py"


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parent = _attribute_parent(func)
        return f"{parent}.{func.attr}" if parent else func.attr
    return ""


def _attribute_parent(node: ast.Attribute) -> str:
    value = node.value
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        parent = _attribute_parent(value)
        return f"{parent}.{value.attr}" if parent else value.attr
    return ""


def _target_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _literal_value(node: ast.expr) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def _should_skip(path: Path, repo_root: Path, config: ForensicsConfig) -> bool:
    rel = path.relative_to(repo_root)
    if any(part in config.excluded_directories for part in rel.parts):
        return True
    if any(part in {".git", ".venv", "venv", "__pycache__"} for part in rel.parts):
        return True
    return False
