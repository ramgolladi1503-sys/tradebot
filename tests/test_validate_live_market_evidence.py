from __future__ import annotations

import json

from core.feed_staleness_observability import build_feed_staleness_report
from scripts.validate_live_market_evidence import (
    scan_run_log_for_fallback_executable_traces,
    validate_live_evidence,
)


def _report(**summary_overrides):
    summary = {
        "feed_ok": True,
        "ws_connected": True,
        "subscribed_option_tokens_count": 70,
        "visible_executable_count": 0,
        "recon_daemon_running": False,
        "suggestions_tail_rows": 2,
        "events_tail_rows": 1,
        "missing_runtime_files": [],
        "errored_runtime_files": {},
    }
    summary.update(summary_overrides)
    return {
        "schema_version": 1,
        "logs_dir": "/tmp/unit-live-validation",
        "read_only": True,
        "is_order_action": False,
        "summary": summary,
        "blocker_evidence": {"suggestions_tail_blocker_counts": {"REGIME_UNSTABLE": 1}},
        "status_counts": {"suggestions_tail_status_counts": {"queue_only": 2}},
    }


def test_clean_live_evidence_is_pass_candidate(monkeypatch):
    monkeypatch.setenv("ORDER_RECON_ENABLED", "false")

    result = validate_live_evidence(_report())

    assert result["verdict"] == "PASS_CANDIDATE"
    assert result["violations"] == []
    assert result["warnings"] == []
    assert result["summary"]["visible_executable_count"] == 0
    assert result["summary"]["recon_daemon_running"] is False


def test_missing_visible_executable_count_is_violation_not_warning(monkeypatch):
    monkeypatch.setenv("ORDER_RECON_ENABLED", "false")
    report = _report()
    report["summary"].pop("visible_executable_count")

    result = validate_live_evidence(report)

    assert result["verdict"] == "FAIL"
    assert "missing_summary_field:visible_executable_count" in result["violations"]
    assert "missing_summary_field:visible_executable_count" not in result["warnings"]


def test_recon_daemon_running_while_disabled_is_violation(monkeypatch):
    monkeypatch.setenv("ORDER_RECON_ENABLED", "false")

    result = validate_live_evidence(_report(recon_daemon_running=True))

    assert result["verdict"] == "FAIL"
    assert "order_recon_daemon_running_while_disabled" in result["violations"]


def test_recon_daemon_running_is_allowed_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("ORDER_RECON_ENABLED", "true")

    result = validate_live_evidence(_report(recon_daemon_running=True))

    assert "order_recon_daemon_running_while_disabled" not in result["violations"]


def test_feed_observability_extracts_recon_daemon_state(tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (logs_dir / "feed_runtime_latest.json").write_text(
        json.dumps({"feed_ok": True, "ws_connected": True, "subscribed_option_tokens_count": 70}),
        encoding="utf-8",
    )
    (logs_dir / "runtime_health_latest.json").write_text(json.dumps({}), encoding="utf-8")
    (logs_dir / "engine_cycle_status.json").write_text(
        json.dumps({"visible_executable_count": 0, "recon": {"daemon_running": True}}),
        encoding="utf-8",
    )
    (logs_dir / "suggestions_status.json").write_text(json.dumps({}), encoding="utf-8")

    report = build_feed_staleness_report(logs_dir)

    assert report["summary"]["recon_daemon_running"] is True


def test_fallback_contract_executable_trace_is_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("ORDER_RECON_ENABLED", "false")
    run_root = tmp_path / "run"
    logs_dir = run_root / "logs"
    logs_dir.mkdir(parents=True)
    (run_root / "run_live.log").write_text(
        "\n".join(
            [
                "2026 [-] CONTRACT_RESOLUTION_FALLBACK {'symbol': 'NIFTY', 'requested_strike': 23750.0, 'resolved_strike': 23700.0}",
                "2026 [-] TB_TOP_EXECUTABLE_CANDIDATE {'symbol': 'NIFTY', 'permission': 'EXECUTE', 'final_action': 'EXECUTE', 'execution_allowed': True}",
            ]
        ),
        encoding="utf-8",
    )

    traces = scan_run_log_for_fallback_executable_traces(logs_dir)
    result = validate_live_evidence(_report(), logs_dir=logs_dir)

    assert len(traces) == 1
    assert traces[0]["symbol"] == "NIFTY"
    assert traces[0]["fallback_line_number"] == 1
    assert result["verdict"] == "FAIL"
    assert "fallback_contract_reached_executable_trace" in result["violations"]
    assert result["fallback_executable_trace_count"] == 1


def test_fallback_contract_without_executable_trace_does_not_fail(tmp_path, monkeypatch):
    monkeypatch.setenv("ORDER_RECON_ENABLED", "false")
    run_root = tmp_path / "run"
    logs_dir = run_root / "logs"
    logs_dir.mkdir(parents=True)
    (run_root / "run_live.log").write_text(
        "\n".join(
            [
                "2026 [-] CONTRACT_RESOLUTION_FALLBACK {'symbol': 'NIFTY', 'requested_strike': 23750.0, 'resolved_strike': 23700.0}",
                "2026 [-] TB_TOP_ADVISORY_CANDIDATE {'symbol': 'NIFTY', 'permission': 'ADVISORY_ONLY', 'final_action': 'QUEUE_ONLY', 'execution_allowed': False}",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_live_evidence(_report(), logs_dir=logs_dir)

    assert result["verdict"] == "PASS_CANDIDATE"
    assert result["fallback_executable_trace_count"] == 0
