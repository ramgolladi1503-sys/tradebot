from __future__ import annotations

import json
from pathlib import Path

from core.agents.candidate_supply_agent import analyze_candidate_supply


def test_candidate_supply_agent_flags_empty_supply(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps({"raw_candidate_count": 0, "phase2_input_candidate_count": 0, "top_blockers": {"RISK_HALT": 1}}),
        encoding="utf-8",
    )

    report = analyze_candidate_supply(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["metrics"]["raw_candidate_count"] == 0
    assert payload["read_only"] is True
    assert payload["no_order_action"] is True
