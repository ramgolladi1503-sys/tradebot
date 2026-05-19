from __future__ import annotations

from pathlib import Path

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.repo_cartographer import build_repo_map
from tools.repo_forensics.report_writer import render_repo_map_report


def test_repo_cartographer_scans_current_checkout_without_runtime_imports():
    repo_root = Path(__file__).resolve().parents[1]
    config = load_config(repo_root / ".gsd-forensics.yaml")

    repo_map = build_repo_map(repo_root, config)

    assert repo_map.inventory.total_files > 0
    assert repo_map.missing_required_entrypoints == []
    assert repo_map.inventory.python_files
    assert repo_map.inventory.test_files
    assert repo_map.inventory.doc_files


def test_repo_map_report_contains_scope_guard_and_configured_sections():
    repo_root = Path(__file__).resolve().parents[1]
    config = load_config(repo_root / ".gsd-forensics.yaml")

    report = render_repo_map_report(build_repo_map(repo_root, config))

    assert "# Repo Forensics" in report
    assert "Scope Guard" in report
    assert "Required Entrypoints" in report
    assert "Critical Modules" in report
    assert "Verdict" in report
