from __future__ import annotations

import json
from pathlib import Path

from core.agents.live_rca_agent import analyze_live_rca


def test_live_rca_agent_identifies_subscription_churn_first(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                "FEED_ON_CONNECT_SUBSCRIBE symbols=3",
                "FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11",
                "Connection error: 1006 - connection was closed uncleanly",
                "kite_ws_error code=1006 reason=connection was closed uncleanly",
                "PHASE2: No input candidates for phase2 raw_count=0",
            ]
        )
        + "\n",
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

    report = analyze_live_rca(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["first_failing_event"] == "FEED_REBALANCE_APPLIED"
    assert payload["metrics"]["feed_rebalance_applied_count"] == 1
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False
