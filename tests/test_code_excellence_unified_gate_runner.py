from __future__ import annotations

import json
import textwrap

import pytest

from tools.code_excellence.unified_gate_runner import (
    UnifiedGateRunnerError,
    render_unified_ce_gate_report,
    run_unified_ce_gates,
)


def _config_text() -> str:
    return """
gsd_forensics_config_version: 1
project:
  name: sample
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
      - CHECK
    forbidden_import_markers:
      - restricted_call
    required_non_action_fields:
      - flag_value=false
      - call_value=false
    block_on:
      - restricted_marker_found
    output_required:
      - boundary_status
  evidence_auditor:
    mission: traceability_checker
    required_fields:
      - mode
      - item_id
      - result
      - reason
      - timestamp
      - flag_value
      - call_value
      - source
    evidence_paths:
      - docs/agent_reviews
    weak_evidence_patterns:
      - status ok only
    output_required:
      - traceability_status
"""


def _write_config(tmp_path):
    path = tmp_path / ".gsd-forensics.yaml"
    path.write_text(_config_text(), encoding="utf-8")
    return path


def _write_file(repo_root, relative_path: str, content: str):
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    return path


def _valid_evidence() -> dict[str, object]:
    return {
        "mode": "CHECK",
        "item_id": "I-1",
        "result": "reviewed",
        "reason": "specific reason",
        "timestamp": "2026-05-20T00:00:00Z",
        "flag_value": False,
        "call_value": False,
        "source": "unit-test",
    }


def test_unified_ce_gates_pass_all_child_gates(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tests/test_behavior.py",
        """
        def test_valid_behavior():
            result = {"value": "ok"}
            assert result["value"] == "ok"
        """,
    )
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_evidence()))

    report = run_unified_ce_gates(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tests/test_behavior.py", "docs/agent_reviews/evidence.json"),
    )

    assert report.exit_code == 0
    assert [status.gate for status in report.statuses] == ["minerva", "cerberus", "evidence"]
    assert all(status.status == "PASS" for status in report.statuses)
    assert report.total_blocks == 0


def test_unified_ce_gates_preserve_child_gate_block_status(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "tests/test_shape_only.py",
        """
        def test_shape_only():
            payload = {"x": 1}
            assert isinstance(payload, dict)
        """,
    )
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_evidence()))

    report = run_unified_ce_gates(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("tests/test_shape_only.py", "docs/agent_reviews/evidence.json"),
    )

    statuses = {status.gate: status for status in report.statuses}
    assert report.exit_code == 1
    assert statuses["minerva"].status == "BLOCK"
    assert statuses["minerva"].block_count == 1
    assert statuses["cerberus"].status == "PASS"
    assert statuses["evidence"].status == "PASS"


def test_unified_ce_gates_preserve_child_gate_error_status(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "../outside_guard.txt", "noop")

    report = run_unified_ce_gates(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("../outside_guard.txt",),
    )

    statuses = {status.gate: status for status in report.statuses}
    assert report.exit_code == 1
    assert statuses["minerva"].status == "PASS"
    assert statuses["cerberus"].status == "ERROR"
    assert statuses["cerberus"].exit_code == 2
    assert "changed_path_outside_repo" in statuses["cerberus"].error
    assert statuses["evidence"].status == "ERROR"


def test_unified_ce_gate_report_contains_summary_and_gate_details(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_evidence()))

    report = run_unified_ce_gates(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("docs/agent_reviews/evidence.json",),
    )
    rendered = render_unified_ce_gate_report(report)

    assert "Unified Code Excellence Gate Report" in rendered
    assert "minerva" in rendered
    assert "cerberus" in rendered
    assert "evidence" in rendered
    assert "docs/agent_reviews/evidence.json" in rendered


def test_unified_ce_gates_require_changed_paths(tmp_path):
    config = _write_config(tmp_path)

    with pytest.raises(UnifiedGateRunnerError, match="changed_paths_required_for_unified_ce_gates"):
        run_unified_ce_gates(repo_root=tmp_path, config_path=config, changed_paths=())
