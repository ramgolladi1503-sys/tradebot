from __future__ import annotations

import json
from pathlib import Path

from core.agents.command_center import run_agent_command_center


def test_agent_command_center_writes_all_reports(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11\n",
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "runtime_state": "RECOVERY_BLOCKED",
                "feed_truth_state": "DEAD",
                "ws_connected": False,
                "process_restart_required": True,
                "ws_reconnect_allowed": False,
                "option_feed_block_reason_by_symbol": {"NIFTY": "NO_LIVE_OPTION_FEED"},
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps({"raw_candidate_count": 0, "phase2_input_candidate_count": 0}),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "ranked_pipeline_runtime_latest.json").write_text(
        json.dumps({"ranked_candidate_count": 0, "executable_count": 0}),
        encoding="utf-8",
    )

    report = run_agent_command_center(
        runtime_dir=runtime_dir,
        logs_dir=logs_dir,
        out_dir=runtime_dir / "agent_reports",
        changed_paths_file=None,
        changed_paths=["tests/test_agent_command_center.py"],
        offline_fixtures=Path("tests/fixtures/candidate_outcomes"),
    )
    payload = report.to_dict()
    assert payload["first_blocker_layer"] == "live_rca"
    assert (runtime_dir / "agent_reports" / "agent_command_center_latest.json").exists()
    assert (runtime_dir / "agent_reports" / "live_rca_latest.json").exists()
    assert payload["safety_summary"]["read_only"] is True
