import json
import tempfile
from pathlib import Path
import pytest

from core.release_change_impact import DependencyEvidence
from core.release_dependency_evidence import (
    GOVERNED_BOUNDED_ROOTS,
    GOVERNED_CRITICAL_ROOTS,
    dependency_graph_digest,
    scan_repository_dependencies,
    serialize_dependency_evidence,
)


def test_governed_roots_immutable_tuple():
    assert "main.py" in GOVERNED_CRITICAL_ROOTS
    assert "core/orchestrator.py" in GOVERNED_CRITICAL_ROOTS
    assert "core/governed_morning_orchestrator.py" in GOVERNED_CRITICAL_ROOTS
    assert "core/ranking_orchestrator.py" in GOVERNED_BOUNDED_ROOTS


def test_deterministic_static_import_resolution():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "main.py").write_text("import core.orchestrator\nfrom core.util import helper\n")
        core_dir = root / "core"
        core_dir.mkdir()
        (core_dir / "orchestrator.py").write_text("from .util import helper\n")
        (core_dir / "util.py").write_text("def helper(): pass\n")

        evidence, meta = scan_repository_dependencies(root, candidate_sha="", critical_roots=("main.py", "core/orchestrator.py"), bounded_roots=())
        assert evidence.complete is True
        assert len(evidence.unresolved) == 0
        assert "core/orchestrator.py" in evidence.edges["main.py"]
        assert "core/util.py" in evidence.edges["main.py"]
        assert "core/util.py" in evidence.edges["core/orchestrator.py"]


def test_relative_import_resolution():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        pkg = root / "pkg" / "sub"
        pkg.mkdir(parents=True)
        (root / "main.py").write_text("import pkg.sub.mod_b\n")
        (pkg / "mod_a.py").write_text("X = 1\n")
        (pkg / "mod_b.py").write_text("from .mod_a import X\n")

        evidence, _ = scan_repository_dependencies(root, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
        assert evidence.complete is True
        assert "pkg/sub/mod_a.py" in evidence.edges["pkg/sub/mod_b.py"]


def test_syntax_error_fails_closed_incomplete():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "main.py").write_text("def broken(\n")

        evidence, meta = scan_repository_dependencies(root, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
        assert evidence.complete is False
        assert any("syntax_error" in u for u in evidence.unresolved)


def test_dynamic_import_fails_closed_incomplete():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "main.py").write_text("import importlib\nmod = importlib.import_module('dynamic_mod')\n")

        evidence, meta = scan_repository_dependencies(root, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
        assert evidence.complete is False
        assert any("dynamic_import_module" in u for u in evidence.unresolved)


def test_dynamic_dunder_import_fails_closed_incomplete():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "main.py").write_text("mod = __import__('dynamic_mod')\n")

        evidence, meta = scan_repository_dependencies(root, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
        assert evidence.complete is False
        assert any("dynamic___import__" in u for u in evidence.unresolved)


def test_missing_governed_critical_root_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "other.py").write_text("pass\n")

        evidence, meta = scan_repository_dependencies(root, candidate_sha="", critical_roots=("missing_critical.py",), bounded_roots=())
        assert evidence.complete is False
        assert "missing_governed_critical_root:missing_critical.py" in evidence.unresolved


def test_repeated_generation_produces_identical_digest():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "main.py").write_text("import a\nimport b\n")
        (root / "a.py").write_text("import b\n")
        (root / "b.py").write_text("X = 1\n")

        ev1, _ = scan_repository_dependencies(root, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
        d1 = dependency_graph_digest(ev1)

        ev2, _ = scan_repository_dependencies(root, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
        d2 = dependency_graph_digest(ev2)

        assert d1 == d2
        assert len(d1) == 64
