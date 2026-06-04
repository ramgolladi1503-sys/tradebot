from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.feed_truth_audit import build_feed_truth_audit_report, write_feed_truth_audit_report


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _log_line(event: str, payload: dict[str, object]) -> str:
    return f"2026-06-05 {event} {json.dumps(payload, sort_keys=True)}"


def _runtime_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "runtime_state": "RECOVERY_BLOCKED",
        "ws_connected": False,
        "feed_truth_state": "RECOVERY_BLOCKED",
        "feed_truth_reason_code": "WS1006_PROCESS_RESTART_REQUIRED",
        "quote_health": {"state": "BLOCKED", "stale_reasons": ["RECOVERY_BLOCKED"]},
        "latency_guard": {
            "latency_guard_triggered": True,
            "latency_guard_action": "DEGRADE_EXIT_ONLY",
            "latency_guard_reason": "LATENCY_GUARD_DEGRADE_EXIT_ONLY",
            "latency_guard_metric": "cycle_latency_ms",
            "latency_guard_value": 123.0,
            "latency_guard_threshold": 100.0,
        },
        "reconnect_blocked_reason": "ws1006_process_restart_required",
        "recovery_action": "process_restart_required",
    }
    payload.update(overrides)
    return payload


def test_blocks_reportable_executable_under_recovery_blocked(tmp_path: Path) -> None:
    log_file = _write(
        tmp_path / "live_console.log",
        "\n".join(
            [
                _log_line(
                    "TB_TOP_EXECUTABLE_CANDIDATE",
                    {
                        "event": "TB_TOP_EXECUTABLE_CANDIDATE",
                        "symbol": "SENSEX",
                        "trade_id": "T-1",
                        "candidate_status": "executable",
                        "execution_status": "executable",
                        "execution_entry_status": "executable",
                        "permission": "EXECUTE",
                        "final_action": "EXECUTE",
                        "readiness": "READY",
                        "execution_allowed": True,
                        "eligible_for_execution": True,
                        "reportable_executable": True,
                        "visibility_bucket": "executable",
                        "execution_truth_blockers": ["WS_DISCONNECTED", "RECOVERY_BLOCKED"],
                    },
                )
            ]
        ),
    )
    runtime_file = _write(tmp_path / "feed_runtime_latest.json", json.dumps(_runtime_payload(), sort_keys=True))

    report = build_feed_truth_audit_report(log_file=log_file, runtime_file=runtime_file)

    assert report["verdict"] == "FAIL"
    codes = {item["code"] for item in report["contradictions"]}
    assert "unsafe_reportable_executable_under_blocked_feedtruth" in codes
    assert "top_executable_emitted_under_blocked_truth" in codes
    assert report["counts"]["reportable_executable_count"] == 1


def test_rejects_recovered_fallback_reportable_executable(tmp_path: Path) -> None:
    log_file = _write(
        tmp_path / "live_console.log",
        "\n".join(
            [
                _log_line(
                    "TB_TOP_EXECUTABLE_CANDIDATE",
                    {
                        "event": "TB_TOP_EXECUTABLE_CANDIDATE",
                        "symbol": "NIFTY",
                        "trade_id": "T-2",
                        "candidate_status": "executable",
                        "execution_status": "executable",
                        "execution_entry_status": "executable",
                        "permission": "EXECUTE",
                        "final_action": "EXECUTE",
                        "readiness": "READY",
                        "execution_allowed": True,
                        "eligible_for_execution": True,
                        "reportable_executable": True,
                        "source": "recovered_quote",
                    },
                )
            ]
        ),
    )
    runtime_file = _write(tmp_path / "feed_runtime_latest.json", json.dumps(_runtime_payload(ws_connected=True), sort_keys=True))

    report = build_feed_truth_audit_report(log_file=log_file, runtime_file=runtime_file)

    assert report["verdict"] == "FAIL"
    codes = {item["code"] for item in report["contradictions"]}
    assert "fallback_quote_marked_executable" in codes


def test_rejects_reportable_executable_when_runtime_feed_snapshot_is_not_fresh(tmp_path: Path) -> None:
    log_file = _write(
        tmp_path / "live_console.log",
        _log_line(
            "TB_TOP_EXECUTABLE_CANDIDATE",
            {
                "event": "TB_TOP_EXECUTABLE_CANDIDATE",
                "symbol": "BANKNIFTY",
                "trade_id": "T-2",
                "candidate_status": "executable",
                "execution_status": "executable",
                "execution_entry_status": "executable",
                "permission": "EXECUTE",
                "final_action": "EXECUTE",
                "readiness": "READY",
                "execution_allowed": True,
                "eligible_for_execution": True,
                "reportable_executable": True,
                "execution_truth_blockers": ["UNKNOWN"],
            },
        ),
    )
    runtime_file = _write(
        tmp_path / "feed_runtime_latest.json",
        json.dumps(
            _runtime_payload(
                runtime_state="RUNNING",
                ws_connected=True,
                feed_truth_reason_code="UNKNOWN",
                quote_health={"state": "OK", "stale_reasons": []},
                feed_fresh=False,
                underlying_tick_fresh=True,
                option_tick_fresh=False,
                depth_fresh=False,
                stale_reason=["option_tick_stale_or_missing"],
            ),
            sort_keys=True,
        ),
    )

    report = build_feed_truth_audit_report(log_file=log_file, runtime_file=runtime_file)

    assert report["verdict"] == "FAIL"
    codes = {item["code"] for item in report["contradictions"]}
    assert "unsafe_reportable_executable_under_blocked_feedtruth" in codes or "reportable_executable_under_blocked_truth" in codes


def test_rejects_latency_guard_ok_used_as_blocker(tmp_path: Path) -> None:
    log_file = _write(
        tmp_path / "live_console.log",
        _log_line(
            "TB_TOP_BLOCKED_CANDIDATE",
            {
                "event": "TB_TOP_BLOCKED_CANDIDATE",
                "symbol": "BANKNIFTY",
                "trade_id": "T-3",
                "candidate_status": "blocked",
                "execution_status": "blocked",
                "execution_entry_status": "executable",
                "permission": "BLOCK",
                "final_action": "BLOCK",
                "readiness": "BLOCKED",
                "execution_allowed": False,
                "eligible_for_execution": False,
                "reportable_executable": False,
                "execution_truth_blockers": ["LATENCY_GUARD_OK"],
            },
        ),
    )
    runtime_file = _write(tmp_path / "feed_runtime_latest.json", json.dumps(_runtime_payload(ws_connected=True), sort_keys=True))

    report = build_feed_truth_audit_report(log_file=log_file, runtime_file=runtime_file)

    assert report["verdict"] == "FAIL"
    codes = {item["code"] for item in report["contradictions"]}
    assert "ok_marker_used_as_blocker" in codes


def test_rejects_duplicate_blockers_and_keeps_order(tmp_path: Path) -> None:
    log_file = _write(
        tmp_path / "live_console.log",
        _log_line(
            "TB_TOP_BLOCKED_CANDIDATE",
            {
                "event": "TB_TOP_BLOCKED_CANDIDATE",
                "symbol": "SENSEX",
                "trade_id": "T-4",
                "candidate_status": "blocked",
                "execution_status": "blocked",
                "execution_entry_status": "blocked",
                "permission": "BLOCK",
                "final_action": "BLOCK",
                "readiness": "BLOCKED",
                "execution_allowed": False,
                "eligible_for_execution": False,
                "reportable_executable": False,
                "execution_truth_blockers": ["WS_DISCONNECTED", "WS_DISCONNECTED", "STALE_OPTION_LTP"],
            },
        ),
    )
    runtime_file = _write(tmp_path / "feed_runtime_latest.json", json.dumps(_runtime_payload(), sort_keys=True))

    report = build_feed_truth_audit_report(log_file=log_file, runtime_file=runtime_file)

    codes = {item["code"] for item in report["contradictions"]}
    assert "duplicate_blockers" in codes
    assert report["blocker_histogram"]["WS_DISCONNECTED"] >= 1


def test_warns_when_quote_health_looks_ok_but_feedtruth_blocked(tmp_path: Path) -> None:
    log_file = _write(
        tmp_path / "live_console.log",
        _log_line(
            "TB_TOP_EXECUTABLE_CANDIDATE",
            {
                "event": "TB_TOP_EXECUTABLE_CANDIDATE",
                "symbol": "NIFTY",
                "trade_id": "T-5",
                "candidate_status": "executable",
                "execution_status": "executable",
                "execution_entry_status": "executable",
                "permission": "EXECUTE",
                "final_action": "EXECUTE",
                "readiness": "READY",
                "execution_allowed": True,
                "eligible_for_execution": True,
                "reportable_executable": True,
                "execution_truth_blockers": ["RECOVERY_BLOCKED"],
                "quote_health_state": "OK",
            },
        ),
    )
    runtime_file = _write(tmp_path / "feed_runtime_latest.json", json.dumps(_runtime_payload(), sort_keys=True))

    report = build_feed_truth_audit_report(log_file=log_file, runtime_file=runtime_file)

    warning_codes = {item["code"] for item in report["warnings"]}
    assert "quote_health_ok_contradicts_blocked_feedtruth" in warning_codes


def test_warns_when_feed_diagnostics_exist_but_no_candidate_events(tmp_path: Path) -> None:
    log_file = _write(
        tmp_path / "live_console.log",
        _log_line(
            "REGIME_UNSTABLE_DIAGNOSTIC",
            {
                "event": "REGIME_UNSTABLE_DIAGNOSTIC",
                "feed_health": {"runtime_state": "RECOVERY_BLOCKED", "ws_connected": False},
                "quote_health": {"state": "OK"},
            },
        ),
    )
    runtime_file = _write(tmp_path / "feed_runtime_latest.json", json.dumps(_runtime_payload(), sort_keys=True))

    report = build_feed_truth_audit_report(log_file=log_file, runtime_file=runtime_file)

    warning_codes = {item["code"] for item in report["warnings"]}
    assert "no_candidate_events_but_feed_diagnostics_exist" in warning_codes


def test_cli_writes_json_report_and_supports_markdown(tmp_path: Path) -> None:
    log_file = _write(
        tmp_path / "live_console.log",
        _log_line(
            "TB_TOP_BLOCKED_CANDIDATE",
            {
                "event": "TB_TOP_BLOCKED_CANDIDATE",
                "symbol": "NIFTY",
                "trade_id": "T-6",
                "candidate_status": "blocked",
                "execution_status": "blocked",
                "execution_entry_status": "blocked",
                    "permission": "BLOCK",
                    "final_action": "BLOCK",
                    "readiness": "BLOCKED",
                    "execution_allowed": False,
                    "eligible_for_execution": False,
                    "reportable_executable": True,
                    "execution_truth_blockers": ["WS_DISCONNECTED"],
                },
            ),
        )
    runtime_file = _write(tmp_path / "feed_runtime_latest.json", json.dumps(_runtime_payload(), sort_keys=True))
    out = tmp_path / "audit.json"
    markdown_out = tmp_path / "audit.md"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/audit_feed_truth_consistency.py",
            "--log-file",
            str(log_file),
            "--runtime-file",
            str(runtime_file),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 1
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["read_only"] is True
    assert report["is_order_action"] is False
    assert report["verdict"] == "FAIL"

    completed_md = subprocess.run(
        [
            sys.executable,
            "scripts/audit_feed_truth_consistency.py",
            "--log-file",
            str(log_file),
            "--runtime-file",
            str(runtime_file),
            "--out",
            str(markdown_out),
            "--format",
            "markdown",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed_md.returncode == 1
    assert markdown_out.read_text(encoding="utf-8").startswith("# FeedTruth Audit Report")


def test_cli_strict_fails_closed_when_runtime_input_missing(tmp_path: Path) -> None:
    log_file = _write(
        tmp_path / "live_console.log",
        _log_line(
            "REGIME_UNSTABLE_DIAGNOSTIC",
            {
                "event": "REGIME_UNSTABLE_DIAGNOSTIC",
                "feed_health": {"runtime_state": "RECOVERY_BLOCKED", "ws_connected": False},
                "quote_health": {"state": "OK"},
            },
        ),
    )
    out = tmp_path / "strict.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/audit_feed_truth_consistency.py",
            "--log-file",
            str(log_file),
            "--runtime-file",
            str(tmp_path / "missing_runtime.json"),
            "--out",
            str(out),
            "--strict",
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["strict"] is True
    assert any(item["code"] == "missing_runtime_file" for item in payload["warnings"])


def test_default_mode_does_not_fail_when_one_source_is_missing(tmp_path: Path) -> None:
    runtime_file = _write(tmp_path / "feed_runtime_latest.json", json.dumps(_runtime_payload(), sort_keys=True))
    out = tmp_path / "default.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/audit_feed_truth_consistency.py",
            "--log-file",
            str(tmp_path / "missing.log"),
            "--runtime-file",
            str(runtime_file),
            "--out",
            str(out),
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["verdict"] in {"PASS", "WARN"}
    assert any(item["code"] == "missing_log_file" for item in payload["warnings"])
