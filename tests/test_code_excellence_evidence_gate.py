from __future__ import annotations

import json
import textwrap

import pytest

from tools.code_excellence.evidence_gate import (
    EvidenceGateError,
    read_changed_paths_file,
    render_evidence_gate_report,
    run_evidence_gate,
)
from tools.repo_forensics.config_loader import ConfigError


def _config_text() -> str:
    return """
gsd_forensics_config_version: 1
project:
  name: sample
entrypoints:
  required:
    - main.py
critical_modules:
  runtime:
    - main.py
agent_parameters:
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
      - docs/reports
      - runtime/records
    weak_evidence_patterns:
      - status ok only
      - value true only
      - missing reason
      - missing item_id
      - missing call_value
    output_required:
      - missing_fields
      - weak_evidence
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


def _valid_payload() -> dict[str, object]:
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


def test_evidence_gate_passes_valid_json_evidence(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_payload()))

    report = run_evidence_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("docs/agent_reviews/evidence.json",),
    )

    assert report.pass_count == 1
    assert report.block_count == 0
    assert report.exit_code == 0


def test_evidence_gate_blocks_missing_required_field(tmp_path):
    config = _write_config(tmp_path)
    payload = _valid_payload()
    payload.pop("reason")
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(payload))

    report = run_evidence_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("docs/agent_reviews/evidence.json",),
    )

    assert report.block_count == 1
    finding = report.blocked_findings[0]
    assert finding.reason == "required_evidence_field_missing"
    assert finding.field == "reason"
    assert report.exit_code == 1


def test_evidence_gate_blocks_empty_required_field(tmp_path):
    config = _write_config(tmp_path)
    payload = _valid_payload()
    payload["item_id"] = ""
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(payload))

    report = run_evidence_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("docs/agent_reviews/evidence.json",),
    )

    assert report.block_count == 1
    finding = report.blocked_findings[0]
    assert finding.reason == "required_evidence_field_empty"
    assert finding.field == "item_id"


def test_evidence_gate_blocks_weak_evidence_pattern(tmp_path):
    config = _write_config(tmp_path)
    _write_file(
        tmp_path,
        "docs/agent_reviews/evidence.md",
        """
        mode: CHECK
        item_id: I-1
        result: reviewed
        reason: specific reason
        timestamp: 2026-05-20T00:00:00Z
        flag_value: false
        call_value: false
        source: unit-test
        status ok only
        """,
    )

    report = run_evidence_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("docs/agent_reviews/evidence.md",),
    )

    assert report.block_count == 1
    finding = report.blocked_findings[0]
    assert finding.reason == "weak_evidence_pattern_found"
    assert finding.field == "status ok only"


def test_evidence_gate_scopes_to_evidence_paths_only(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "docs/not_evidence/random.md", "status ok only")

    report = run_evidence_gate(
        repo_root=tmp_path,
        config_path=config,
        changed_paths=("docs/not_evidence/random.md",),
    )

    assert report.findings == ()
    assert report.block_count == 0


def test_evidence_gate_report_lists_contract(tmp_path):
    config = _write_config(tmp_path)
    _write_file(tmp_path, "docs/agent_reviews/evidence.json", json.dumps(_valid_payload()))

    report = run_evidence_gate(repo_root=tmp_path, config_path=config, changed_paths=("docs/agent_reviews/evidence.json",))
    rendered = render_evidence_gate_report(report)

    assert "item_id" in rendered
    assert "call_value" in rendered
    assert "status ok only" in rendered
    assert "evidence_contract_satisfied" in rendered


def test_read_changed_paths_file_rejects_missing_file(tmp_path):
    with pytest.raises(EvidenceGateError, match="changed_paths_file_not_found"):
        read_changed_paths_file(tmp_path / "missing.txt")


def test_evidence_gate_requires_changed_paths(tmp_path):
    config = _write_config(tmp_path)

    with pytest.raises(EvidenceGateError, match="changed_paths_required_for_evidence_gate"):
        run_evidence_gate(repo_root=tmp_path, config_path=config)


def test_evidence_gate_rejects_path_outside_repo(tmp_path):
    config = _write_config(tmp_path)
    outside = tmp_path.parent / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(EvidenceGateError, match="changed_path_outside_repo"):
        run_evidence_gate(repo_root=tmp_path, config_path=config, changed_paths=("../outside.json",))


def test_evidence_gate_fails_closed_when_config_missing(tmp_path):
    path = tmp_path / ".gsd-forensics.yaml"
    path.write_text("gsd_forensics_config_version: 1\nproject:\n  name: sample\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="agent_parameters_missing agent=evidence_auditor"):
        run_evidence_gate(repo_root=tmp_path, config_path=path, changed_paths=("docs/agent_reviews/evidence.json",))
