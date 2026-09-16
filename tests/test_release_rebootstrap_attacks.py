"""Static/adversarial contract checks for the exceptional recovery path.

These supplement behavioral tests; they intentionally ensure the recovery API
cannot regress into the caller-authored PASS mechanism removed by PR #907.
"""
from pathlib import Path

from core.release_rebootstrap import REBOOTSTRAP_GATES


def test_rebootstrap_requires_full_18_gate_set():
    assert len(REBOOTSTRAP_GATES) == 18
    assert len(REBOOTSTRAP_GATES) == len(set(REBOOTSTRAP_GATES))


def test_rebootstrap_source_has_no_callback_or_pass_boolean_authority():
    source = Path("core/release_rebootstrap.py").read_text()
    assert "gate_runner" not in source
    assert "lambda" not in source
    assert "pass: True" not in source
    assert "rebootstrap_requires_quarantined_head" in source
    assert "rebootstrap_requires_full_gate_set" in source
    assert "rebootstrap_dependency_graph_incomplete" in source


def test_rebootstrap_forces_no_trusted_fallback():
    source = Path("core/release_rebootstrap.py").read_text()
    store = Path("core/certified_release_store.py").read_text()
    assert '"fallback_sha": None' in source
    assert '"rollback_status": "NO_TRUSTED_FALLBACK"' in source
    assert '"fallback_live_sha": None' in store
    assert "rebootstrap_fallback_must_fail_closed" in store


def test_rebootstrap_attestation_binds_predecessor_and_dependency_graph():
    source = Path("core/release_rebootstrap.py").read_text()
    for required in ("quarantined_predecessor_sha", "quarantined_predecessor_event", "dependency_graph_sha256", "certification_sha256", "evidence_hashes", "rollback_status"):
        assert required in source


def test_normal_verifier_dependency_graph_binding_matches_promoter():
    verifier = Path("scripts/verify_release_manager.py").read_text()
    assert '"dependency_graph_sha256": result["dependency_graph_sha256"]' in verifier
