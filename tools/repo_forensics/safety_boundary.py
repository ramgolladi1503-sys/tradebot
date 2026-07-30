from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from tools.repo_forensics.config_loader import ForensicsConfig


_ORDER_FIELD = "order"
_ORDER_ACTIONS = tuple(
    f"{verb}_{_ORDER_FIELD}" for verb in ("place", "modify", "cancel", "exit")
)
_BROKER_FIELD = "broker" + "_api_called"
_KITE_CLIENT_MODULE = "core." + "kite_client"

_DIRECT_BROKER_MODULE_PREFIXES = (
    _KITE_CLIENT_MODULE,
    "core.execution_engine",
    "core.execution_router",
    "kiteconnect",
    "upstox_client",
)
_EXECUTION_OWNER_PATHS = {
    "core/execution_engine.py",
    "core/execution_router.py",
    "core/kite_client.py",
}
_REPO_FORENSICS_FORBIDDEN_IMPORT_PREFIXES = (
    _KITE_CLIENT_MODULE,
    "core.market_data",
    "core.orchestrator",
    "strategies.trade_builder",
)
_ACTION_FIELDS = {
    "is_order_action",
    _BROKER_FIELD,
    "live_order_action",
    "broker_order_action",
}


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


def audit_safety_boundaries(
    repo_root: str | Path, config: ForensicsConfig
) -> SafetyBoundaryReport:
    root = Path(repo_root).resolve()
    findings: list[SafetyFinding] = []
    for path in sorted(root.rglob("*.py")):
        if _should_skip(path, root, config):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(
                SafetyFinding(rel, "UNKNOWN", "file_read", "unreadable_python_file")
            )
            continue
        findings.extend(_audit_python_file(rel, source))

    for path in sorted(root.rglob("*.sh")):
        if _should_skip(path, root, config):
            continue
        rel = path.relative_to(root).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            findings.append(
                SafetyFinding(rel, "UNKNOWN", "file_read", "unreadable_shell_file")
            )
            continue
        findings.extend(_audit_shell_file(rel, source))

    return SafetyBoundaryReport(findings=_dedupe_findings(findings))


def _audit_python_file(path: str, source: str) -> list[SafetyFinding]:
    if _is_test_path(path):
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [
            SafetyFinding(path, "UNKNOWN", "python_parse", "syntax_error_unparsed")
        ]

    imported_modules = _imported_modules(tree)
    if _is_repo_forensics_path(path):
        return _dedupe_findings(
            _repo_forensics_safety_findings(path, imported_modules)
        )

    called_names = _called_names(tree)
    assigned_fields = _assigned_literal_fields(tree)
    findings: list[SafetyFinding] = []
    findings.extend(_import_findings(path, imported_modules))
    findings.extend(_call_findings(path, called_names))
    findings.extend(_assignment_findings(path, assigned_fields))
    if _looks_paper_or_sim_path(path):
        findings.extend(
            _paper_or_sim_leakage_findings(path, imported_modules, called_names)
        )
    return _dedupe_findings(findings)


def _audit_shell_file(path: str, source: str) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    for idx, line in enumerate(source.splitlines(), start=1):
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        lowered = clean.lower().replace('"', "").replace("'", "")
        if "execution_mode=live" in lowered and "run_live" not in path:
            findings.append(
                SafetyFinding(
                    path,
                    "HIGH",
                    "live_mode_default",
                    "EXECUTION_MODE=LIVE outside run_live",
                    idx,
                )
            )
        if "trading_mode=live" in lowered and "run_live" not in path:
            findings.append(
                SafetyFinding(
                    path,
                    "HIGH",
                    "live_mode_default",
                    "TRADING_MODE=LIVE outside run_live",
                    idx,
                )
            )
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


def _import_findings(
    path: str, modules: tuple[tuple[str, int | None], ...]
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    for module, line in modules:
        lowered = module.lower()
        if _looks_paper_or_sim_path(path) and _is_broker_adjacent_import(lowered):
            findings.append(
                SafetyFinding(
                    path,
                    "HIGH",
                    "paper_sim_broker_import",
                    f"broker_adjacent_import:{lowered}",
                    line,
                )
            )
        if _looks_read_only_path(path) and _is_execution_adjacent_import(lowered):
            findings.append(
                SafetyFinding(
                    path,
                    "HIGH",
                    "readonly_execution_import",
                    f"execution_import_in_readonly_path:{lowered}",
                    line,
                )
            )
    return findings


def _call_findings(
    path: str, calls: tuple[tuple[str, int | None], ...]
) -> list[SafetyFinding]:
    if path in _EXECUTION_OWNER_PATHS:
        return []
    findings: list[SafetyFinding] = []
    for name, line in calls:
        lowered = name.lower()
        if not _is_order_action_name(lowered):
            continue
        if _looks_paper_or_sim_path(path) or _looks_read_only_path(path):
            severity = "CRITICAL"
        else:
            severity = "HIGH"
        findings.append(
            SafetyFinding(
                path,
                severity,
                "order_action_call",
                f"order_action_call:{lowered}",
                line,
            )
        )
    return findings


def _assignment_findings(
    path: str, assignments: tuple[tuple[str, object, int | None], ...]
) -> list[SafetyFinding]:
    findings: list[SafetyFinding] = []
    for name, value, line in assignments:
        lowered = name.lower()
        if lowered in _ACTION_FIELDS and value is True:
            severity = "CRITICAL" if _looks_read_only_path(path) else "HIGH"
            findings.append(
                SafetyFinding(
                    path,
                    severity,
                    "unsafe_action_field",
                    f"{name}=true",
                    line,
                )
            )
        if (
            lowered in {"execution_mode", "trading_mode"}
            and isinstance(value, str)
            and value.upper() == "LIVE"
            and "run_live" not in path
        ):
            findings.append(
                SafetyFinding(
                    path,
                    "HIGH",
                    "live_mode_default",
                    f"{name}=LIVE",
                    line,
                )
            )
    return findings


def _paper_or_sim_leakage_findings(
    path: str,
    modules: tuple[tuple[str, int | None], ...],
    calls: tuple[tuple[str, int | None], ...],
) -> list[SafetyFinding]:
    has_broker_import = any(
        _is_broker_adjacent_import(module) for module, _line in modules
    )
    order_call_line = next(
        (line for name, line in calls if _is_order_action_name(name)), None
    )
    if not has_broker_import or order_call_line is None:
        return []
    return [
        SafetyFinding(
            path,
            "CRITICAL",
            "paper_sim_live_broker_call_path",
            "paper_or_sim_path_reaches_broker_order_action",
            order_call_line,
        )
    ]


def _imported_modules(tree: ast.AST) -> tuple[tuple[str, int | None], ...]:
    modules: set[tuple[str, int | None]] = set()
    for node in ast.walk(tree):
        line = getattr(node, "lineno", None)
        if isinstance(node, ast.Import):
            modules.update((alias.name, line) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add((node.module, line))
    return tuple(sorted(modules, key=lambda item: (item[1] or 0, item[0])))


def _called_names(tree: ast.AST) -> tuple[tuple[str, int | None], ...]:
    calls = {
        (_call_name(node), getattr(node, "lineno", None))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _call_name(node)
    }
    return tuple(sorted(calls, key=lambda item: (item[1] or 0, item[0])))


def _assigned_literal_fields(
    tree: ast.AST,
) -> tuple[tuple[str, object, int | None], ...]:
    assignments: list[tuple[str, object, int | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = _literal_value(node.value)
            assignments.extend(
                (_target_name(target), value, getattr(node, "lineno", None))
                for target in node.targets
                if _target_name(target)
            )
        elif isinstance(node, ast.AnnAssign):
            name = _target_name(node.target)
            if name:
                assignments.append(
                    (name, _literal_value(node.value), getattr(node, "lineno", None))
                )
        elif isinstance(node, ast.Dict):
            for key, value_node in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    assignments.append(
                        (
                            key.value,
                            _literal_value(value_node),
                            getattr(key, "lineno", getattr(node, "lineno", None)),
                        )
                    )
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
    return (
        "paper" in lowered
        or "/sim" in lowered
        or "sim_" in lowered
        or "dry_run" in lowered
    )


def _looks_read_only_path(path: str) -> bool:
    lowered = path.lower()
    markers = [
        "dashboard",
        "report",
        "replay",
        "repo_forensics",
        "audit",
        "evidence",
        "read_only",
        "snapshot",
    ]
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


def _literal_value(node: ast.expr | None) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    return None


def _dedupe_findings(findings: list[SafetyFinding]) -> list[SafetyFinding]:
    unique: dict[tuple[str, str, str, str, int | None], SafetyFinding] = {}
    for finding in findings:
        key = (
            finding.path,
            finding.severity,
            finding.boundary,
            finding.evidence,
            finding.line,
        )
        unique[key] = finding
    return sorted(
        unique.values(),
        key=lambda item: (
            item.path,
            item.line or 0,
            item.severity,
            item.boundary,
            item.evidence,
        ),
    )


def _should_skip(path: Path, repo_root: Path, config: ForensicsConfig) -> bool:
    rel = path.relative_to(repo_root)
    if any(part in config.excluded_directories for part in rel.parts):
        return True
    if any(part in {".git", ".venv", "venv", "__pycache__"} for part in rel.parts):
        return True
    return False
