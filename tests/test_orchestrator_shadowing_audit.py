from pathlib import Path

import pytest

from core.orchestrator_shadowing_audit import (
    BASELINE_SHADOWED_TRUTH_ALIASES,
    audit_orchestrator_truth_shadowing,
    audit_repository_orchestrator,
)


def test_ast_audit_detects_shadowed_alias():
    source = """
from core.orchestrator_truth import candidate_origin as _candidate_origin

def _candidate_origin(candidate):
    return "local"
"""
    result = audit_orchestrator_truth_shadowing(
        source,
        baseline={"_candidate_origin"},
    )
    assert result.shadowed_aliases == ("_candidate_origin",)
    assert result.new_shadowing == ()
    assert result.controlled is True


def test_new_shadowing_is_reported():
    source = """
from core.orchestrator_truth import candidate_origin as _candidate_origin
from core.orchestrator_truth import safe_float as _safe_float

def _candidate_origin(candidate):
    return "local"

def _safe_float(value):
    return 0
"""
    result = audit_orchestrator_truth_shadowing(
        source,
        baseline={"_candidate_origin"},
    )
    assert result.new_shadowing == ("_safe_float",)
    assert result.controlled is False


def test_repository_shadowing_does_not_expand():
    if not Path("core/orchestrator.py").exists():
        pytest.skip("repository orchestrator fixture unavailable")
    result = audit_repository_orchestrator(".")
    assert set(result.shadowed_aliases).issubset(BASELINE_SHADOWED_TRUTH_ALIASES)
    assert result.new_shadowing == ()
