from __future__ import annotations

import json

from core.paper_trading_runbook_command import (
    RUNBOOK_BLOCKED,
    RUNBOOK_READY,
    build_paper_trading_runbook_report,
)
from scripts.paper_trading_runbook import main, run_command


def _snapshot(**overrides):
    payload = {
        "session_id": "paper-session-1",
        "read_only": True,
        "is_order_action": False,
        "append": False,
        "broker_order_action": False,
        "live_order_action": False,
        "feed_uptime_pct": 99.5,
        "stale_feed_duration_sec": 10.0,
        "ws_disconnect_count": 1,
        "restart_count": 0,
        "crash_loop_detected": False,
        "evidence_complete": True,
        "candidate_count": 20,
        "paper_order_count": 3,
        "paper_fill_count": 2,
        "paper_rejection_count": 1,
        "fallback_paper_fill_count": 0,
        "stale_feed_paper_fill_count": 0,
        "unresolved_contract_paper_fill_count": 0,
        "missing_evidence_trade_count": 0,
        "realized_pnl": 125.5,
        "max_drawdown": -40.0,
        "blockers": [],
        "warnings": [],
    }
    payload.update(overrides)
    return payload


def test_clean_session_snapshot_builds_ready_runbook_report():
    report = build_paper_trading_runbook_report(_snapshot())

    assert report.state == RUNBOOK_READY
    assert report.read_only is True
    assert report.is_order_action is False
    assert report.append is False
    assert report.broker_order_action is False
    assert report.live_order_action is False
    assert report.session_id == "paper-session-1"
    assert report.gate_state == "SESSION_GATE_PASS"
    assert report.evidence_complete is True
    assert report.paper_order_count == 3
    assert report.paper_fill_count == 2
    assert report.blockers == ()
    assert "Review the full-session paper gate report." in report.next_actions


def test_failed_gate_blocks_runbook_report():
    report = build_paper_trading_runbook_report(
        _snapshot(
            fallback_paper_fill_count=1,
            stale_feed_paper_fill_count=1,
            unresolved_contract_paper_fill_count=1,
            missing_evidence_trade_count=1,
        )
    )

    assert report.state == RUNBOOK_BLOCKED
    assert "PAPER_SESSION_GATE_NOT_PASS" in report.blockers
    assert "FALLBACK_PAPER_FILLS_PRESENT" in report.blockers
    assert "STALE_FEED_PAPER_FILLS_PRESENT" in report.blockers
    assert "UNRESOLVED_CONTRACT_PAPER_FILLS_PRESENT" in report.blockers
    assert "MISSING_EVIDENCE_TRADES_PRESENT" in report.blockers


def test_unsafe_snapshot_flags_block_runbook_report():
    report = build_paper_trading_runbook_report(
        _snapshot(
            broker_order_action=True,
            live_order_action=True,
            is_order_action=True,
            append=True,
        )
    )

    assert report.state == RUNBOOK_BLOCKED
    assert "SESSION_SNAPSHOT_BROKER_ORDER_ACTION_REJECTED" in report.blockers
    assert "SESSION_SNAPSHOT_LIVE_ORDER_ACTION_REJECTED" in report.blockers
    assert "SESSION_SNAPSHOT_ORDER_ACTION_REJECTED" in report.blockers
    assert "SESSION_SNAPSHOT_APPEND_TRUE_REJECTED" in report.blockers


def test_to_dict_is_json_friendly_and_stable():
    payload = build_paper_trading_runbook_report(_snapshot()).to_dict()

    assert payload["schema_version"] == 1
    assert payload["state"] == RUNBOOK_READY
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
    assert payload["append"] is False
    assert payload["broker_order_action"] is False
    assert payload["live_order_action"] is False
    assert payload["gate_report"]["state"] == "SESSION_GATE_PASS"
    assert payload["metadata"]["runbook_command"] == "paper_trading_runbook_command_v1"
    assert payload["metadata"]["scope"] == "read_only_no_runtime_start_no_broker_calls_no_order_mutation_no_file_io"


def test_cli_run_command_reads_snapshot_and_returns_report(tmp_path):
    path = tmp_path / "session.json"
    path.write_text(json.dumps(_snapshot()), encoding="utf-8")

    payload = run_command(path)

    assert payload["state"] == RUNBOOK_READY
    assert payload["session_id"] == "paper-session-1"


def test_cli_main_returns_zero_for_ready_report(tmp_path, monkeypatch, capsys):
    path = tmp_path / "session.json"
    path.write_text(json.dumps(_snapshot()), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["paper_trading_runbook.py", "--session-snapshot", str(path)])

    exit_code = main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["state"] == RUNBOOK_READY


def test_cli_main_returns_blocked_exit_for_failed_gate(tmp_path, monkeypatch, capsys):
    path = tmp_path / "session.json"
    path.write_text(json.dumps(_snapshot(evidence_complete=False)), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["paper_trading_runbook.py", "--session-snapshot", str(path)])

    exit_code = main()
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert output["state"] == RUNBOOK_BLOCKED
    assert "PAPER_SESSION_EVIDENCE_INCOMPLETE" in output["blockers"]
