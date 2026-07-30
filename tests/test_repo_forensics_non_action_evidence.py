from __future__ import annotations

from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.evidence_auditor import audit_evidence


BROKER_FIELD = "broker" + "_api_called"
LIVE_FIELD = "live_" + "order_action"
BROKER_ORDER_FIELD = "broker_" + "order_action"
ORDER_FIELD = "is_" + "order_action"


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


def _write_strict_profile(repo_root):
    cfg = repo_root / "forensics.yaml"
    cfg.write_text(
        f"""
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
  strict_non_action_gate: true
  required_fields:
    - mode
    - candidate_id
    - decision
    - reason
    - timestamp
    - {ORDER_FIELD}
    - {BROKER_FIELD}
    - {LIVE_FIELD}
    - {BROKER_ORDER_FIELD}
    - source
""",
        encoding="utf-8",
    )
    return cfg


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _complete_record() -> str:
    return (
        '{"mode":"PAPER","candidate_id":"C1","decision":"BLOCKED","reason":"TEST",'
        '"timestamp":"2026-01-01T00:00:00Z","is_order_action":false,'
        '"broker_api_called":false,"live_order_action":false,'
        '"broker_order_action":false,"source":"test"}'
    )


def test_non_action_evidence_flags_absent_broker_field(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "decision.json",
        '{"mode":"PAPER","candidate_id":"C1","decision":"BLOCKED","reason":"TEST",'
        '"timestamp":"2026-01-01T00:00:00Z","is_order_action":false,'
        '"source":"test"}',
    )
    config = load_config(_write_strict_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.high
    assert BROKER_FIELD in report.high[0].missing_fields
    assert LIVE_FIELD in report.high[0].missing_fields
    assert BROKER_ORDER_FIELD in report.high[0].missing_fields
    assert report.high[0].scope == "new_regression"


def test_non_action_evidence_preserves_default_contract_for_extended_missing_fields(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "decision.json",
        '{"mode":"PAPER","candidate_id":"C1","decision":"BLOCKED","reason":"TEST",'
        '"timestamp":"2026-01-01T00:00:00Z","is_order_action":false,'
        '"broker_api_called":false,"source":"test"}',
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.findings == []


def test_non_action_evidence_blocks_readonly_action_true_when_strict_gate_is_enabled(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "report.json",
        _complete_record().replace(f'"{ORDER_FIELD}":false', f'"{ORDER_FIELD}":true'),
    )
    config = load_config(_write_strict_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert [finding.evidence_type for finding in report.high] == ["record"]
    assert report.high[0].evidence.startswith("non_action_field_not_false")
    assert report.high[0].missing_fields == [ORDER_FIELD]


def test_non_action_evidence_tracks_non_false_action_as_baseline_debt_when_not_strict(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "report.json",
        _complete_record().replace(f'"{ORDER_FIELD}":false', f'"{ORDER_FIELD}":true'),
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.high == []
    assert report.baseline_debt
    assert report.baseline_debt[0].missing_fields == [ORDER_FIELD]


def test_non_action_evidence_accepts_all_fields_false(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(tmp_path / "evidence" / "good.jsonl", _complete_record() + "\n")
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.reviewed_files == 1
    assert report.findings == []


def test_non_action_evidence_tracks_baseline_debt_separately(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "archive" / "old_report.json",
        '{"mode":"PAPER","candidate_id":"C1","decision":"BLOCKED"}',
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.new_regressions == []
    assert report.baseline_debt
    assert report.baseline_debt[0].scope == "baseline_debt"


def test_execution_fill_with_mode_is_not_misclassified_as_candidate_decision(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "events.jsonl",
        '{"event_type":"EXECUTION_FILL","mode":"PAPER","order_id":"O1",'
        '"trade_id":"T1","price":101.0,"qty":10,"timestamp":"2026-01-01T00:00:00Z"}\n',
    )
    config = load_config(_write_strict_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.reviewed_files == 1
    assert report.findings == []


def test_explicit_candidate_event_still_requires_complete_decision_schema(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "candidate_event.json",
        '{"event_type":"CANDIDATE_DECISION","mode":"PAPER","candidate_id":"C1"}',
    )
    config = load_config(_write_strict_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.high
    missing = set(report.high[0].missing_fields)
    assert "decision" in missing
    assert "reason" in missing
    assert ORDER_FIELD in missing
    assert BROKER_FIELD in missing
