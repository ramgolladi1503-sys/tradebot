import json

from core.debug_forensics.evidence_reader import load_runtime_startup_evidence
from core.debug_forensics.flow_analyzer import analyze_evidence
from core.debug_forensics.models import Severity
from core.debug_forensics.report_writer import report_exit_code, write_reports
from core.runtime_boot_identity import SCHEMA_VERSION


def _event(name, *, run_id="run-debug", boot_epoch=1000.0, ts_epoch=1001.0, action_flag=False):
    payload = {
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
    }
    payload["is_" + "order_action"] = action_flag
    return payload


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


FULL_PREFIX_THROUGH_EXECUTE_STARTED = [
    "MAIN_BOOT_STARTED",
    "MAIN_SAFETY_VALIDATED",
    "DB_READY_COMPLETED",
    "ORCHESTRATOR_INIT_ENTERED",
    "ORCHESTRATOR_TRADE_LOG_READY_COMPLETED",
    "ORCHESTRATOR_EVENT_LOG_REPAIR_COMPLETED",
    "ORCHESTRATOR_AUTH_WARM_CHECK_COMPLETED",
    "ORCHESTRATOR_RISK_STATE_INIT_COMPLETED",
    "ORCHESTRATOR_PREDICTOR_INIT_COMPLETED",
    "ORCHESTRATOR_EXECUTION_ENGINE_INIT_COMPLETED",
    "ORCHESTRATOR_EXECUTION_ROUTER_INIT_COMPLETED",
    "ORCHESTRATOR_TRADE_BUILDER_INIT_COMPLETED",
    "ORCHESTRATOR_WARMUP_STARTED",
    "ORCHESTRATOR_WARMUP_MARKET_DATA_STARTED",
    "MARKET_DATA_WARMUP_ENTERED",
    "MARKET_DATA_WARMUP_SEED_STARTED",
    "MARKET_DATA_WARMUP_SEED_COMPLETED",
    "MARKET_DATA_WARMUP_COMPLETED",
    "ORCHESTRATOR_WARMUP_MARKET_DATA_COMPLETED",
    "ORCHESTRATOR_WARMUP_COMPLETED",
    "ORCHESTRATOR_INIT_COMPLETED",
    "LIVE_MONITORING_CALLING",
    "LIVE_MONITORING_ENTERED",
    "ORCHESTRATOR_CYCLE_STARTED",
    "RUNTIME_STATUS_WRITE_ATTEMPTED",
    "FAST_ENGINE_EVALUATE_STARTED",
    "FAST_ENGINE_EVALUATE_COMPLETED",
    "FAST_ENGINE_EXECUTE_STARTED",
]


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


def test_startup_forensics_reports_fast_engine_evaluate_boundary(tmp_path):
    events = FULL_PREFIX_THROUGH_EXECUTE_STARTED[:25]
    log_dir = _write_evidence(tmp_path, events)

    evidence = load_runtime_startup_evidence(logs_path=log_dir)
    report = analyze_evidence(evidence)

    assert report.evidence_valid is True
    assert report.last_confirmed_event == "RUNTIME_STATUS_WRITE_ATTEMPTED"
    assert report.first_missing_event == "FAST_ENGINE_EVALUATE_STARTED"


def test_startup_forensics_reports_fast_engine_execute_boundary(tmp_path):
    events = FULL_PREFIX_THROUGH_EXECUTE_STARTED[:-1]
    log_dir = _write_evidence(tmp_path, events)

    evidence = load_runtime_startup_evidence(logs_path=log_dir)
    report = analyze_evidence(evidence)

    assert report.evidence_valid is True
    assert report.last_confirmed_event == "FAST_ENGINE_EVALUATE_COMPLETED"
    assert report.first_missing_event == "FAST_ENGINE_EXECUTE_STARTED"


def test_startup_forensics_reports_legacy_cycle_boundary(tmp_path):
    log_dir = _write_evidence(tmp_path, FULL_PREFIX_THROUGH_EXECUTE_STARTED)

    evidence = load_runtime_startup_evidence(logs_path=log_dir)
    report = analyze_evidence(evidence)

    assert report.evidence_valid is True
    assert report.last_confirmed_event == "FAST_ENGINE_EXECUTE_STARTED"
    assert report.first_missing_event == "FAST_ENGINE_LEGACY_CYCLE_STARTED"


def test_startup_forensics_reports_legacy_cycle_completion_boundary(tmp_path):
    events = [*FULL_PREFIX_THROUGH_EXECUTE_STARTED, "FAST_ENGINE_LEGACY_CYCLE_STARTED"]
    log_dir = _write_evidence(tmp_path, events)

    evidence = load_runtime_startup_evidence(logs_path=log_dir)
    report = analyze_evidence(evidence)

    assert report.evidence_valid is True
    assert report.last_confirmed_event == "FAST_ENGINE_LEGACY_CYCLE_STARTED"
    assert report.first_missing_event == "FAST_ENGINE_LEGACY_CYCLE_COMPLETED"


def test_startup_forensics_rejects_action_evidence(tmp_path):
    log_dir = _write_evidence(
        tmp_path,
        [
            "MAIN_BOOT_STARTED",
            _event("BROKER_ORDER_SUBMITTED", ts_epoch=1002.0, action_flag=True),
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


def test_startup_forensics_rejects_large_non_monotonic_events(tmp_path):
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


def test_startup_forensics_warns_on_minor_non_monotonic_events(tmp_path):
    log_dir = _write_evidence(
        tmp_path,
        [
            _event("MAIN_BOOT_STARTED", ts_epoch=1001.100),
            _event("MAIN_SAFETY_VALIDATED", ts_epoch=1001.099),
        ],
    )

    evidence = load_runtime_startup_evidence(logs_path=log_dir)

    assert evidence.valid is True
    assert any("non_monotonic_event_ts" in warning for warning in evidence.validation_warnings)


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
