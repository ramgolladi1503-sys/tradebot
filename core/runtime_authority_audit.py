from __future__ import annotations

import ast
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ModuleAuthority:
    path: str
    line_count: int
    class_names: tuple[str, ...]
    function_names: tuple[str, ...]
    imported_symbols: tuple[str, ...]
    locally_redefined_imports: tuple[str, ...]
    broker_action_references: tuple[str, ...]
    file_write_references: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


_BROKER_ACTION_MARKERS = (
    "place_order",
    "modify_order",
    "cancel_order",
    "exit_order",
    "execution_router",
    "route_execution",
)
_FILE_WRITE_MARKERS = (
    "write_text",
    "write_json_atomic",
    "append_event",
    "append_trade_lifecycle_event",
    "open",
)


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def inspect_module(path: str | Path) -> ModuleAuthority:
    source_path = Path(path)
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))

    imported: set[str] = set()
    classes: list[str] = []
    functions: list[str] = []
    calls: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
        elif isinstance(node, ast.Call):
            call_name = _dotted_name(node.func)
            if call_name:
                calls.append(call_name)

    local_symbols = set(classes) | set(functions)
    redefined = tuple(sorted(imported & local_symbols))
    broker_refs = tuple(
        sorted({call for call in calls if any(marker in call.lower() for marker in _BROKER_ACTION_MARKERS)})
    )
    write_refs = tuple(
        sorted({call for call in calls if any(marker in call.lower() for marker in _FILE_WRITE_MARKERS)})
    )

    return ModuleAuthority(
        path=str(source_path),
        line_count=len(source.splitlines()),
        class_names=tuple(classes),
        function_names=tuple(functions),
        imported_symbols=tuple(sorted(imported)),
        locally_redefined_imports=redefined,
        broker_action_references=broker_refs,
        file_write_references=write_refs,
    )


def audit_runtime_authority(repo_root: str | Path, paths: Iterable[str]) -> dict:
    root = Path(repo_root)
    modules = tuple(inspect_module(root / path) for path in paths)
    return {
        "schema_version": 1,
        "read_only": True,
        "modules": [module.to_dict() for module in modules],
        "summary": {
            "module_count": len(modules),
            "total_lines": sum(module.line_count for module in modules),
            "locally_redefined_import_count": sum(len(module.locally_redefined_imports) for module in modules),
            "broker_action_reference_count": sum(len(module.broker_action_references) for module in modules),
            "file_write_reference_count": sum(len(module.file_write_references) for module in modules),
        },
    }


__all__ = ["ModuleAuthority", "audit_runtime_authority", "inspect_module"]
