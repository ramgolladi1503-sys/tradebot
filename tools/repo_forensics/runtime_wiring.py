from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.repo_forensics.config_loader import ForensicsConfig


@dataclass(frozen=True)
class FlowStepStatus:
    flow_name: str
    step: str
    status: str
    evidence: str


@dataclass(frozen=True)
class RuntimeFlowReport:
    flow_statuses: dict[str, list[FlowStepStatus]] = field(default_factory=dict)

    @property
    def unknowns(self) -> list[FlowStepStatus]:
        result: list[FlowStepStatus] = []
        for statuses in self.flow_statuses.values():
            result.extend([status for status in statuses if status.status == "UNKNOWN"])
        return result

    @property
    def failures(self) -> list[FlowStepStatus]:
        result: list[FlowStepStatus] = []
        for statuses in self.flow_statuses.values():
            result.extend([status for status in statuses if status.status == "FAIL"])
        return result


@dataclass(frozen=True)
class DottedStepResolution:
    module_name: str | None
    module_path: str | None
    symbol: str | None
    module_exists: bool


def audit_runtime_wiring(repo_root: str | Path, config: ForensicsConfig) -> RuntimeFlowReport:
    root = Path(repo_root).resolve()
    python_imports = _collect_python_imports(root)
    file_text_cache: dict[str, str] = {}
    flow_statuses: dict[str, list[FlowStepStatus]] = {}

    for flow_name, flow in config.runtime_flows.items():
        steps = _flow_steps(flow)
        statuses: list[FlowStepStatus] = []
        for step in steps:
            statuses.append(_status_for_step(root, step, python_imports, file_text_cache, flow_name))
        flow_statuses[flow_name] = statuses
    return RuntimeFlowReport(flow_statuses=flow_statuses)


def _flow_steps(flow: dict[str, Any]) -> list[str]:
    for key in ("expected_chain", "expected_steps"):
        value = flow.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
    starts_at = flow.get("starts_at")
    return [str(starts_at)] if starts_at else []


def _status_for_step(
    repo_root: Path,
    step: str,
    python_imports: dict[str, set[str]],
    file_text_cache: dict[str, str],
    flow_name: str,
) -> FlowStepStatus:
    normalized = step.strip()
    if not normalized:
        return FlowStepStatus(flow_name, step, "UNKNOWN", "empty_step")

    candidate_file = _candidate_file_for_step(normalized)
    if candidate_file and (repo_root / candidate_file).exists():
        return FlowStepStatus(flow_name, step, "PASS", f"file_exists:{candidate_file}")

    resolution = _resolve_dotted_step(repo_root, normalized)
    if resolution.module_name and resolution.module_path:
        if not resolution.module_exists:
            return FlowStepStatus(flow_name, step, "FAIL", f"module_file_missing:{resolution.module_path}")
        if resolution.symbol:
            if _symbol_defined(repo_root, resolution.module_path, resolution.symbol, file_text_cache):
                return FlowStepStatus(flow_name, step, "PASS", f"symbol_defined:{resolution.module_path}:{resolution.symbol}")
            return FlowStepStatus(flow_name, step, "FAIL", f"symbol_missing:{resolution.module_path}:{resolution.symbol}")
        return FlowStepStatus(flow_name, step, "PASS", f"module_file_exists:{resolution.module_path}")

    if _reference_found(normalized, python_imports, file_text_cache, repo_root):
        return FlowStepStatus(flow_name, step, "PASS", "reference_found")
    return FlowStepStatus(flow_name, step, "UNKNOWN", "reference_not_proven")


def _candidate_file_for_step(step: str) -> str | None:
    if step.endswith(".py") or step.endswith(".sh"):
        return step.lstrip("./")
    if "/" in step and "." in Path(step).name:
        return step.lstrip("./")
    return None


def _resolve_dotted_step(repo_root: Path, step: str) -> DottedStepResolution:
    if "." not in step or "/" in step:
        return DottedStepResolution(None, None, None, False)

    parts = step.split(".")
    if not parts or not parts[0] in {"core", "dashboard", "strategies", "scripts", "tools"}:
        return DottedStepResolution(None, None, None, False)

    # Prefer the longest existing module prefix and treat the remaining dotted
    # suffix as a symbol path. This keeps checks static and avoids importing
    # Tradebot runtime modules while preventing false failures such as treating
    # `core.auth.validate_kite_startup_credentials` as
    # `core/auth/validate_kite_startup_credentials.py`.
    for split_index in range(len(parts), 0, -1):
        module = ".".join(parts[:split_index])
        module_path = module.replace(".", "/") + ".py"
        if (repo_root / module_path).exists():
            symbol = ".".join(parts[split_index:]) or None
            return DottedStepResolution(module, module_path, symbol, True)

    module = ".".join(parts)
    return DottedStepResolution(module, module.replace(".", "/") + ".py", None, False)


def _symbol_defined(repo_root: Path, module_path: str, symbol: str, cache: dict[str, str]) -> bool:
    source = _read_text(repo_root / module_path, cache)
    if not source:
        return False
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return symbol in source
    first_symbol = symbol.split(".", 1)[0]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == first_symbol:
            return True
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == first_symbol:
                    return True
    return first_symbol in source


def _reference_found(
    step: str,
    python_imports: dict[str, set[str]],
    cache: dict[str, str],
    repo_root: Path,
) -> bool:
    search_tokens = {step, step.replace(".", "/")}
    for imports in python_imports.values():
        if step in imports:
            return True
    for path in python_imports:
        text = _read_text(repo_root / path, cache)
        if any(token in text for token in search_tokens):
            return True
    return False


def _collect_python_imports(repo_root: Path) -> dict[str, set[str]]:
    imports_by_file: dict[str, set[str]] = {}
    for path in repo_root.rglob("*.py"):
        if _should_skip(path, repo_root):
            continue
        rel = path.relative_to(repo_root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            imports_by_file[rel] = set()
            continue
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    found.add(node.module)
                    found.update(f"{node.module}.{alias.name}" for alias in node.names)
        imports_by_file[rel] = found
    return imports_by_file


def _should_skip(path: Path, repo_root: Path) -> bool:
    rel_parts = path.relative_to(repo_root).parts
    return any(part in {".git", ".venv", "venv", "__pycache__"} for part in rel_parts)


def _read_text(path: Path, cache: dict[str, str]) -> str:
    key = path.as_posix()
    if key not in cache:
        try:
            cache[key] = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            cache[key] = ""
    return cache[key]
