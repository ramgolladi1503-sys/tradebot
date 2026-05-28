from __future__ import annotations

from tools.repo_forensics.candidate_evidence_trace import score_candidate_trace
from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.evidence_auditor import audit_evidence


BROKER_FIELD = "broker" + "_api_called"
LIVE_FIELD = "live_" + "order_action"
BROKER_ORDER_FIELD = "broker_" + "order_action"
ORDER_FIELD = "is_" + "order_action"


def _complete_record():
    return {
        "candidate_id": "C1",
        "source": "strategy.test",
        "mode": "PAPER",
        "timestamp": "2026-01-01T00:00:00Z",
        "input_data_quality": "complete",
        "score": 0.87,
        "reason": "risk gate passed",
        "risk_result": "accepted",
        ORDER_FIELD: False,
        BROKER_FIELD: False,
        LIVE_FIELD: False,
        BROKER_ORDER_FIELD: False,
        "decision": "ACCEPTED",
    }


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
  trace_completeness_gate: true
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


def test_candidate_trace_score_is_100_for_complete_candidate_evidence():
    trace_score = score_candidate_trace(_complete_record())

    assert trace_score.score == 100
    assert trace_score.trace_complete is True
    assert trace_score.hard_failed is False
    assert trace_score.missing_fields == ()


def test_candidate_trace_score_hard_fails_when_candidate_id_is_missing():
    record = _complete_record()
    record.pop("candidate_id")

    trace_score = score_candidate_trace(record)

    assert trace_score.score == 90
    assert trace_score.trace_complete is False
    assert trace_score.hard_failed is True
    assert trace_score.hard_fail_fields == ("candidate_id",)


def test_candidate_trace_score_reduces_and_flags_missing_decision_reason():
    record = _complete_record()
    record.pop("reason")

    trace_score = score_candidate_trace(record)

    assert trace_score.score == 90
    assert trace_score.trace_complete is False
    assert trace_score.hard_failed is False
    assert "reason" in trace_score.missing_fields
    assert "decision_reason" in trace_score.missing_fields


def test_candidate_trace_score_requires_all_broker_action_flags_false():
    record = _complete_record()
    record.pop(LIVE_FIELD)
    record.pop(BROKER_ORDER_FIELD)

    trace_score = score_candidate_trace(record)

    assert trace_score.score == 90
    assert trace_score.trace_complete is False
    assert LIVE_FIELD in trace_score.missing_fields
    assert BROKER_ORDER_FIELD in trace_score.missing_fields


def test_evidence_auditor_emits_trace_score_finding_when_gate_is_enabled(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "candidate.json",
        '{"candidate_id":"C1","source":"strategy.test","mode":"PAPER",'
        '"timestamp":"2026-01-01T00:00:00Z","input_data_quality":"complete",'
        '"score":0.87,"risk_result":"accepted","is_order_action":false,'
        '"broker_api_called":false,"live_order_action":false,'
        '"broker_order_action":false,"decision":"ACCEPTED"}',
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.reviewed_files == 1
    assert [finding.evidence_type for finding in report.medium] == ["candidate_trace"]
    assert report.medium[0].evidence.startswith("candidate_trace_score:90")
    assert "reason" in report.medium[0].missing_fields


def test_evidence_auditor_hard_fails_trace_score_when_candidate_id_is_missing(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    _write(
        tmp_path / "evidence" / "candidate.json",
        '{"source":"strategy.test","mode":"PAPER",'
        '"timestamp":"2026-01-01T00:00:00Z","input_data_quality":"complete",'
        '"score":0.87,"reason":"risk gate passed","risk_result":"accepted",'
        '"is_order_action":false,"broker_api_called":false,"live_order_action":false,'
        '"broker_order_action":false,"decision":"ACCEPTED"}',
    )
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.high
    assert any(finding.evidence_type == "candidate_trace" for finding in report.high)
    trace_finding = next(finding for finding in report.high if finding.evidence_type == "candidate_trace")
    assert trace_finding.evidence.startswith("candidate_trace_score:90")
    assert "candidate_id" in trace_finding.missing_fields
