from __future__ import annotations

import json
from pathlib import Path

from core.agents.feed_stability_agent import analyze_feed_stability


def test_feed_stability_agent_flags_overreactive_mutation(tmp_path: Path):
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
                "runtime_state": "RUNNING",
                "ws_connected": True,
                "option_ticks_received_count_by_symbol": {"BANKNIFTY": 19, "NIFTY": 19},
                "option_tokens_subscribed_count_by_symbol": {"BANKNIFTY": 20, "NIFTY": 20},
                "option_feed_block_reason_by_symbol": {"BANKNIFTY": "OK", "NIFTY": "OK"},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_feed_stability(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "WARN"
    assert payload["metrics"]["max_subscribe_count"] == 12
    assert payload["metrics"]["fresh_ratio_min"] > 0.90
    assert payload["read_only"] is True
    assert payload["broker_api_called"] is False


def test_feed_stability_agent_parses_json_watchdog_lines(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                '{"event": "FEED_REBALANCE_APPLIED", "subscribe_count": 25, "unsubscribe_count": 1, "fresh_ratio": 0.93, "stale_count": 3}',
                '{"event": "FEED_OPTION_PRUNE_REFRESH", "fresh_ratio": 0.98, "stale_count": 1}',
                '{"event": "FEED_WS_PROCESS_RESTART_REQUIRED", "code": 1006}',
            ]
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "runtime_state": "RECOVERY_BLOCKED",
                "ws_connected": False,
                "option_ticks_received_count_by_symbol": {"BANKNIFTY": 24, "NIFTY": 24},
                "option_tokens_subscribed_count_by_symbol": {"BANKNIFTY": 25, "NIFTY": 25},
                "option_feed_block_reason_by_symbol": {"BANKNIFTY": "NO_LIVE_OPTION_FEED", "NIFTY": "NO_LIVE_OPTION_FEED"},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_feed_stability(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] in {"WARN", "BLOCKER"}
    assert payload["metrics"]["max_subscribe_count"] == 25
    assert payload["metrics"]["large_rebalance_count"] >= 1
    assert payload["metrics"]["ws1006_count"] >= 1
    assert payload["metrics"]["fresh_ratio_min"] > 0.90
    assert payload["metrics"]["stale_count_max"] >= 1
