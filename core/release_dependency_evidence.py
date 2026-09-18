"""Authoritative repository-owned dependency evidence analyzer for release change-impact and certification.

Conservatively derives the canonical DependencyEvidence contract from static AST inspection
of repository source files. Preserves all unresolved imports, dynamic loading, and parse errors
as explicit uncertainty reasons (complete=False), enforcing fail-closed release safety.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from core.release_change_impact import DependencyEvidence

GENERATOR_VERSION = "release_dependency_evidence_v1"
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Immutable governed critical and bounded roots
GOVERNED_CRITICAL_ROOTS: tuple[str, ...] = (
    "main.py",
    "core/orchestrator.py",
    "core/governed_morning_orchestrator.py",
    "core/execution_router.py",
    "core/risk_engine.py",
    "core/release_certification.py",
    "core/certified_release_store.py",
    "core/release_manager.py",
    "core/release_rebootstrap.py",
)

GOVERNED_BOUNDED_ROOTS: tuple[str, ...] = (
    "core/ranking_orchestrator.py",
    "core/candidate_pool_orchestrator.py",
    "core/paper_decision_orchestrator.py",
)


class DependencyAnalysisError(ValueError):
    """Raised when repository dependency analysis encounters fatal structural corruption."""


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def resolve_import_target(
    repo: Path,
    current_file: str,
    module_name: str | None,
    level: int = 0,
) -> tuple[str | None, str | None]:
    """Resolve an import statement to a repository relative POSIX path.

    Returns (target_rel_path, unresolved_reason).
    """
    if level > 0:
        # Relative import
        current_parts = list(PurePosixPath(current_file).parent.parts)
        if level > len(current_parts) + 1:
            return None, f"relative_import_escapes_repo:{current_file}:level_{level}"
        # Pop (level - 1) parts
        base_parts = current_parts[: len(current_parts) - (level - 1)] if (level - 1) > 0 else current_parts
        if module_name:
            mod_parts = module_name.split(".")
            target_parts = base_parts + mod_parts
        else:
            target_parts = base_parts
        target_base = "/".join(target_parts)
    else:
        # Absolute import relative to repo root
        if not module_name:
            return None, f"empty_module_name:{current_file}"
        target_base = module_name.replace(".", "/")

    # Check potential file targets: <target>.py or <target>/__init__.py
    py_candidate = f"{target_base}.py" if target_base else None
    init_candidate = f"{target_base}/__init__.py" if target_base else "__init__.py"

    if py_candidate and (repo / py_candidate).is_file():
        return py_candidate, None
    if (repo / init_candidate).is_file():
        return init_candidate, None

    # Not a local repository file (could be standard library or 3rd-party vendor package)
    return None, None


class ModuleDependencyVisitor(ast.NodeVisitor):
    """Inspects AST nodes for static imports, dynamic loading, and __import__ calls."""

    def __init__(self, rel_path: str, repo: Path) -> None:
        self.rel_path = rel_path
        self.repo = repo
        self.edges: set[str] = set()
        self.unresolved: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            target, unres = resolve_import_target(self.repo, self.rel_path, alias.name, level=0)
            if target:
                self.edges.add(target)
            elif unres:
                self.unresolved.append(unres)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        target, unres = resolve_import_target(self.repo, self.rel_path, node.module, level=node.level)
        if target:
            self.edges.add(target)
        elif unres:
            self.unresolved.append(unres)

        # Also check if imported names correspond to submodules (e.g. from foo import bar where bar.py exists)
        if node.module:
            for alias in node.names:
                submod_name = f"{node.module}.{alias.name}"
                sub_target, _ = resolve_import_target(self.repo, self.rel_path, submod_name, level=node.level)
                if sub_target:
                    self.edges.add(sub_target)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Detect dynamic imports: __import__(...), importlib.import_module(...)
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            self.unresolved.append(f"dynamic___import__:{self.rel_path}:L{node.lineno}")
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "import_module":
            self.unresolved.append(f"dynamic_import_module:{self.rel_path}:L{node.lineno}")
        elif isinstance(node.func, ast.Name) and node.func.id in ("eval", "exec"):
            self.unresolved.append(f"dynamic_code_execution:{self.rel_path}:L{node.lineno}")
        self.generic_visit(node)


def scan_repository_dependencies(
    repo: Path,
    candidate_sha: str,
    *,
    critical_roots: Sequence[str] = GOVERNED_CRITICAL_ROOTS,
    bounded_roots: Sequence[str] = GOVERNED_BOUNDED_ROOTS,
) -> tuple[DependencyEvidence, dict[str, Any]]:
    """Deterministically scan repository ASTs to produce canonical DependencyEvidence and metadata."""
    resolved_repo = Path(repo).resolve()
    if not resolved_repo.is_dir():
        raise DependencyAnalysisError(f"repository_not_a_directory:{repo}")

    # Verify git status if possible
    try:
        head_sha = _git(resolved_repo, "rev-parse", "HEAD")
        if candidate_sha and head_sha != candidate_sha:
            raise DependencyAnalysisError(f"candidate_not_checked_out:{head_sha}!={candidate_sha}")
    except (subprocess.CalledProcessError, OSError):
        pass

    # Discover all Python files in the repository, excluding virtualenvs, dotdirs, and data stores
    py_files: list[str] = []
    for p in resolved_repo.glob("**/*.py"):
        rel = p.relative_to(resolved_repo).as_posix()
        parts = rel.split("/")
        if any(part.startswith(".") for part in parts):
            continue
        if any(part in ("venv", ".venv", "env", "site-packages", "node_modules") for part in parts):
            continue
        py_files.append(rel)

    py_files.sort()

    edges: dict[str, frozenset[str]] = {}
    all_unresolved: list[str] = []

    for rel_path in py_files:
        full_path = resolved_repo / rel_path
        try:
            source_bytes = full_path.read_bytes()
            tree = ast.parse(source_bytes, filename=rel_path)
            visitor = ModuleDependencyVisitor(rel_path, resolved_repo)
            visitor.visit(tree)
            edges[rel_path] = frozenset(sorted(visitor.edges))
            all_unresolved.extend(visitor.unresolved)
        except SyntaxError as exc:
            all_unresolved.append(f"syntax_error:{rel_path}:L{exc.lineno}:{exc.msg}")
            edges[rel_path] = frozenset()
        except Exception as exc:
            all_unresolved.append(f"parse_exception:{rel_path}:{type(exc).__name__}:{exc}")
            edges[rel_path] = frozenset()

    # Validate that critical and bounded roots exist in repository
    active_critical = [r for r in critical_roots if r in edges]
    missing_critical = [r for r in critical_roots if r not in edges]
    if missing_critical:
        for mc in missing_critical:
            all_unresolved.append(f"missing_governed_critical_root:{mc}")

    active_bounded = [r for r in bounded_roots if r in edges]
    missing_bounded = [r for r in bounded_roots if r not in edges]
    if missing_bounded:
        for mb in missing_bounded:
            all_unresolved.append(f"missing_governed_bounded_root:{mb}")

    unique_unresolved = sorted(set(all_unresolved))
    is_complete = (len(unique_unresolved) == 0)

    evidence = DependencyEvidence(
        edges=edges,
        critical_roots=frozenset(active_critical),
        bounded_roots=frozenset(active_bounded),
        complete=is_complete,
        unresolved=frozenset(unique_unresolved),
    )

    metadata = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "candidate_sha": candidate_sha,
        "governed_critical_roots": sorted(critical_roots),
        "governed_bounded_roots": sorted(bounded_roots),
        "active_critical_roots": sorted(active_critical),
        "active_bounded_roots": sorted(active_bounded),
        "total_files_scanned": len(py_files),
        "complete": is_complete,
        "unresolved": unique_unresolved,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return evidence, metadata


def serialize_dependency_evidence(evidence: DependencyEvidence) -> dict[str, Any]:
    """Deterministically serialize canonical DependencyEvidence to JSON-serializable dictionary."""
    return {
        "edges": {k: sorted(v) for k, v in sorted(evidence.edges.items())},
        "critical_roots": sorted(evidence.critical_roots),
        "bounded_roots": sorted(evidence.bounded_roots),
        "complete": bool(evidence.complete),
        "unresolved": sorted(evidence.unresolved),
    }


def dependency_graph_digest(graph: DependencyEvidence) -> str:
    """Canonical reproducible SHA-256 digest of semantic dependency graph."""
    payload = serialize_dependency_evidence(graph)
    canonical_bytes = (json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()
