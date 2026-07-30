from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.repo_forensics.config_loader import ForensicsConfig


_SHELL_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_.]*)\s*(?:$|#)")
_SHELL_FROM_RE = re.compile(
    r"^\s*from\s+([A-Za-z_][A-Za-z0-9_.]*)\s+import\s+([A-Za-z_][A-Za-z0-9_]*)"
)


@dataclass(frozen=True)
class FileReferenceGraph:
    files: set[str] = field(default_factory=set)
    imports_by_file: dict[str, set[str]] = field(default_factory=dict)
    references_by_file: dict[str, set[str]] = field(default_factory=dict)

    def files_referencing_module(self, module_path: str) -> set[str]:
        module_name = _module_name_from_path(module_path)
        module_stem = Path(module_path).stem
        callers: set[str] = set()
        for source_file, imports in self.imports_by_file.items():
            if module_name in imports or any(
                item.startswith(module_name + ".") for item in imports
            ):
                callers.add(source_file)
                continue
            refs = self.references_by_file.get(source_file, set())
            if module_name in refs or module_path in refs or module_stem in refs:
                callers.add(source_file)
        return callers

    def production_callers(self, module_path: str) -> set[str]:
        return {
            caller
            for caller in self.files_referencing_module(module_path)
            if not _is_test_path(caller)
        }

    def test_callers(self, module_path: str) -> set[str]:
        return {
            caller
            for caller in self.files_referencing_module(module_path)
            if _is_test_path(caller)
        }


def build_reference_graph(
    repo_root: str | Path, config: ForensicsConfig
) -> FileReferenceGraph:
    root = Path(repo_root).resolve()
    files: set[str] = set()
    imports_by_file: dict[str, set[str]] = {}
    references_by_file: dict[str, set[str]] = {}

    for path in root.rglob("*.py"):
        if _should_skip(path, root, config):
            continue
        rel = path.relative_to(root).as_posix()
        files.add(rel)
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            imports_by_file[rel] = set()
            references_by_file[rel] = set()
            continue
        imports, references = _parse_python_source(source)
        imports_by_file[rel] = imports
        references_by_file[rel] = references

    for pattern in ("*.sh", "*.bash"):
        for path in root.rglob(pattern):
            if _should_skip(path, root, config):
                continue
            rel = path.relative_to(root).as_posix()
            files.add(rel)
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                imports_by_file[rel] = set()
                references_by_file[rel] = set()
                continue
            imports, references = _parse_shell_embedded_python(source)
            imports_by_file[rel] = imports
            references_by_file[rel] = references

    return FileReferenceGraph(
        files=files,
        imports_by_file=imports_by_file,
        references_by_file=references_by_file,
    )


def _parse_python_source(source: str) -> tuple[set[str], set[str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set(), set()
    imports: set[str] = set()
    references: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
                imports.update(f"{node.module}.{alias.name}" for alias in node.names)
                references.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Name):
            references.add(node.id)
        elif isinstance(node, ast.Attribute):
            references.add(node.attr)
    return imports, references


def _parse_shell_embedded_python(source: str) -> tuple[set[str], set[str]]:
    """Extract Python imports from shell heredocs without executing the script.

    The parser intentionally accepts only lines that begin with valid Python
    ``import`` or ``from ... import`` syntax. Comments, echo statements, and
    quoted documentation are ignored. This is sufficient to prove startup
    wiring such as ``run_live.sh`` importing ``core.startup_recovery``.
    """

    imports: set[str] = set()
    references: set[str] = set()
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        from_match = _SHELL_FROM_RE.match(line)
        if from_match:
            module, symbol = from_match.groups()
            imports.add(module)
            imports.add(f"{module}.{symbol}")
            references.add(symbol)
            continue
        import_match = _SHELL_IMPORT_RE.match(line)
        if import_match:
            imports.add(import_match.group(1))
    return imports, references


def _module_name_from_path(module_path: str) -> str:
    normalized = module_path.removesuffix(".py").replace("/", ".")
    if normalized.endswith(".__init__"):
        normalized = normalized.removesuffix(".__init__")
    return normalized


def _is_test_path(path: str) -> bool:
    parts = path.split("/")
    return bool(parts and parts[0] in {"tests", "testing"}) or Path(path).name.startswith(
        "test_"
    )


def _should_skip(path: Path, repo_root: Path, config: ForensicsConfig) -> bool:
    rel = path.relative_to(repo_root)
    excluded_dirs = config.excluded_directories
    if any(part in excluded_dirs for part in rel.parts):
        return True
    if any(part in {".git", ".venv", "venv", "__pycache__"} for part in rel.parts):
        return True
    return False
