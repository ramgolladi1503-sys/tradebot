from __future__ import annotations

from pathlib import Path

from scripts.run_agent_elite_report import _required_gate_exit_code


WORKFLOW_PATH = Path(".github/workflows/code-excellence-gates.yml")


def test_code_excellence_workflow_exists():
    assert WORKFLOW_PATH.exists()


def test_code_excellence_workflow_runs_unified_gate_on_prs():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "name: Code Excellence Gates" in text
    assert "pull_request_target:" in text
    assert "branches:" in text
    assert "- main" in text
    assert "workflow_dispatch:" in text
    assert "code-excellence-gates:" in text
    assert "scripts/run_unified_ce_gates.py" in text


def test_code_excellence_workflow_uses_changed_paths_file():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "+refs/heads/main:refs/remotes/origin/main" in text
    assert "+refs/pull/${PR_NUMBER}/head:refs/remotes/origin/pr-${PR_NUMBER}-head" in text
    assert 'git diff --name-only "$MERGE_BASE" "$CANDIDATE_REF"' in text
    assert "docs/code_excellence/reports/changed_paths.txt" in text
    assert "--changed-paths-file docs/code_excellence/reports/changed_paths.txt" in text


def test_code_excellence_workflow_uploads_reports_even_on_failure():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "if: always()" in text
    assert "code-excellence-gate-reports" in text
    assert "docs/code_excellence/reports/unified_ce_gate_latest.md" in text
    assert "docs/code_excellence/reports/unified_agent_elite_latest.md" in text


def test_code_excellence_workflow_requires_agent_elite_report():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "Build required Agent Elite report" in text
    assert "scripts/run_agent_elite_report.py" in text
    assert "--require-ci-pass" in text
    assert "--unknown-explanation docs/code_excellence/reports/unified_ce_gate_latest.md" in text
    assert "run_agent_elite_report.py" in text
    assert "|| true" not in text


def test_required_gate_fails_when_report_is_missing(tmp_path):
    missing = tmp_path / "missing.md"

    assert _required_gate_exit_code("PASS", missing, None) == 1


def test_required_gate_fails_on_new_hard_failure(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("verdict: FAIL\n", encoding="utf-8")

    assert _required_gate_exit_code("FAIL", report, None) == 1


def test_required_gate_requires_explanation_for_unknown(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("verdict: UNKNOWN\n", encoding="utf-8")

    assert _required_gate_exit_code("UNKNOWN", report, None) == 1


def test_required_gate_allows_unknown_with_explanation(tmp_path):
    report = tmp_path / "report.md"
    explanation = tmp_path / "explanation.md"
    report.write_text("verdict: UNKNOWN\n", encoding="utf-8")
    explanation.write_text("upstream gate explains unknowns\n", encoding="utf-8")

    assert _required_gate_exit_code("UNKNOWN", report, str(explanation)) == 0


def test_required_gate_allows_warnings_and_pass(tmp_path):
    report = tmp_path / "report.md"
    report.write_text("verdict: PASS_WITH_WARNINGS\n", encoding="utf-8")

    assert _required_gate_exit_code("PASS_WITH_WARNINGS", report, None) == 0
    assert _required_gate_exit_code("PASS", report, None) == 0


def test_code_excellence_workflow_stays_lightweight():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "pip install -r requirements.txt" not in text
    assert "pytest -q" not in text
    assert "core.health_gate" not in text
