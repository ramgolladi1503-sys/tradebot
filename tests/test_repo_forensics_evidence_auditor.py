from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.evidence_auditor import audit_evidence


def _write_profile(repo_root):
    cfg = repo_root / "forensics.yaml"
    cfg.write_text(
        """
project:
  name: tradebot
baseline_rules:
  unknown_is_not_pass: true
entrypoints:
  required:
    - app.py
critical_modules:
  runtime:
    - app.py
agent_parameters:
  evidence_auditor:
    evidence_paths:
      - evidence
exclude:
  directories:
    - cache_dir
evidence:
  required_fields:
    - mode
    - candidate_id
    - decision
    - reason
    - timestamp
    - is_order_action
    - broker_api_called
    - source
""",
        encoding="utf-8",
    )
    return cfg


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_evidence_auditor_flags_missing_decision_fields(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "decision.json",
        '{"mode":"PAPER","candidate_id":"C1","decision":"BLOCKED"}',
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.reviewed_files == 1
    assert report.high
    assert "reason" in report.high[0].missing_fields
    assert "broker_api_called" in report.high[0].missing_fields


def test_evidence_auditor_flags_status_only_payload(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "evidence" / "weak.json", '{"status":"ok","safe":true}')
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.medium
    assert report.medium[0].evidence.startswith("weak_status_only")


def test_evidence_auditor_accepts_complete_decision_record(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "good.jsonl",
        '{"mode":"PAPER","candidate_id":"C1","decision":"BLOCKED","reason":"TEST","timestamp":"2026-01-01T00:00:00Z","is_order_action":false,"broker_api_called":false,"source":"test"}\n',
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.reviewed_files == 1
    assert report.findings == []
