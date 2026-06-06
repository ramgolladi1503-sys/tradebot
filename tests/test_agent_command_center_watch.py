from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from core.agents.command_center import run_agent_command_center
from scripts import run_tradebot_agent_command_center as command_center_script


def _write_minimal_runtime(tmp_path: Path) -> tuple[Path, Path]:
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "runtime_state": "RUNNING",
                "feed_truth_state": "LIVE",
                "ws_connected": True,
                "process_restart_required": False,
                "ws_reconnect_allowed": True,
                "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
            }
        ),
        encoding="utf-8",
    )
    return runtime_dir, logs_dir


def _fake_report() -> SimpleNamespace:
    return SimpleNamespace(
        root_cause_summary="Feed lifecycle churn and websocket recovery state are the first observable blocker.",
        first_blocker_layer="FEED_STABILITY",
        next_pr_recommendation="Feed Lifecycle Stabilization — keep dead-WS mutation blocked.",
    )


def _fake_command_center_writer(*, out_dir: Path, **_: object) -> SimpleNamespace:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_order_allowed": False,
        "no_order_action": True,
    }
    (out_dir / "agent_command_center_latest.json").write_text(json.dumps(payload), encoding="utf-8")
    (out_dir / "agent_command_center_latest.md").write_text("# Tradebot Agent Command Center\n", encoding="utf-8")
    return _fake_report()


def test_watch_once_runs_exactly_one_iteration_and_copies_latest(tmp_path: Path, monkeypatch) -> None:
    runtime_dir, logs_dir = _write_minimal_runtime(tmp_path)
    output_root = tmp_path / "reports"
    run_root = output_root / "runs"
    calls: list[Path] = []

    def fake_run_agent_command_center(*, out_dir: Path, **kwargs: object) -> SimpleNamespace:
        calls.append(out_dir)
        return _fake_command_center_writer(out_dir=out_dir, **kwargs)

    monkeypatch.setattr(command_center_script, "run_agent_command_center", fake_run_agent_command_center)
    exit_code = command_center_script.main(
        [
            "--runtime-dir",
            str(runtime_dir),
            "--logs-dir",
            str(logs_dir),
            "--out-dir",
            str(output_root),
            "--run-dir",
            str(run_root),
            "--run-id",
            "watch-once-test",
            "--watch",
            "--once",
            "--copy-latest",
            "true",
        ]
    )

    session_dir = run_root / "watch-once-test"
    assert exit_code == 0
    assert calls == [session_dir]
    assert session_dir.exists()
    assert (session_dir / "agent_command_center_latest.json").exists()
    assert (output_root / "agent_command_center_latest.json").exists()
    assert (output_root / "agent_command_center_latest.md").exists()
    assert json.loads((output_root / "agent_command_center_latest.json").read_text(encoding="utf-8"))["read_only"] is True


def test_run_id_and_run_dir_create_per_run_directory(tmp_path: Path, monkeypatch) -> None:
    runtime_dir, logs_dir = _write_minimal_runtime(tmp_path)
    output_root = tmp_path / "reports"
    run_root = tmp_path / "custom-runs"
    seen_session_dirs: list[Path] = []

    def fake_run_agent_command_center(*, out_dir: Path, **kwargs: object) -> SimpleNamespace:
        seen_session_dirs.append(out_dir)
        return _fake_command_center_writer(out_dir=out_dir, **kwargs)

    monkeypatch.setattr(command_center_script, "run_agent_command_center", fake_run_agent_command_center)
    exit_code = command_center_script.main(
        [
            "--runtime-dir",
            str(runtime_dir),
            "--logs-dir",
            str(logs_dir),
            "--out-dir",
            str(output_root),
            "--run-dir",
            str(run_root),
            "--run-id",
            "custom-run-id",
        ]
    )

    session_dir = run_root / "custom-run-id"
    assert exit_code == 0
    assert seen_session_dirs == [session_dir]
    assert session_dir.exists()
    assert (session_dir / "agent_command_center_latest.json").exists()
    assert (output_root / "agent_command_center_latest.json").exists()


def test_copy_latest_can_be_disabled(tmp_path: Path, monkeypatch) -> None:
    runtime_dir, logs_dir = _write_minimal_runtime(tmp_path)
    output_root = tmp_path / "reports"
    run_root = output_root / "runs"

    def fake_run_agent_command_center(*, out_dir: Path, **kwargs: object) -> SimpleNamespace:
        return _fake_command_center_writer(out_dir=out_dir, **kwargs)

    monkeypatch.setattr(command_center_script, "run_agent_command_center", fake_run_agent_command_center)
    exit_code = command_center_script.main(
        [
            "--runtime-dir",
            str(runtime_dir),
            "--logs-dir",
            str(logs_dir),
            "--out-dir",
            str(output_root),
            "--run-dir",
            str(run_root),
            "--run-id",
            "copy-disabled",
            "--copy-latest",
            "false",
        ]
    )

    assert exit_code == 0
    assert (run_root / "copy-disabled" / "agent_command_center_latest.json").exists()
    assert not (output_root / "agent_command_center_latest.json").exists()
    assert not (output_root / "agent_command_center_latest.md").exists()


def test_missing_logs_do_not_crash_watch_mode(tmp_path: Path, monkeypatch) -> None:
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    output_root = tmp_path / "reports"
    run_root = output_root / "runs"

    def fake_run_agent_command_center(*, out_dir: Path, **kwargs: object) -> SimpleNamespace:
        out_dir.mkdir(parents=True, exist_ok=True)
        return _fake_report()

    monkeypatch.setattr(command_center_script, "run_agent_command_center", fake_run_agent_command_center)
    exit_code = command_center_script.main(
        [
            "--runtime-dir",
            str(runtime_dir),
            "--logs-dir",
            str(logs_dir),
            "--out-dir",
            str(output_root),
            "--run-dir",
            str(run_root),
            "--run-id",
            "missing-logs",
            "--watch",
            "--once",
        ]
    )

    assert exit_code == 0
    assert (run_root / "missing-logs").exists()


def test_run_agent_command_center_respects_format_selection(tmp_path: Path) -> None:
    runtime_dir, logs_dir = _write_minimal_runtime(tmp_path)
    json_out = tmp_path / "json-out"
    md_out = tmp_path / "md-out"

    run_agent_command_center(runtime_dir=runtime_dir, logs_dir=logs_dir, out_dir=json_out, fmt="json")
    assert (json_out / "agent_command_center_latest.json").exists()
    assert not (json_out / "agent_command_center_latest.md").exists()

    run_agent_command_center(runtime_dir=runtime_dir, logs_dir=logs_dir, out_dir=md_out, fmt="markdown")
    assert not (md_out / "agent_command_center_latest.json").exists()
    assert (md_out / "agent_command_center_latest.md").exists()
