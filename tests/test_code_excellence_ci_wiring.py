from __future__ import annotations

from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/code-excellence-gates.yml")


def test_code_excellence_workflow_exists():
    assert WORKFLOW_PATH.exists()


def test_code_excellence_workflow_runs_unified_gate_on_prs():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "name: Code Excellence Gates" in text
    assert "pull_request:" in text
    assert "branches:" in text
    assert "- main" in text
    assert "workflow_dispatch:" in text
    assert "code-excellence-gates:" in text
    assert "scripts/run_unified_ce_gates.py" in text


def test_code_excellence_workflow_uses_changed_paths_file():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "git diff --name-only origin/main...HEAD" in text
    assert "docs/code_excellence/reports/changed_paths.txt" in text
    assert "--changed-paths-file docs/code_excellence/reports/changed_paths.txt" in text


def test_code_excellence_workflow_uploads_reports_even_on_failure():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "if: always()" in text
    assert "code-excellence-gate-reports" in text
    assert "docs/code_excellence/reports/unified_ce_gate_latest.md" in text


def test_code_excellence_workflow_stays_lightweight():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "pip install -r requirements.txt" not in text
    assert "pytest -q" not in text
    assert "core.health_gate" not in text
