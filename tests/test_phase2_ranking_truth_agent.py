from __future__ import annotations

import json
from pathlib import Path

from core.agents.phase2_ranking_truth_agent import analyze_phase2_ranking_truth


def test_phase2_ranking_truth_agent_flags_hard_execution(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "ranked_pipeline_runtime_latest.json").write_text(
        json.dumps(
            {
                "phase2_state": "INPUT_DROPPED",
                "ranked_candidate_count": 4,
                "executable_count": 0,
                "phase2_drop_reason_counts": {"hard_execution": 4},
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps({"phase2_input_candidate_count": 4, "phase2_survivor_count": 0, "phase2_drop_counts": {"hard_execution": 4}}),
        encoding="utf-8",
    )

    report = analyze_phase2_ranking_truth(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["metrics"]["phase2_drop_reason_counts"]["hard_execution"] == 4
    assert payload["read_only"] is True
    assert payload["broker_api_called"] is False
