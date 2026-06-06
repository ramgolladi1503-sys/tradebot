from __future__ import annotations

import json
from pathlib import Path

from core.agents.safety_regression_gate_agent import analyze_safety_regression_gate


def test_safety_regression_gate_agent_blocks_forbidden_paths(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps({"runtime_state": "RECOVERY_BLOCKED", "ws_reconnect_allowed": False}),
        encoding="utf-8",
    )

    report = analyze_safety_regression_gate(
        runtime_dir=runtime_dir,
        logs_dir=logs_dir,
        changed_paths=["core/broker/reconciliation.py", "tests/test_agent_command_center.py"],
    )
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["metrics"]["forbidden_paths"] == ["core/broker/reconciliation.py"]
    assert payload["read_only"] is True
    assert payload["broker_api_called"] is False
