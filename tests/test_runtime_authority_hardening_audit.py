from pathlib import Path

import pytest

from scripts.audit_runtime_authority_hardening_v1 import build_audit_payload


def test_audit_passes_for_additive_hardening_paths():
    if not Path("core/orchestrator.py").exists():
        pytest.skip("repository orchestrator fixture unavailable")
    payload = build_audit_payload(
        ".",
        changed_paths=[
            "core/canonical_execution_decision.py",
            "core/runtime_authority_contract.py",
            "tests/test_runtime_authority_contract.py",
        ],
        base_ref="origin/main",
    )
    assert payload["verdict"] == "PASS_RUNTIME_AUTHORITY_HARDENING_AUDIT"
    assert payload["feed_boundary_frozen"] is True
    assert payload["allowed_for_live_execution"] is False
    assert payload["broker_api_called"] is False


def test_audit_fails_for_feed_change():
    if not Path("core/orchestrator.py").exists():
        pytest.skip("repository orchestrator fixture unavailable")
    payload = build_audit_payload(
        ".",
        changed_paths=["core/market_data.py"],
        base_ref="origin/main",
    )
    assert payload["verdict"] == "FAIL_RUNTIME_AUTHORITY_HARDENING_AUDIT"
    assert payload["feed_boundary_frozen"] is False
    assert any(
        str(error).startswith("feed_boundary_modified:")
        for error in payload["errors"]
    )
