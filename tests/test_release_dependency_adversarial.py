import json
import pytest
from pathlib import Path

from core.release_change_impact import DependencyEvidence
from core.release_dependency_evidence import (
    dependency_graph_digest,
    scan_repository_dependencies,
    serialize_dependency_evidence,
    GOVERNED_CRITICAL_ROOTS,
    GOVERNED_BOUNDED_ROOTS,
)
from scripts.verify_release_manager import _commit_exists, verify_rebootstrap
from core.certified_release_store import ReleaseStore, ReleaseStoreError


@pytest.fixture
def repo_with_evidence(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("import core.orchestrator\n")
    core_dir = repo / "core"
    core_dir.mkdir()
    (core_dir / "orchestrator.py").write_text("pass\n")

    ev, meta = scan_repository_dependencies(repo, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
    return repo, ev, meta


def test_a01_force_complete_true_rejected_if_unresolved_present(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("def broken(\n")
    ev, meta = scan_repository_dependencies(repo, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
    assert ev.complete is False
    assert len(ev.unresolved) > 0


def test_a02_drop_unresolved_tamper_detected(repo_with_evidence):
    repo, ev, _ = repo_with_evidence
    serialized = serialize_dependency_evidence(ev)
    d1 = dependency_graph_digest(ev)

    # Tamper unresolved list
    mutated_ev = DependencyEvidence(
        edges=ev.edges,
        critical_roots=ev.critical_roots,
        bounded_roots=ev.bounded_roots,
        complete=ev.complete,
        unresolved=frozenset({"fake_unresolved"}),
    )
    d2 = dependency_graph_digest(mutated_ev)
    assert d1 != d2


def test_a03_drop_edge_tamper_detected(repo_with_evidence):
    repo, ev, _ = repo_with_evidence
    d1 = dependency_graph_digest(ev)

    mutated_ev = DependencyEvidence(
        edges={"main.py": frozenset()},
        critical_roots=ev.critical_roots,
        bounded_roots=ev.bounded_roots,
        complete=ev.complete,
        unresolved=ev.unresolved,
    )
    d2 = dependency_graph_digest(mutated_ev)
    assert d1 != d2


def test_a05_remove_critical_root_tamper_detected(repo_with_evidence):
    repo, ev, _ = repo_with_evidence
    d1 = dependency_graph_digest(ev)

    mutated_ev = DependencyEvidence(
        edges=ev.edges,
        critical_roots=frozenset(),
        bounded_roots=ev.bounded_roots,
        complete=ev.complete,
        unresolved=ev.unresolved,
    )
    d2 = dependency_graph_digest(mutated_ev)
    assert d1 != d2


def test_a10_parse_failure_not_swallowed(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("import broken\n")
    (repo / "broken.py").write_text("class 123:\n")

    ev, meta = scan_repository_dependencies(repo, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
    assert ev.complete is False
    assert any("syntax_error:broken.py" in u for u in ev.unresolved)


def test_a11_dynamic_import_detected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("x = __import__('os')\n")

    ev, meta = scan_repository_dependencies(repo, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
    assert ev.complete is False
    assert any("dynamic___import__" in u for u in ev.unresolved)


def test_a12_importlib_dynamic_detected(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("import importlib\nimportlib.import_module('sys')\n")

    ev, meta = scan_repository_dependencies(repo, candidate_sha="", critical_roots=("main.py",), bounded_roots=())
    assert ev.complete is False
    assert any("dynamic_import_module" in u for u in ev.unresolved)


def test_a17_caller_root_override_fails_if_governed_missing(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("pass\n")

    ev, meta = scan_repository_dependencies(repo, candidate_sha="", critical_roots=GOVERNED_CRITICAL_ROOTS, bounded_roots=GOVERNED_BOUNDED_ROOTS)
    assert ev.complete is False
    assert any("missing_governed_critical_root" in u for u in ev.unresolved)
