from __future__ import annotations

import subprocess
from pathlib import Path

from research.option_e2e_recertification_v4.signal_ledger_provenance_v1.oracle import _oracle_search
from research.option_e2e_recertification_v4.signal_ledger_provenance_v1.provenance_search import (
    search_preexisting_non_outcome_provenance,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_search_excludes_self_generated_audit_paths(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    ledger_hash = "a" * 64
    _write(
        root,
        "research/option_e2e_recertification_v4/signal_ledger_provenance_v1/self.json",
        ledger_hash,
    )
    _write(root, "docs/agent_reviews/SIGNAL_LEDGER_PROVENANCE_V1.md", ledger_hash)
    _write(root, "evidence/preexisting_provenance.json", ledger_hash)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")

    primary = search_preexisting_non_outcome_provenance(root, ledger_sha256=ledger_hash, row_count=24)
    repository_record = primary[0]
    matched_paths = {item["semantic_path"] for item in repository_record["matching_records"]}
    assert matched_paths == {"evidence/preexisting_provenance.json"}
    assert repository_record["scope_excluded_candidate_count"] == 2
    assert all("signal_ledger_provenance_v1" not in path for path in repository_record["inspected_candidate_paths"])

    oracle = _oracle_search(root, (), ledger_hash, 24)
    assert oracle[0]["matching_record_count"] == 1
    assert oracle[0]["scope_excluded_candidate_count"] == 2
    assert oracle[0]["candidate_count"] == repository_record["candidate_count"]
    assert oracle[0]["inspected_candidate_count"] == repository_record["inspected_candidate_count"]
