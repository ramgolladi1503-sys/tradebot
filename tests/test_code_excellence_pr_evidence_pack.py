from __future__ import annotations

import json
import textwrap

import pytest

from tools.code_excellence.pr_evidence_pack import (
    PREvidencePackError,
    build_pr_evidence_pack,
    build_pr_evidence_pack_from_paths,
    render_pr_body,
    render_evidence_pack,
)
from tools.code_excellence.unified_gate_runner import run_unified_ce_gates


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


def test_pr_evidence_pack_renders_pr_ready_body(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_evidence()))
    report = run_unified_ce_gates(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("docs/agent_reviews/evidence.json",),
    )

    pack = build_pr_evidence_pack(
        pr_label="CE-12 — PR Evidence Pack Generator",
        changed_files=("tools/code_excellence/pr_evidence_pack.py", "docs/agent_reviews/evidence.json"),
        unified_report=report,
        test_commands=("PYTHONPATH=. pytest -q tests/test_code_excellence_pr_evidence_pack.py",),
        next_step="CE-13 — CI Wiring for CE Gates.",
    )
    body = render_pr_body(pack)

    assert "CE-12 — PR Evidence Pack Generator" in body
    assert "## Files Changed" in body
    assert "tools/code_excellence/pr_evidence_pack.py" in body
    assert "## Unified CE Gate Summary" in body
    assert "minerva" in body
    assert "cerberus" in body
    assert "evidence" in body
    assert "PYTHONPATH=. pytest -q tests/test_code_excellence_pr_evidence_pack.py" in body
    assert "CE-13 — CI Wiring for CE Gates." in body


def test_pr_evidence_pack_includes_failed_gate_summary(tmp_path):
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
    report = run_unified_ce_gates(repo_root=tmp_path, config_path=config, changed_paths=("tests/test_shape_only.py",))

    pack = build_pr_evidence_pack(
        pr_label="CE-12 — PR Evidence Pack Generator",
        changed_files=("tests/test_shape_only.py",),
        unified_report=report,
        test_commands=("PYTHONPATH=. pytest -q tests/test_code_excellence_pr_evidence_pack.py",),
        next_step="Fix blocked gate before merge.",
    )
    body = render_pr_body(pack)

    assert pack.exit_code == 1
    assert "## Blocked or Failed Gates" in body
    assert "minerva" in body
    assert "blocked findings present" in body


def test_pr_evidence_pack_from_paths_uses_changed_paths_file(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_evidence()))
    changed_paths_file = tmp_path / "changed.txt"
    changed_paths_file.write_text("docs/agent_reviews/evidence.json\n", encoding="utf-8")

    pack = build_pr_evidence_pack_from_paths(
        repo_root=tmp_path,
        config_path=config,
        changed_paths_file=changed_paths_file,
        pr_label="CE-12 — PR Evidence Pack Generator",
        test_commands=("pytest -q tests/test_code_excellence_pr_evidence_pack.py",),
        next_step="Review CI.",
    )

    rendered = render_evidence_pack(pack)
    assert "## PR Body" in rendered
    assert "## Unified Gate Detail" in rendered
    assert "docs/agent_reviews/evidence.json" in rendered
    assert pack.exit_code == 0


def test_pr_evidence_pack_requires_label(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_evidence()))
    report = run_unified_ce_gates(repo_root=tmp_path, config_path=config, changed_paths=("docs/agent_reviews/evidence.json",))

    with pytest.raises(PREvidencePackError, match="pr_label_required"):
        build_pr_evidence_pack(
            pr_label="",
            changed_files=("docs/agent_reviews/evidence.json",),
            unified_report=report,
            test_commands=("pytest -q tests/test_code_excellence_pr_evidence_pack.py",),
            next_step="Review CI.",
        )


def test_pr_evidence_pack_requires_changed_files(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_evidence()))
    report = run_unified_ce_gates(repo_root=tmp_path, config_path=config, changed_paths=("docs/agent_reviews/evidence.json",))

    with pytest.raises(PREvidencePackError, match="changed_files_required"):
        build_pr_evidence_pack(
            pr_label="CE-12",
            changed_files=(),
            unified_report=report,
            test_commands=("pytest -q tests/test_code_excellence_pr_evidence_pack.py",),
            next_step="Review CI.",
        )


def test_pr_evidence_pack_requires_test_commands(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_evidence()))
    report = run_unified_ce_gates(repo_root=tmp_path, config_path=config, changed_paths=("docs/agent_reviews/evidence.json",))

    with pytest.raises(PREvidencePackError, match="test_commands_required"):
        build_pr_evidence_pack(
            pr_label="CE-12",
            changed_files=("docs/agent_reviews/evidence.json",),
            unified_report=report,
            test_commands=(),
            next_step="Review CI.",
        )
