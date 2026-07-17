from __future__ import annotations

from pathlib import Path

import pytest

from core.ai_certification.bundle import BundleError, resolve_under_root
from core.ai_certification.mcp_server import resolve_allowed_bundle


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
