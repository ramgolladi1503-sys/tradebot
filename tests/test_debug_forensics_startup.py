import json
from pathlib import Path

from core.debug_forensics.evidence_reader import load_runtime_startup_evidence
from core.debug_forensics.flow_analyzer import analyze_evidence
from core.debug_forensics.models import Severity
from core.debug_forensics.report_writer import report_exit_code, write_reports
from core.runtime_boot_identity import SCHEMA_VERSION


def _event(name, *, run_id="run-debug", boot_epoch=1000.0, ts_epoch=1001.0, is_order_action=False):
    return {
        "event": name,
        "run_id": run_id,
        "boot_epoch": boot_epoch,
        "pid": 123,
        "writer": "runtime_startup_lifecycle.event",
        "schema_version": SCHEMA_VERSION,
        "ts_epoch": ts_epoch,
        "source": "unit.test",
        "details": {},
        "error": "",
        "is_order_action": is_order_action,
    }


def _write_evidence(tmp_path, events):
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True)
    rows = []
    for index, event_name in enumerate(events):
        if isinstance(event_name, dict):
            rows.append(event_name)
        else:
            rows.append(_event(event_name, ts_epoch=1001.0 + index))
    (log_dir / "runtime_startup_lifecycle.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
        encoding="utf-8",
    )
    latest = {
        "run_id": "run-debug",
        "boot_epoch": 1000.0,
        "pid": 123,
        "writer": "runtime_startup_lifecycle",
        "schema_version": SCHEMA_VERSION,
        "is_order_action": False,
    }
    (log_dir / "runtime_startup_lifecycle_latest.json").write_text(json.dumps(latest), encoding="utf-8")
    return log_dir


def test_startup_forensics_detects_first_missing_event(tmp_path):
    log_dir = _write_evidence(tmp_path, ["MAIN_BOOT_STARTED", "MAIN_SAFETY_VALIDATED", "DB_READY_COMPLETED"])

    evidence = load_runtime_startup_evidence(logs_path=log_dir)
    report = analyze_evidence(evidence)

    assert report.evidence_valid is True
    assert report.last_confirmed_event == "DB_READY_COMPLETED"
    assert report.first_missing_event == "ORCHESTRATOR_INIT_ENTERED"
    assert any(finding.severity == Severity.BLOCKER for finding in report.findings)
    assert report_exit_code(report) == 1
    assert "WebSocket" in "\n".join(report.killed_hypotheses)


def test_startup_forensics_rejects_order_action_evidence(tmp_path):
    log_dir = _write_evidence(
        tmp_path,
        [
            "MAIN_BOOT_STARTED",
            _event("BROKER_ORDER_SUBMITTED", ts_epoch=1002.0, is_order_action=True),
        ],
    )

    evidence = load_runtime_startup_evidence(logs_path=log_dir)
    report = analyze_evidence(evidence)

    assert any(finding.severity == Severity.SAFETY_VIOLATION for finding in report.findings)
    assert report_exit_code(report) == 1


def test_startup_forensics_rejects_mixed_boot_epoch(tmp_path):
    log_dir = _write_evidence(
        tmp_path,
        [
            _event("MAIN_BOOT_STARTED", boot_epoch=1000.0, ts_epoch=1001.0),
            _event("MAIN_SAFETY_VALIDATED", boot_epoch=2000.0, ts_epoch=1002.0),
        ],
    )

    evidence = load_runtime_startup_evidence(logs_path=log_dir)
    report = analyze_evidence(evidence)

    assert evidence.valid is False
    assert any("mixed_boot_epoch" in error for error in evidence.validation_errors)
    assert any(finding.severity == Severity.INSUFFICIENT_EVIDENCE for finding in report.findings)


def test_startup_forensics_rejects_non_monotonic_events(tmp_path):
    log_dir = _write_evidence(
        tmp_path,
        [
            _event("MAIN_BOOT_STARTED", ts_epoch=1002.0),
            _event("MAIN_SAFETY_VALIDATED", ts_epoch=1001.0),
        ],
    )

    evidence = load_runtime_startup_evidence(logs_path=log_dir)

    assert evidence.valid is False
    assert any("non_monotonic_event_ts" in error for error in evidence.validation_errors)


def test_startup_forensics_writes_json_and_markdown_reports(tmp_path):
    log_dir = _write_evidence(tmp_path, ["MAIN_BOOT_STARTED"])
    evidence = load_runtime_startup_evidence(logs_path=log_dir)
    report = analyze_evidence(evidence)

    json_path, md_path = write_reports(report, base_dir=tmp_path / "reports")

    assert json_path.exists()
    assert md_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["profile"] == "startup"
    assert payload["is_order_action"] is False
    text = md_path.read_text(encoding="utf-8")
    assert "Debug Forensics Report" in text
    assert "Killed Hypotheses" in text
