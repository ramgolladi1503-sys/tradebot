from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from tools.repo_forensics.config_loader import ForensicsConfig


PYTHON_SUFFIX = ".py"
SHELL_SUFFIXES = {".sh", ".bash", ".zsh"}
DOC_SUFFIXES = {".md", ".rst", ".txt"}
DASHBOARD_DIRS = {"dashboard"}
TEST_DIRS = {"tests", "testing"}


@dataclass(frozen=True)
class FileInventory:
    total_files: int = 0
    python_files: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    shell_scripts: list[str] = field(default_factory=list)
    dashboard_files: list[str] = field(default_factory=list)
    doc_files: list[str] = field(default_factory=list)
    runtime_evidence_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PathStatus:
    path: str
    status: str
    category: str
    evidence: str


@dataclass(frozen=True)
class RepoMap:
    repo_root: Path
    inventory: FileInventory
    required_entrypoints: list[PathStatus]
    optional_entrypoints: list[PathStatus]
    critical_modules: dict[str, list[PathStatus]]
    top_manual_inspection_files: list[str]

    @property
    def missing_required_entrypoints(self) -> list[PathStatus]:
        return [item for item in self.required_entrypoints if item.status != "PASS"]

    @property
    def missing_critical_modules(self) -> list[PathStatus]:
        missing: list[PathStatus] = []
        for items in self.critical_modules.values():
            missing.extend([item for item in items if item.status != "PASS"])
        return missing


def build_repo_map(repo_root: str | Path, config: ForensicsConfig) -> RepoMap:
    root = Path(repo_root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"repo_root_not_found path={root}")
    files = sorted(_iter_repo_files(root, config), key=lambda p: p.as_posix())
    rel_files = [path.relative_to(root).as_posix() for path in files]
    rel_file_set = set(rel_files)

    inventory = FileInventory(
        total_files=len(rel_files),
        python_files=[p for p in rel_files if p.endswith(PYTHON_SUFFIX)],
        test_files=[p for p in rel_files if _is_test_file(p)],
        shell_scripts=[p for p in rel_files if Path(p).suffix in SHELL_SUFFIXES],
        dashboard_files=[p for p in rel_files if _first_part(p) in DASHBOARD_DIRS],
        doc_files=[p for p in rel_files if Path(p).suffix in DOC_SUFFIXES],
        runtime_evidence_paths=_configured_runtime_evidence_paths(root, config),
    )

    required_entrypoints = [
        _path_status(path, rel_file_set, category="required_entrypoint")
        for path in config.required_entrypoints
    ]
    optional_entrypoints = [
        _path_status(path, rel_file_set, category="optional_entrypoint")
        for path in config.optional_entrypoints
    ]
    critical_modules = {
        group: [_path_status(path, rel_file_set, category=f"critical_module:{group}") for path in paths]
        for group, paths in config.critical_modules.items()
    }

    top_manual = _top_manual_inspection_files(required_entrypoints, optional_entrypoints, critical_modules)
    return RepoMap(
        repo_root=root,
        inventory=inventory,
        required_entrypoints=required_entrypoints,
        optional_entrypoints=optional_entrypoints,
        critical_modules=critical_modules,
        top_manual_inspection_files=top_manual,
    )


def _iter_repo_files(repo_root: Path, config: ForensicsConfig) -> Iterable[Path]:
    excluded_dirs = set(config.excluded_directories)
    excluded_patterns = set(config.excluded_file_patterns)
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        if _is_excluded(rel, excluded_dirs, excluded_patterns):
            continue
        yield path


def _is_excluded(rel: Path, excluded_dirs: set[str], excluded_patterns: set[str]) -> bool:
    parts = set(rel.parts)
    for directory in excluded_dirs:
        if directory in parts or rel.as_posix().startswith(directory.rstrip("/") + "/"):
            return True
    name = rel.name
    for pattern in excluded_patterns:
        if pattern.startswith("*") and name.endswith(pattern[1:]):
            return True
        if pattern == name:
            return True
    return False


def _is_test_file(path: str) -> bool:
    parts = path.split("/")
    return bool(parts and parts[0] in TEST_DIRS) or Path(path).name.startswith("test_")


def _first_part(path: str) -> str:
    return path.split("/", 1)[0] if path else ""


def _configured_runtime_evidence_paths(repo_root: Path, config: ForensicsConfig) -> list[str]:
    return [path for path in config.runtime_evidence_paths if (repo_root / path).exists()]


def _path_status(path: str, rel_file_set: set[str], *, category: str) -> PathStatus:
    normalized = str(path).strip().lstrip("./")
    exists = normalized in rel_file_set
    return PathStatus(
        path=normalized,
        status="PASS" if exists else "FAIL",
        category=category,
        evidence=("path_exists" if exists else "path_missing"),
    )


def _top_manual_inspection_files(
    required: list[PathStatus],
    optional: list[PathStatus],
    critical: dict[str, list[PathStatus]],
) -> list[str]:
    ordered: list[str] = []
    for item in required:
        if item.path not in ordered:
            ordered.append(item.path)
    for group in ("orchestration", "candidates_and_ranking", "risk_and_safety", "execution_boundary"):
        for item in critical.get(group, []):
            if item.path not in ordered:
                ordered.append(item.path)
    for item in optional:
        if item.status == "PASS" and item.path not in ordered:
            ordered.append(item.path)
    return ordered[:10]
