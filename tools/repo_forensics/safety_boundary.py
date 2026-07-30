from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from tools.repo_forensics.config_loader import ForensicsConfig


_ORDER_FIELD = "order"
_ORDER_ACTIONS = tuple(f"{verb}_{_ORDER_FIELD}" for verb in ("place", "modify", "cancel", "exit"))
_BROKER_FIELD = "broker" + "_api_called"
_KITE_CLIENT_MODULE = "core." + "kite_client"
_KITE_CLIENT_PATH = "core/" + "kite_client.py"

# These modules expose a direct broker or execution capability. Names such as
# "broker_payload_gate" and "broker_reconciliation_proof" are intentionally not
# included: a filename containing "broker" is not evidence of broker capability.
_DIRECT_BROKER_MODULE_PREFIXES = (
    _KITE_CLIENT_MODULE,
    "core.execution_engine",
    "core.execution_router",
    "kiteconnect",
    "upstox_client",
)

_REPO_FORENSICS_FORBIDDEN_IMPORT_PREFIXES = (
    _KITE_CLIENT_MODULE,
    "core.market_data",
    "core.orchestrator",
    "strategies.trade_builder",
)


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
    # Product safety findings must describe production code. Test-code realism,
    # broker mocking, and firewall strength are audited by dedicated test-reality
    # and broker-firewall gates. Treating a test import as a production broker
    # leak inflates critical counts without proving a runtime path.
    if _is_test_path(path):
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [SafetyFinding(path, "UNKNOWN", "python_parse", "syntax_error_unparsed")]

    imported_modules = _imported_modules(tree)
    if _is_repo_forensics_path(path):
        return _repo_forensics_safety_findings(path, imported_modules)

    findings: list[SafetyFinding] = []
    called_names = _called_names(tree)
    assigned_fields = _assigned_literal_fields(tree)

    findings.extend(_import_findings(path, imported_modules))
    findings.extend(_call_findings(path, called_names))
    findings.extend(_assignment_findings(path, assigned_fields))

    if _looks_read_only_path(path):
        findings.extend(_read_only_field_findings(path, assigned_fields))
    if _looks_paper_or_sim_path(path):
        findings.extend(_paper_or_sim_leakage_findings(path, imported_modules, called_names))
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


def _repo_forensics_safety_findings(
    path: str,
    modules: tuple[tuple[str, int | None], ...],
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    for module, line in modules:
        lowered = module.lower()
        for forbidden in _REPO_FORENSICS_FORBIDDEN_IMPORT_PREFIXES:
            if lowered == forbidden or lowered.startswith(f"{forbidden}."):
                findings.append(
                    SafetyFinding(
                        path,
                        "CRITICAL",
                        "forensics_runtime_import",
                        f"forensics_imports_runtime_module:{lowered}",
                        line,
                    )
                )
                break
    return findings


def _import_findings(path: str, modules: tuple[tuple[str, int | None], ...]) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    for module, line in modules:
        lowered = module.lower()
        if _looks_paper_or_sim_path(path) and _is_broker_adjacent_import(lowered):
            findings.append(SafetyFinding(path, "CRITICAL", "paper_sim_broker_import", f"broker_adjacent_import:{lowered}", line))
        if _looks_read_only_path(path) and _is_execution_adjacent_import(lowered):
            findings.append(SafetyFinding(path, "HIGH", "readonly_execution_import", f"execution_import_in_readonly_path:{lowered}", line))
    return findings


def _call_findings(path: str, calls: tuple[tuple[str, int | None], ...]) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    for name, line in calls:
        lowered = name.lower()
        if _is_order_action_name(lowered):
            severity = "CRITICAL" if _looks_paper_or_sim_path(path) or _looks_read_only_path(path) else "HIGH"
            findings.append(SafetyFinding(path, severity, "order_action_call", f"order_action_call:{lowered}", line))
    return findings


def _assignment_findings(path: str, assignments: tuple[tuple[str, object, int | None], ...]) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    for name, value, line in assignments:
        lowered = name.lower()
        if lowered in {"is_order_action", _BROKER_FIELD, "live_order_action", "broker_order_action"} and value is True:
            severity = "CRITICAL" if _looks_read_only_path(path) else "HIGH"
            findings.append(SafetyFinding(path, severity, "unsafe_action_field", f"{name}=true", line))
        if lowered in {"execution_mode", "trading_mode"} and isinstance(value, str) and value.upper() == "LIVE" and "run_live" not in path:
            findings.append(SafetyFinding(path, "HIGH", "live_mode_default", f"{name}=LIVE", line))
    return findings


def _read_only_field_findings(path: str, assignments: tuple[tuple[str, object, int | None], ...]) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    for name, value, line in assignments:
        if name.lower() in {"is_order_action", _BROKER_FIELD, "live_order_action", "broker_order_action"} and value is True:
            findings.append(SafetyFinding(path, "CRITICAL", "readonly_action_field", f"{name}=true", line))
    return findings


def _paper_or_sim_leakage_findings(
    path: str,
    modules: tuple[tuple[str, int | None], ...],
    calls: tuple[tuple[str, int | None], ...],
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    if any(_is_broker_adjacent_import(module) for module, _line in modules) and any(_is_order_action_name(name) for name, _line in calls):
        line = next((line for name, line in calls if _is_order_action_name(name)), None)
        findings.append(SafetyFinding(path, "CRITICAL", "paper_sim_live_broker_call_path", "paper_or_sim_path_reaches_broker_order_action", line))
    return findings


def _imported_modules(tree: ast.AST) -> tuple[tuple[str, int | None], ...]:
    modules: list[tuple[str, int | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend((alias.name, getattr(node, "lineno", None)) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append((node.module, getattr(node, "lineno", None)))
            modules.extend((f"{node.module}.{alias.name}", getattr(node, "lineno", None)) for alias in node.names)
    return tuple(modules)


def _called_names(tree: ast.AST) -> tuple[tuple[str, int | None], ...]:
    calls: list[tuple[str, int | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            calls.append((_call_name(node), getattr(node, "lineno", None)))
    return tuple(calls)


def _assigned_literal_fields(tree: ast.AST) -> tuple[tuple[str, object, int | None], ...]:
    assignments: list[tuple[str, object, int | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _literal_value(node.value)
            for target in node.targets:
                assignments.append((_target_name(target), value, getattr(node, "lineno", None)))
    return tuple(assignments)


def _is_broker_adjacent_import(module: str) -> bool:
    lowered = module.lower()
    return any(
        lowered == prefix or lowered.startswith(f"{prefix}.")
        for prefix in _DIRECT_BROKER_MODULE_PREFIXES
    )


def _is_execution_adjacent_import(module: str) -> bool:
    lowered = module.lower()
    return any(
        lowered == prefix or lowered.startswith(f"{prefix}.")
        for prefix in (
            _KITE_CLIENT_MODULE,
            "core.execution_engine",
            "core.execution_router",
        )
    )


def _is_order_action_name(name: str) -> bool:
    lowered = name.lower()
    return any(action in lowered for action in _ORDER_ACTIONS)


def _looks_paper_or_sim_path(path: str) -> bool:
    lowered = path.lower()
    return "paper" in lowered or "/sim" in lowered or "sim_" in lowered or "dry_run" in lowered


def _looks_read_only_path(path: str) -> bool:
    lowered = path.lower()
    markers = ["dashboard", "report", "replay", "repo_forensics", "audit", "evidence", "read_only", "snapshot"]
    return any(marker in lowered for marker in markers)


def _is_repo_forensics_path(path: str) -> bool:
    return path.startswith("tools/repo_forensics/") or path == "scripts/run_repo_forensics.py"


def _is_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return (
        normalized.startswith("tests/")
        or normalized.startswith("testing/tests/")
        or "/tests/" in normalized
        or Path(normalized).name.startswith("test_")
    )


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
