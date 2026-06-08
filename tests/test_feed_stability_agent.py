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


def test_feed_stability_agent_marks_dead_ws_mutation_as_blocker(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                '{"event": "FEED_REBALANCE_APPLIED", "subscribe_count": 25, "unsubscribe_count": 1, "source": "on_error", "ws_connected": false, "runtime_state": "RECOVERY_BLOCKED"}',
                '{"event": "FEED_REBALANCE_SKIPPED", "guard_reason": "ws_disconnected", "subscribe_count": 0, "unsubscribe_count": 0}',
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
                "option_ticks_received_count_by_symbol": {"BANKNIFTY": 24},
                "option_tokens_subscribed_count_by_symbol": {"BANKNIFTY": 25},
                "option_feed_block_reason_by_symbol": {"BANKNIFTY": "NO_LIVE_OPTION_FEED"},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_feed_stability(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["findings"][0]["code"] == "MUTATION_ON_DEAD_WS"
    assert payload["metrics"]["current_session_rebalance_applied_count"] == 1
    assert payload["metrics"]["current_session_rebalance_skipped_count"] == 1
    assert payload["metrics"]["current_session_mutation_on_dead_ws_count"] == 1
    assert payload["metrics"]["current_session_feed_ltp_stale_count"] >= 0
    assert payload["metrics"]["current_session_feed_depth_stale_count"] >= 0
    assert payload["metrics"]["current_session_slo_feed_stale_count"] >= 0


def test_feed_stability_agent_treats_skipped_rebalance_as_safety_positive(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        '{"event": "FEED_REBALANCE_SKIPPED", "guard_reason": "ws_disconnected", "subscribe_count": 0, "unsubscribe_count": 0}\n',
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "runtime_state": "RUNNING",
                "feed_truth_state": "LIVE",
                "ws_connected": True,
                "option_ticks_received_count_by_symbol": {"BANKNIFTY": 24},
                "option_tokens_subscribed_count_by_symbol": {"BANKNIFTY": 25},
                "option_feed_block_reason_by_symbol": {"BANKNIFTY": "OK"},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_feed_stability(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] in {"PASS", "WARN"}
    assert payload.get("first_failing_event") is None
    assert payload["findings"][0]["code"] != "MUTATION_ON_DEAD_WS"


def test_feed_stability_agent_reports_no_live_option_feed_after_subscribe(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                '{"event": "FEED_ON_CONNECT_SUBSCRIBE", "reason": "connect", "subscription_requested_by_symbol": {"NIFTY": 2}, "subscribed_option_tokens_count_by_symbol": {"NIFTY": 2}}',
                '{"event": "FEED_OPTION_VERIFY_BEGIN", "reason": "connect", "required_symbols": ["NIFTY"]}',
                '{"event": "FEED_OPTION_VERIFY_WAITING_TICKS", "reason": "connect"}',
                '{"event": "FEED_OPTION_VERIFY_FAILED", "reason": "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE", "missing_symbols": ["NIFTY"]}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "run_id": "run-current",
                "boot_epoch": 2000.0,
                "ts_epoch": 2001.0,
                "runtime_state": "RUNNING",
                "feed_truth_state": "DEAD",
                "ws_connected": True,
                "option_feed_verification": {
                    "state": "FAILED",
                    "failure_detail": "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE",
                    "reason": "connect",
                },
                "option_ticks_received_count_by_symbol": {"NIFTY": 0},
                "option_tokens_subscribed_count_by_symbol": {"NIFTY": 2},
                "option_feed_block_reason_by_symbol": {"NIFTY": "NO_LIVE_OPTION_FEED"},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_feed_stability(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["first_failing_event"] == "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE"
    assert payload["metrics"]["current_session_option_subscribe_count"] == 1
    assert payload["metrics"]["current_session_option_verify_begin_count"] == 1
    assert payload["metrics"]["current_session_option_verify_ok_count"] == 0
    assert payload["metrics"]["current_session_option_verify_failed_count"] == 1
    assert payload["metrics"]["current_session_no_live_option_feed_after_subscribe_count"] == 1


def test_feed_stability_agent_reports_option_ticks_verified_after_subscribe(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                '{"event": "FEED_ON_CONNECT_SUBSCRIBE", "reason": "connect", "subscription_requested_by_symbol": {"NIFTY": 2}, "subscribed_option_tokens_count_by_symbol": {"NIFTY": 2}}',
                '{"event": "FEED_OPTION_VERIFY_BEGIN", "reason": "connect", "required_symbols": ["NIFTY"]}',
                '{"event": "FEED_OPTION_VERIFY_WAITING_TICKS", "reason": "connect"}',
                '{"event": "FEED_OPTION_VERIFY_OK", "reason": "connect", "verified_symbols": ["NIFTY"]}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "run_id": "run-current",
                "boot_epoch": 2000.0,
                "ts_epoch": 2001.0,
                "runtime_state": "RUNNING",
                "feed_truth_state": "LIVE",
                "ws_connected": True,
                "option_feed_verification": {
                    "state": "OK",
                    "reason": "connect",
                    "verified_symbols": ["NIFTY"],
                },
                "option_ticks_received_count_by_symbol": {"NIFTY": 2},
                "option_tokens_subscribed_count_by_symbol": {"NIFTY": 2},
                "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_feed_stability(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] in {"PASS", "WARN"}
    assert payload["metrics"]["current_session_option_verify_ok_count"] == 1
    assert payload["metrics"]["current_session_option_verify_failed_count"] == 0


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


def test_feed_stability_agent_marks_stale_tail_churn_as_historical_when_current_feed_is_fresh(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                "ts_epoch=1500.0 boot_epoch=1000.0 run_id=run-old event=FEED_REBALANCE_APPLIED subscribe_count=12 unsubscribe_count=11",
                "ts_epoch=1500.5 boot_epoch=1000.0 run_id=run-old event=CONNECTION_ERROR code=1006",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "run_id": "run-current",
                "boot_epoch": 2000.0,
                "ts_epoch": 2001.0,
                "runtime_state": "RUNNING",
                "ws_connected": True,
                "feed_health_snapshot": {"N2_FEED_FRESH": {"ok": True}},
                "gate_status": {"N2_FEED_FRESH": {"ok": True}},
                "option_ticks_received_count_by_symbol": {"BANKNIFTY": 25},
                "option_tokens_subscribed_count_by_symbol": {"BANKNIFTY": 25},
                "option_feed_block_reason_by_symbol": {"BANKNIFTY": "OK"},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_feed_stability(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["metrics"]["current_session_feed_fresh"] is True
    assert payload["metrics"]["evidence_scope"] == "historical_tail"
    assert payload["metrics"]["stale_evidence_ignored_count"] >= 1
    assert payload["metrics"]["stale_evidence_reason"]


def test_feed_stability_agent_keeps_current_session_churn_as_current(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                "ts_epoch=2002.0 boot_epoch=2000.0 run_id=run-current event=FEED_REBALANCE_APPLIED subscribe_count=12 unsubscribe_count=11",
                "ts_epoch=2002.5 boot_epoch=2000.0 run_id=run-current event=CONNECTION_ERROR code=1006",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(
        json.dumps(
            {
                "run_id": "run-current",
                "boot_epoch": 2000.0,
                "ts_epoch": 2001.0,
                "runtime_state": "RUNNING",
                "ws_connected": True,
                "feed_health_snapshot": {"N2_FEED_FRESH": {"ok": True}},
                "gate_status": {"N2_FEED_FRESH": {"ok": True}},
                "option_ticks_received_count_by_symbol": {"BANKNIFTY": 25},
                "option_tokens_subscribed_count_by_symbol": {"BANKNIFTY": 25},
                "option_feed_block_reason_by_symbol": {"BANKNIFTY": "OK"},
            }
        ),
        encoding="utf-8",
    )

    report = analyze_feed_stability(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["metrics"]["current_session_feed_fresh"] is True
    assert payload["metrics"]["evidence_scope"] == "current_session"
    assert payload["metrics"]["stale_evidence_ignored_count"] == 0
