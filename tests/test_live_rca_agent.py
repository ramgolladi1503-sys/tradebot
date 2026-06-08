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
    assert payload["first_failing_event"] == "WS1006_PROCESS_RESTART_REQUIRED"
    assert payload["metrics"]["feed_rebalance_applied_count"] == 1
    assert payload["read_only"] is True
    assert payload["is_order_action"] is False


def test_live_rca_agent_ignores_generic_auth_text(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                "auth_runtime started and authenticated successfully",
                "authorization header present",
                "auth guard reset for test harness",
                "HTTP 401 returned by downstream service during unrelated replay",
                "FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11",
                "Connection error: 1006 - connection was closed uncleanly",
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
    assert payload["first_failing_event"] == "WS1006_PROCESS_RESTART_REQUIRED"
    assert payload["findings"][0]["code"] != "AUTH_FAILURE"
    assert payload["next_fix_recommendation"] != "Investigate auth_failure first."


def test_live_rca_agent_flags_explicit_auth_failure(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                "AUTH_BLOCKED: login required",
                "KITE_ACCESS_TOKEN_MISSING",
                "401 unauthorized token/session context",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "feed_runtime_latest.json").write_text(json.dumps({"runtime_state": "RUNNING"}), encoding="utf-8")

    report = analyze_live_rca(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["findings"][0]["code"] == "AUTH_FAILURE"
    assert payload["first_failing_event"] in {"AUTH_FAILURE", "AUTH", "AUTH_BLOCKED", "KITE_ACCESS_TOKEN_MISSING"}


def test_live_rca_agent_treats_401_as_auth_only_with_auth_context(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                "HTTP 401 returned by downstream service during unrelated replay",
                "FEED_REBALANCE_APPLIED reason=stale_option_prune_refresh subscribe_count=12 unsubscribe_count=11",
                "Connection error: 1006 - connection was closed uncleanly",
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
    assert payload["findings"][0]["code"] == "WS1006_PROCESS_RESTART_REQUIRED"
    assert payload["next_fix_recommendation"] != "Investigate auth_failure first."


def test_live_rca_agent_ignores_unit_test_auth_failure_when_feed_is_churning(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                '{"event": "AUTH_FAILURE", "source": "unit_test", "reason": "synthetic"}',
                '{"event": "FEED_REBALANCE_APPLIED", "source": "on_ticks", "subscribe_count": 25, "unsubscribe_count": 1}',
                '{"event": "FEED_WS_PROCESS_RESTART_REQUIRED", "reason": "ws_error:1006"}',
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
                "reconnect_blocked_reason": "ws1006_process_restart_required",
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
    assert payload["findings"][0]["code"] == "WS1006_PROCESS_RESTART_REQUIRED"
    assert payload["first_failing_event"] == "WS1006_PROCESS_RESTART_REQUIRED"
    assert payload["next_fix_recommendation"] != "Investigate auth_failure first."


def test_live_rca_agent_prefers_current_session_strategy_select_when_feed_is_fresh(tmp_path: Path):
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
                "feed_truth_state": "LIVE",
                "ws_connected": True,
                "feed_health_snapshot": {"N2_FEED_FRESH": {"ok": True}},
                "gate_status": {"N2_FEED_FRESH": {"ok": True}},
                "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "strategy_no_qualified_reasons_latest.json").write_text(
        json.dumps(
            {
                "strategy_no_qualified_applicable": True,
                "no_candidate_constructed": True,
                "gate_reasons": {"NO_STRATEGY_QUALIFIED": 1},
                "writer_name": "runtime_strategy_no_qualified_reasons",
                "by_symbol": {
                    "NIFTY": {
                        "attempt_count": 1,
                        "strategies_attempted": ["MEAN_REVERT"],
                        "no_setup_qualified_count": 1,
                        "candidate_generated_then_dropped_count": 0,
                        "reason_categories": {"direction_or_regime_mismatch": 1},
                        "attempts": [
                            {
                                "symbol": "NIFTY",
                                "strategy_id": "MEAN_REVERT",
                                "no_candidate_constructed": True,
                                "reason_category": "direction_or_regime_mismatch",
                                "no_setup_reason": "regime_low_confidence",
                            }
                        ],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps({"raw_candidate_count": 4, "phase2_input_candidate_count": 4}),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "ranked_pipeline_runtime_latest.json").write_text(
        json.dumps({"ranked_candidate_count": 4, "executable_count": 0}),
        encoding="utf-8",
    )

    report = analyze_live_rca(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["findings"][0]["code"] in {"STRATEGY_SELECT_NO_QUALIFIED", "CANDIDATE_SUPPLY_EMPTY", "PHASE2_FILTERED_ALL"}
    assert payload["metrics"]["current_session_feed_fresh"] is True
    assert payload["metrics"]["stale_feed_evidence_count"] >= 1
    assert payload["metrics"]["current_session_strategy_select_count"] >= 1


def test_live_rca_agent_keeps_current_session_feed_churn_as_subscription_churn(tmp_path: Path):
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
                "feed_truth_state": "LIVE",
                "ws_connected": True,
                "feed_health_snapshot": {"N2_FEED_FRESH": {"ok": True}},
                "gate_status": {"N2_FEED_FRESH": {"ok": True}},
                "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
            }
        ),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "candidate_starvation_trace_latest.json").write_text(
        json.dumps({"raw_candidate_count": 4, "phase2_input_candidate_count": 4}),
        encoding="utf-8",
    )
    (runtime_dir / "logs" / "ranked_pipeline_runtime_latest.json").write_text(
        json.dumps({"ranked_candidate_count": 4, "executable_count": 0}),
        encoding="utf-8",
    )

    report = analyze_live_rca(runtime_dir=runtime_dir, logs_dir=logs_dir)
    payload = report.to_dict()
    assert payload["verdict"] == "BLOCKER"
    assert payload["findings"][0]["code"] == "SUBSCRIPTION_CHURN"
    assert payload["metrics"]["current_session_feed_fresh"] is True
    assert payload["metrics"]["stale_feed_evidence_count"] == 0


def test_live_rca_agent_classifies_no_live_option_feed_after_subscribe(tmp_path: Path):
    runtime_dir = tmp_path / ".runtime"
    logs_dir = tmp_path / "logs"
    (runtime_dir / "logs").mkdir(parents=True)
    logs_dir.mkdir()
    (runtime_dir / "logs" / "depth_ws_watchdog.log").write_text(
        "\n".join(
            [
                '{"event": "FEED_ON_CONNECT_SUBSCRIBE", "reason": "connect", "subscription_requested_by_symbol": {"NIFTY": 2}, "subscribed_option_tokens_count_by_symbol": {"NIFTY": 2}}',
                '{"event": "FEED_OPTION_VERIFY_BEGIN", "reason": "connect"}',
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
    assert payload["findings"][0]["code"] == "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE"
    assert payload["first_failing_event"] == "NO_LIVE_OPTION_FEED_AFTER_SUBSCRIBE"
