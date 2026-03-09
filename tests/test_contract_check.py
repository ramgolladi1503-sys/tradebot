from __future__ import annotations

from pathlib import Path

import scripts.contract_check as contract_check


def test_contract_check_passes_current_repo(capsys) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    violations = contract_check.run_checks(repo_root)
    assert violations == []

    rc = contract_check.main(["--repo-root", str(repo_root)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "Contract check passed." in captured.out
