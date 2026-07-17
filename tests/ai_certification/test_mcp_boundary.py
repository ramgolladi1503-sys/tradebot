from __future__ import annotations

from pathlib import Path

import pytest

from core.ai_certification.bundle import BundleError, resolve_under_root
from core.ai_certification.mcp_server import (
    evaluate_gate,
    resolve_allowed_bundle,
    retrieve_policy_context,
)


def test_mcp_bundle_id_cannot_escape_allowlisted_root(tmp_path: Path):
    with pytest.raises(BundleError):
        resolve_allowed_bundle("../secrets", tmp_path)
    with pytest.raises(BundleError):
        resolve_allowed_bundle("/tmp/secrets", tmp_path)


def test_report_path_cannot_escape_root(tmp_path: Path):
    with pytest.raises(BundleError):
        resolve_under_root(tmp_path, "../../.env")


def test_safe_bundle_id_resolves_under_root(tmp_path: Path):
    resolved = resolve_allowed_bundle("orb-run-001", tmp_path)
    assert resolved == (tmp_path / "orb-run-001").resolve()


def test_unknown_gate_is_rejected_before_bundle_access(tmp_path: Path):
    with pytest.raises(BundleError, match="unknown certification gate"):
        evaluate_gate(
            "does-not-exist",
            "not_a_certification_gate",
            evidence_root=tmp_path,
        )


def test_policy_retrieval_uses_only_curated_repository_sources(tmp_path: Path):
    policy = tmp_path / "docs/ai_certification/certification_policy_v1.md"
    policy.parent.mkdir(parents=True)
    policy.write_text(
        "# Temporal causality\nSame-event entry is non-certifying.",
        encoding="utf-8",
    )
    secret = tmp_path / ".env"
    secret.write_text("BROKER_TOKEN=do-not-index", encoding="utf-8")

    result = retrieve_policy_context(
        "same event temporal causality",
        repository_root=tmp_path,
    )

    assert result["results"]
    assert all(row["citation"].startswith("docs/") for row in result["results"])
    assert "BROKER_TOKEN" not in str(result)
