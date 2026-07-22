from __future__ import annotations

from pathlib import Path

import pytest

from tools.tradebot_mcp.core import SafetyError, Settings
from tools.tradebot_mcp.safe_git import SafeGitAuditService


def test_git_ref_rejects_option_injection(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / ".git").mkdir()
    settings = Settings(root=root, evidence_roots=(), data_roots=())
    service = SafeGitAuditService(settings)

    with pytest.raises(SafetyError):
        service.get_branch_head("--help")
