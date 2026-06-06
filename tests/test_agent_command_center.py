from __future__ import annotations

import json
from pathlib import Path

from core.agents.command_center import run_agent_command_center


def _write_runtime(
    tmp_path: Path,
    *,
    feed_runtime: dict,
    depth_log: str = "",
    starvation_trace: dict | None = None,
    ranked_runtime: dict | None = None,
) -> tuple[Path, Path]:
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    if depth_log:
        (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(depth_log, encoding="utf-8")
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(json.dumps(feed_runtime), encoding="utf-8")
    if starvation_trace is not None:
        (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(json.dumps(starvation_trace), encoding="utf-8")
    if ranked_runtime is not None:
        (runtime_dir / "logs" / "ranked_pipeline_runtime_latest.json").write_text(json.dumps(ranked_runtime), encoding="utf-8")
    return runtime_dir, logs_dir


def _common_feed_runtime() -> dict:
    return {
        "runtime_state": "RECOVERY_BLOCKED",
        "feed_truth_state": "DEAD",
        "ws_connected": False,
        "process_restart_required": True,
        "ws_reconnect_allowed": False,
        "reconnect_blocked_reason": "ws1006_process_restart_required",
        "option_feed_block_reason_by_symbol": {"NIFTY": "NO_LIVE_OPTION_FEED"},
    }


def _common_starvation_trace() -> dict:
    return {"raw_candidate_count": 0, "phase2_input_candidate_count": 0}


def _common_ranked_runtime() -> dict:
    return {"ranked_candidate_count": 0, "executable_count": 0}


def test_agent_command_center_uses_domain_layer_not_agent_name(tmp_path: Path):
    runtime_dir, logs_dir = _write_runtime(
        tmp_path,
        feed_runtime=_common_feed_runtime(),
        depth_log="FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11\nConnection error: 1006\n",
        starvation_trace=_common_starvation_trace(),
        ranked_runtime=_common_ranked_runtime(),
    )

    report = run_agent_command_center(runtime_dir=runtime_dir, logs_dir=logs_dir, out_dir=runtime_dir / "agent_reports")
    payload = report.to_dict()
    assert payload["first_blocker_layer"] in {"FEED_STABILITY", "FEED_TRUTH"}
    assert payload["first_blocker_layer"] != "live_rca"
    assert payload["first_blocker_layer"] != "candidate_supply"
    assert payload["first_blocker_layer"] != "phase2_ranking_truth"
    assert payload["next_action_type"] == "FIX_FEED_LIFECYCLE"
    assert payload["confidence"] in {"HIGH", "MEDIUM"}
    assert "stale-option" in payload["next_pr_recommendation"].lower()
    assert "subscription" in payload["next_pr_recommendation"].lower()
    assert "feed lifecycle" in payload["root_cause_summary"].lower()


def test_feed_blocker_outranks_candidate_supply_and_phase2(tmp_path: Path):
    runtime_dir, logs_dir = _write_runtime(
        tmp_path,
        feed_runtime=_common_feed_runtime(),
        depth_log="FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11\nConnection error: 1006\n",
        starvation_trace=_common_starvation_trace(),
        ranked_runtime=_common_ranked_runtime(),
    )

    report = run_agent_command_center(runtime_dir=runtime_dir, logs_dir=logs_dir, out_dir=runtime_dir / "agent_reports")
    payload = report.to_dict()
    assert payload["first_blocker_layer"] in {"FEED_STABILITY", "FEED_TRUTH"}
    assert payload["first_blocker_layer"] != "CANDIDATE_SUPPLY"
    assert payload["first_blocker_layer"] != "PHASE2_RANKING"
    assert payload["what_is_not_root_cause"]
    assert any("candidate supply" in item.lower() for item in payload["what_is_not_root_cause"])
    assert any("phase2" in item.lower() for item in payload["what_is_not_root_cause"])
    assert payload["downstream_impact"]


def test_report_includes_next_action_type_and_markdown_headings(tmp_path: Path):
    runtime_dir, logs_dir = _write_runtime(
        tmp_path,
        feed_runtime=_common_feed_runtime(),
        depth_log="FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11\nConnection error: 1006\n",
        starvation_trace=_common_starvation_trace(),
        ranked_runtime=_common_ranked_runtime(),
    )

    report = run_agent_command_center(runtime_dir=runtime_dir, logs_dir=logs_dir, out_dir=runtime_dir / "agent_reports")
    payload = report.to_dict()
    md = (runtime_dir / "agent_reports" / "agent_command_center_latest.md").read_text(encoding="utf-8")
    assert payload["next_action_type"] == "FIX_FEED_LIFECYCLE"
    assert payload["first_failing_event"] in {"FEED_REBALANCE_APPLIED", "CONNECTION_ERROR:1006"}
    assert payload["downstream_impact"]
    assert "# What happened?" in md
    assert "# Why this is first" in md
    assert "# Evidence" in md
    assert "# What is not root cause yet" in md
    assert "FEED_STABILITY" in md or "FEED_TRUTH" in md


def test_live_rca_unknown_cannot_override_feed_stability_evidence(tmp_path: Path):
    runtime_dir, logs_dir = _write_runtime(
        tmp_path,
        feed_runtime=_common_feed_runtime(),
        depth_log="FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11\nConnection error: 1006\n",
        starvation_trace=_common_starvation_trace(),
        ranked_runtime=_common_ranked_runtime(),
    )

    report = run_agent_command_center(runtime_dir=runtime_dir, logs_dir=logs_dir, out_dir=runtime_dir / "agent_reports")
    payload = report.to_dict()
    assert payload["first_blocker_layer"] in {"FEED_STABILITY", "FEED_TRUTH"}
    assert payload["first_blocker_layer"] != "AUTH"
    assert payload["next_action_type"] == "FIX_FEED_LIFECYCLE"


def test_feed_and_phase2_downstream_blocks_do_not_beat_feed_stability(tmp_path: Path):
    runtime_dir, logs_dir = _write_runtime(
        tmp_path,
        feed_runtime=_common_feed_runtime(),
        depth_log="FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11\nConnection error: 1006\n",
        starvation_trace=_common_starvation_trace(),
        ranked_runtime=_common_ranked_runtime(),
    )

    report = run_agent_command_center(runtime_dir=runtime_dir, logs_dir=logs_dir, out_dir=runtime_dir / "agent_reports")
    payload = report.to_dict()
    assert payload["first_blocker_layer"] in {"FEED_STABILITY", "FEED_TRUTH"}
    assert payload["first_blocker_layer"] != "CANDIDATE_SUPPLY"
    assert payload["first_blocker_layer"] != "PHASE2_RANKING"
    assert payload["next_action_type"] == "FIX_FEED_LIFECYCLE"


def test_feed_truth_dead_uses_live_rca_findings_not_code_attribute(tmp_path: Path):
    runtime_dir, logs_dir = _write_runtime(
        tmp_path,
        feed_runtime={
            "runtime_state": "DEAD",
            "feed_truth_state": "DEAD",
            "ws_connected": False,
            "process_restart_required": False,
            "ws_reconnect_allowed": False,
            "option_feed_block_reason_by_symbol": {"NIFTY": "NO_LIVE_OPTION_FEED"},
        },
        depth_log="",
        starvation_trace={"raw_candidate_count": 0, "phase2_input_candidate_count": 0},
        ranked_runtime={"ranked_candidate_count": 0, "executable_count": 0},
    )

    report = run_agent_command_center(runtime_dir=runtime_dir, logs_dir=logs_dir, out_dir=runtime_dir / "agent_reports")
    payload = report.to_dict()
    assert payload["first_blocker_layer"] == "FEED_TRUTH"
    assert payload["next_action_type"] == "FIX_FEED_TRUTH"
    assert payload["first_failing_event"] == "FEED_TRUTH_DEAD"


def test_command_center_markdown_does_not_recommend_auth_first_for_feed_churn(tmp_path: Path):
    runtime_dir, logs_dir = _write_runtime(
        tmp_path,
        feed_runtime=_common_feed_runtime(),
        depth_log="FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11\nConnection error: 1006\n",
        starvation_trace=_common_starvation_trace(),
        ranked_runtime=_common_ranked_runtime(),
    )

    run_agent_command_center(runtime_dir=runtime_dir, logs_dir=logs_dir, out_dir=runtime_dir / "agent_reports")
    md = (runtime_dir / "agent_reports" / "agent_command_center_latest.md").read_text(encoding="utf-8")
    assert "Investigate auth_failure first" not in md
