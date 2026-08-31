from __future__ import annotations

import textwrap
import subprocess

import pytest

from tools.code_excellence.cerberus_gate import (
    CerberusGateError,
    read_changed_paths_file,
    render_cerberus_gate_report,
    run_cerberus_gate,
)


def _config_text() -> str:
    return """
gsd_forensics_config_version: 1
project:
  name: tradebot
baseline_rules:
  no_target_runtime_execution: true
entrypoints:
  required:
    - main.py
critical_modules:
  runtime:
    - main.py
agent_parameters:
  ariadne:
    mission: root_cause_investigator
    input_sources:
      - repo_forensics_report
    cluster_signals:
      - same_file
    confidence_levels:
      - CONFIRMED
    output_required:
      - finding_cluster
  daedalus:
    mission: remediation_architect
    decisions:
      - FIX_NOW
    required_contract_fields:
      - root_cause
    block_on:
      - no_root_cause
    output_required:
      - scoped_pr_contract
  vulcan:
    mission: production_hardening_from_scoped_contract
    allowed_only_after:
      - daedalus_contract
    hardening_targets:
      - safe_defaults
    forbidden_actions:
      - broad_repo_rewrite
    output_required:
      - maturity_before
  minerva:
    mission: test_reality_classifier
    classes:
      - UNIT_BEHAVIOR
      - UNKNOWN
    weak_test_patterns:
      - assert key exists only
    required_negative_tests:
      - invalid_state_cannot_pass
    output_required:
      - test_classification_summary
  cerberus:
    mission: boundary_guard
    protected_modes:
      - SIM
      - PAPER
      - LIVE
    forbidden_import_markers:
      - restricted_call
      - restricted_client.place
    required_non_action_fields:
      - no_action=false
      - client_called=false
    block_on:
      - restricted_marker_found
      - non_action_field_regression
    output_required:
      - boundary_status
      - proof_required
"""


def _write_config(tmp_path):
    path = tmp_path / ".gsd-forensics.yaml"
    path.write_text(_config_text(), encoding="utf-8")
    return path


def _write_file(repo_root, relative_path: str, source: str):
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def test_cerberus_gate_passes_clean_scoped_file(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tools/safe_report.py",
        """
        REPORT = {
            "no_action": False,
            "client_called": False,
            "reason": "static proof only",
        }
        """,
    )

    report = run_cerberus_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tools/safe_report.py",),
    )

    assert report.pass_count == 1
    assert report.block_count == 0
    assert report.exit_code == 0


def test_cerberus_gate_blocks_forbidden_marker_in_scoped_file(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tools/unsafe_adapter.py",
        """
        def run():
            return restricted_client.place(payload={})
        """,
    )

    report = run_cerberus_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tools/unsafe_adapter.py",),
    )

    assert report.pass_count == 0
    assert report.block_count == 1
    finding = report.blocked_findings[0]
    assert finding.path == "tools/unsafe_adapter.py"
    assert finding.reason == "forbidden_boundary_marker_in_scoped_file"
    assert finding.marker == "restricted_client.place"
    assert report.exit_code == 1


def test_cerberus_gate_blocks_non_action_field_regression(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tools/bad_evidence.py",
        """
        REPORT = {
            "no_action": True,
            "client_called": False,
        }
        """,
    )

    report = run_cerberus_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tools/bad_evidence.py",),
    )

    assert report.block_count == 1
    finding = report.blocked_findings[0]
    assert finding.reason == "non_action_field_not_explicitly_false"
    assert finding.marker == "no_action=false"


def test_cerberus_gate_allows_unsafe_test_fixture_when_false_output_is_proven(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tests/test_fail_closed.py",
        """
        def test_fail_closed():
            unsafe = {"no_action": True, "client_called": True}
            result = {"no_action": False, "client_called": False}
            assert result["no_action"] is False
            assert result["client_called"] is False
        """,
    )

    report = run_cerberus_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tests/test_fail_closed.py",),
    )

    assert report.block_count == 0
    assert report.exit_code == 0


def test_cerberus_gate_still_blocks_unproven_unsafe_test_fixture(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tests/test_unproven_fixture.py",
        """
        def test_unproven_fixture():
            unsafe = {"no_action": True, "client_called": True}
            assert unsafe
        """,
    )

    report = run_cerberus_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tests/test_unproven_fixture.py",),
    )

    assert report.block_count == 2
    assert {finding.marker for finding in report.blocked_findings} == {
        "no_action=false",
        "client_called=false",
    }


def test_cerberus_gate_ignores_required_field_name_constants(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tests/test_contract_header.py",
        """
        REQUIRED_FIELDS = (
            "no_action:",
            "client_called:",
        )

        def test_header_lists_required_fields():
            header = "no_action: false\\nclient_called: false"
            for field in REQUIRED_FIELDS:
                assert field in header
        """,
    )

    report = run_cerberus_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tests/test_contract_header.py",),
    )

    assert report.block_count == 0
    assert report.exit_code == 0


def test_cerberus_gate_scopes_to_changed_paths_only(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tools/scoped_clean.py",
        """
        VALUE = "clean"
        """,
    )
    _write_file(
        tmp_path,
        "tools/unscoped_bad.py",
        """
        VALUE = restricted_call()
        """,
    )

    report = run_cerberus_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tools/scoped_clean.py",),
    )

    assert [finding.path for finding in report.findings] == ["tools/scoped_clean.py"]
    assert report.block_count == 0


def test_cerberus_gate_ignores_unchanged_baseline_marker(tmp_path, monkeypatch):
    config = _write_config(tmp_path)
    path = _write_file(tmp_path, "tools/adapter.py", "VALUE = restricted_call()\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
    path.write_text("VALUE = restricted_call()\nNOTE = 'changed-safe-line'\n", encoding="utf-8")
    monkeypatch.setenv("CERBERUS_BASE_REF", "HEAD~1")

    report = run_cerberus_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tools/adapter.py",),
    )

    assert report.block_count == 0
    assert report.exit_code == 0


def test_cerberus_gate_report_lists_configured_contract(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tools/safe_report.py",
        """
        VALUE = "clean"
        """,
    )

    report = run_cerberus_gate(repo_root=tmp_path, config_path=config, changed_paths=("tools/safe_report.py",))
    rendered = render_cerberus_gate_report(report)

    assert "SIM" in rendered
    assert "PAPER" in rendered
    assert "LIVE" in rendered
    assert "no_action=false" in rendered
    assert "client_called=false" in rendered


def test_read_changed_paths_file_rejects_missing_file(tmp_path):
    with pytest.raises(CerberusGateError, match="changed_paths_file_not_found"):
        read_changed_paths_file(tmp_path / "missing.txt")


def test_cerberus_gate_requires_changed_paths(tmp_path):
    config = _write_config(tmp_path)

    with pytest.raises(CerberusGateError, match="changed_paths_required_for_cerberus_gate"):
        run_cerberus_gate(repo_root=tmp_path, config_path=config)


def test_cerberus_gate_rejects_path_outside_repo(tmp_path):
    config = _write_config(tmp_path)
    outside = tmp_path.parent / "outside.py"
    outside.write_text("VALUE = 'outside'", encoding="utf-8")

    with pytest.raises(CerberusGateError, match="changed_path_outside_repo"):
        run_cerberus_gate(repo_root=tmp_path, config_path=config, changed_paths=("../outside.py",))
