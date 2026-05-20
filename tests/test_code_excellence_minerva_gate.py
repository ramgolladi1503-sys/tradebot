from __future__ import annotations

import textwrap

import pytest

from tools.code_excellence.minerva_gate import (
    MinervaGateError,
    read_changed_paths_file,
    render_minerva_gate_report,
    run_minerva_gate,
)
from tools.repo_forensics.config_loader import ConfigError


def _config_text(*, include_unknown: bool = True) -> str:
    unknown = "      - UNKNOWN\n" if include_unknown else ""
    return f"""
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
      - SHAPE_ONLY
      - UNIT_BEHAVIOR
      - SAFETY_REGRESSION
      - RUNTIME_COMMAND
      - EVIDENCE_CONTRACT
      - FAKE_CONFIDENCE
{unknown}    weak_test_patterns:
      - assert key exists only
    required_negative_tests:
      - fallback_candidate_cannot_be_executable
      - stale_feed_blocks_order_intent
    output_required:
      - test_classification_summary
  cerberus:
    mission: sim_paper_live_safety_boundary_guard
    protected_modes:
      - PAPER
    forbidden_import_markers:
      - place_order
    required_non_action_fields:
      - is_order_action=false
    block_on:
      - read_only_sets_order_action_true
    output_required:
      - safety_boundary_status
"""


def _write_config(tmp_path, *, include_unknown: bool = True):
    path = tmp_path / ".gsd-forensics.yaml"
    path.write_text(_config_text(include_unknown=include_unknown), encoding="utf-8")
    return path


def _write_test(repo_root, relative_path: str, source: str):
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def test_minerva_gate_passes_behavior_test_and_blocks_shape_only_test(tmp_path):
    config = _write_config(tmp_path)
    _write_test(
        tmp_path,
        "tests/test_behavior.py",
        """
        def test_blocks_bad_state():
            result = {"decision": "blocked"}
            assert result["decision"] == "blocked"
        """,
    )
    _write_test(
        tmp_path,
        "tests/test_shape_only.py",
        """
        def test_shape_only():
            result = {"decision": "blocked"}
            assert "decision" in result
        """,
    )

    report = run_minerva_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tests/test_behavior.py", "tests/test_shape_only.py"),
    )

    assert report.pass_count == 1
    assert report.block_count == 1
    blocked = report.blocked_findings[0]
    assert blocked.path == "tests/test_shape_only.py"
    assert blocked.reason == "shape_only_test_not_valid_proof"
    assert report.exit_code == 1


def test_minerva_gate_scopes_to_changed_paths_only(tmp_path):
    config = _write_config(tmp_path)
    _write_test(
        tmp_path,
        "tests/test_good.py",
        """
        def test_good_behavior():
            assert 1 == 1
        """,
    )
    _write_test(
        tmp_path,
        "tests/test_bad.py",
        """
        def test_bad_shape_only():
            data = {"x": 1}
            assert "x" in data
        """,
    )

    report = run_minerva_gate(repo_root=tmp_path, config_path=config, changed_paths=("tests/test_good.py",))

    assert [finding.path for finding in report.findings] == ["tests/test_good.py"]
    assert report.block_count == 0
    assert report.exit_code == 0


def test_minerva_gate_blocks_unknown_test_reality(tmp_path):
    config = _write_config(tmp_path)
    _write_test(
        tmp_path,
        "tests/test_unknown.py",
        """
        def test_no_assertions():
            value = 1 + 1
        """,
    )

    report = run_minerva_gate(repo_root=tmp_path, config_path=config, changed_paths=("tests/test_unknown.py",))

    assert report.block_count == 1
    assert report.blocked_findings[0].test_class == "UNKNOWN"
    assert report.blocked_findings[0].reason == "unknown_test_reality_not_valid_proof"


def test_minerva_gate_report_contains_required_negative_tests(tmp_path):
    config = _write_config(tmp_path)
    _write_test(
        tmp_path,
        "tests/test_safety.py",
        """
        def test_fallback_candidate_cannot_be_executable():
            result = {"is_order_action": False}
            assert result["is_order_action"] is False
        """,
    )

    report = run_minerva_gate(repo_root=tmp_path, config_path=config, changed_paths=("tests/test_safety.py",))
    rendered = render_minerva_gate_report(report)

    assert "fallback_candidate_cannot_be_executable" in rendered
    assert "stale_feed_blocks_order_intent" in rendered
    assert "tests/test_safety.py" in rendered
    assert report.block_count == 0


def test_read_changed_paths_file_rejects_missing_file(tmp_path):
    with pytest.raises(MinervaGateError, match="changed_paths_file_not_found"):
        read_changed_paths_file(tmp_path / "missing.txt")


def test_minerva_gate_fails_closed_for_unconfigured_class(tmp_path):
    config = _write_config(tmp_path, include_unknown=False)
    _write_test(
        tmp_path,
        "tests/test_unknown.py",
        """
        def test_no_assertions():
            value = 1 + 1
        """,
    )

    with pytest.raises(ConfigError, match="minerva_class_not_configured class=UNKNOWN"):
        run_minerva_gate(repo_root=tmp_path, config_path=config, changed_paths=("tests/test_unknown.py",))
