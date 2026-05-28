from __future__ import annotations

import json
from datetime import datetime, timezone

from tools.repo_forensics.artifact_freshness import evaluate_artifact_freshness
from tools.repo_forensics.config_loader import load_config
from tools.repo_forensics.evidence_auditor import audit_evidence


BROKER_FIELD = "broker" + "_api_called"
ORDER_FIELD = "is_" + "order_action"
LIVE_FIELD = "live_" + "order_action"
BROKER_ORDER_FIELD = "broker_" + "order_action"


def _candidate_record(**updates):
    record = {
        "candidate_id": "C1",
        "source": "strategy.test",
        "mode": "PAPER",
        "timestamp": "2026-05-28T10:00:00Z",
        "reason": "candidate reviewed",
        ORDER_FIELD: False,
        BROKER_FIELD: False,
        LIVE_FIELD: False,
        BROKER_ORDER_FIELD: False,
        "decision": "REVIEWED",
    }
    record.update(updates)
    return record


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_profile(repo_root, *, max_age_seconds=3600):
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
  freshness_gate: true
  freshness_max_age_seconds: {max_age_seconds}
  freshness_now: 2026-05-28T10:30:00Z
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


def test_artifact_freshness_is_unknown_when_timestamp_absent(tmp_path):
    record = _candidate_record()
    record.pop("timestamp")

    result = evaluate_artifact_freshness(
        record,
        artifact_path="evidence/candidate.json",
        repo_root=tmp_path,
        now=datetime(2026, 5, 28, 10, 30, tzinfo=timezone.utc),
    )

    assert result.freshness == "UNKNOWN"
    assert result.complete is False
    assert result.issues == ("timestamp_absent",)


def test_artifact_freshness_is_stale_when_threshold_exceeded(tmp_path):
    result = evaluate_artifact_freshness(
        _candidate_record(timestamp="2026-05-28T08:00:00Z"),
        artifact_path="evidence/candidate.json",
        repo_root=tmp_path,
        max_age_seconds=3600,
        now=datetime(2026, 5, 28, 10, 30, tzinfo=timezone.utc),
    )

    assert result.freshness == "STALE"
    assert result.complete is False
    assert "artifact_stale" in result.issues
    assert result.age_seconds == 9000


def test_artifact_freshness_fails_when_latest_marker_target_is_absent(tmp_path):
    result = evaluate_artifact_freshness(
        _candidate_record(latest_path="evidence/latest.json"),
        artifact_path="evidence/candidate.json",
        repo_root=tmp_path,
        max_age_seconds=3600,
        now=datetime(2026, 5, 28, 10, 30, tzinfo=timezone.utc),
    )

    assert result.freshness == "UNKNOWN"
    assert result.complete is False
    assert "latest_marker_target_absent" in result.issues


def test_artifact_freshness_passes_when_artifact_is_fresh_and_complete(tmp_path):
    artifact = tmp_path / "evidence" / "candidate.json"
    _write(artifact, "{}")
    record = _candidate_record(latest_path="evidence/candidate.json", session_id="S1", consumed_at="2026-05-28T10:05:00Z")

    result = evaluate_artifact_freshness(
        record,
        artifact_path="evidence/candidate.json",
        repo_root=tmp_path,
        max_age_seconds=3600,
        now=datetime(2026, 5, 28, 10, 30, tzinfo=timezone.utc),
    )

    assert result.freshness == "FRESH"
    assert result.complete is True
    assert result.issues == ()
    assert result.gap_seconds == 300


def test_evidence_auditor_emits_unknown_freshness_finding_when_gate_enabled(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    record = _candidate_record()
    record.pop("timestamp")
    _write(tmp_path / "evidence" / "candidate.json", json.dumps(record))
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.reviewed_files == 1
    assert any(finding.evidence_type == "artifact_freshness" for finding in report.unknown)
    finding = next(finding for finding in report.unknown if finding.evidence_type == "artifact_freshness")
    assert "timestamp_absent" in finding.missing_fields


def test_evidence_auditor_emits_stale_freshness_finding_when_threshold_exceeded(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    record = _candidate_record(timestamp="2026-05-28T08:00:00Z")
    _write(tmp_path / "evidence" / "candidate.json", json.dumps(record))
    config = load_config(_write_profile(tmp_path, max_age_seconds=60))

    report = audit_evidence(tmp_path, config)

    stale_findings = [finding for finding in report.findings if finding.evidence_type == "artifact_freshness"]
    assert stale_findings
    assert stale_findings[0].severity == "STALE"
    assert "artifact_stale" in stale_findings[0].missing_fields


def test_evidence_auditor_high_fails_when_latest_marker_target_is_absent(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    record = _candidate_record(latest_path="evidence/latest.json")
    _write(tmp_path / "evidence" / "candidate.json", json.dumps(record))
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert any(finding.evidence_type == "artifact_freshness" for finding in report.high)
    finding = next(finding for finding in report.high if finding.evidence_type == "artifact_freshness")
    assert "latest_marker_target_absent" in finding.missing_fields


def test_evidence_auditor_has_no_freshness_finding_for_fresh_complete_artifact(tmp_path):
    _write(tmp_path / "app.py", "x = 1\n")
    record = _candidate_record(latest_path="evidence/candidate.json", session_id="S1", consumed_at="2026-05-28T10:05:00Z")
    _write(tmp_path / "evidence" / "candidate.json", json.dumps(record))
    config = load_config(_write_profile(tmp_path))

    report = audit_evidence(tmp_path, config)

    assert report.reviewed_files == 1
    assert not [finding for finding in report.findings if finding.evidence_type == "artifact_freshness"]
