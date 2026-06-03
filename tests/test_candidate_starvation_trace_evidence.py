from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.runtime_candidate_starvation_trace import (
    build_candidate_starvation_trace_payload,
    write_candidate_starvation_trace_latest,
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture()
def _artifact_dirs(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = tmp_path / "logs"
    runtime_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DATA_ROOT", str(runtime_root))
    monkeypatch.setenv("LOG_DIR", str(runtime_root / "logs"))
    monkeypatch.setenv("REPO_LOG_DIR", str(logs_root))
    return runtime_root, logs_root


def _symbol_snapshot(
    *,
    symbol: str,
    primary_regime: str,
    regime_entropy: float,
    regime_prob_max: float,
    unstable_reasons: list[str],
    raw_candidate_count: int,
    scan_reject_counts: dict[str, int],
    post_scan_survivor_count: int = 0,
    post_soft_reject_count: int = 0,
    post_real_filter_count: int = 0,
    post_executable_filter_count: int = 0,
    reject_reason: str | None = None,
    final_emit_block_reason: str | None = None,
    feed_runtime_state: str = "RUNNING",
    ws_connected: bool = True,
    option_feed_block_reason: str = "OK",
    quote_health_state: str = "OK",
    ltp_age_sec: float = 0.4,
) -> dict:
    return {
        "symbol": symbol,
        "regime": {
            "primary_regime": primary_regime,
            "regime_entropy": regime_entropy,
            "regime_entropy_max": 1.3,
            "regime_prob_max": regime_prob_max,
            "regime_prob_min": 0.45,
            "regime_unstable_streak": 3 if unstable_reasons else 0,
            "regime_unstable_block_after": 2 if unstable_reasons else 0,
            "regime_unstable_debounced": bool(unstable_reasons),
            "unstable_reasons": list(unstable_reasons),
            "regime_unstable": bool(unstable_reasons),
            "feed_runtime_state": feed_runtime_state,
            "ws_connected": ws_connected,
            "option_feed_block_reason": option_feed_block_reason,
            "quote_health_state": quote_health_state,
            "quote_health_stale_reasons": [],
            "ltp_age_sec": ltp_age_sec,
        },
        "raw_candidate_count": raw_candidate_count,
        "post_scan_survivor_count": post_scan_survivor_count,
        "post_soft_reject_count": post_soft_reject_count,
        "post_real_filter_count": post_real_filter_count,
        "post_executable_filter_count": post_executable_filter_count,
        "reject_reason": reject_reason,
        "final_emit_block_reason": final_emit_block_reason,
        "reject_gate_reasons": ["REGIME_UNSTABLE"] if unstable_reasons else [],
        "scan_reject_counts": dict(scan_reject_counts),
        "feed_runtime_state": feed_runtime_state,
        "ws_connected": ws_connected,
        "option_feed_block_reason": option_feed_block_reason,
        "quote_health_state": quote_health_state,
        "quote_health_stale_reasons": [],
        "ltp_age_sec": ltp_age_sec,
    }


def test_candidate_starvation_trace_aggregates_regime_unstable_and_survivor_funnel(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    payload = build_candidate_starvation_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "BANKNIFTY"}, {"symbol": "NIFTY"}],
        cycle_blockers={"REGIME_UNSTABLE": 162, "PHASE2_NO_INPUT": 28},
        feed_runtime={
            "ws_connected": True,
            "runtime_state": "RUNNING",
            "option_feed_block_reason": "OK",
            "feed_fresh": True,
            "option_tick_fresh": True,
            "underlying_tick_fresh": True,
            "depth_fresh": True,
            "subscribed_tokens_count": 73,
            "subscribed_option_tokens_count": 70,
            "stale_reason": [],
        },
        candidate_starvation_snapshots=[
            _symbol_snapshot(
                symbol="BANKNIFTY",
                primary_regime="CHOP",
                regime_entropy=1.62,
                regime_prob_max=0.41,
                unstable_reasons=["prob_too_low", "entropy_too_high"],
                raw_candidate_count=22,
                scan_reject_counts={"confidence_raw_gate": 22},
            ),
            _symbol_snapshot(
                symbol="NIFTY",
                primary_regime="RANGE",
                regime_entropy=1.58,
                regime_prob_max=0.44,
                unstable_reasons=["prob_too_low"],
                raw_candidate_count=4,
                scan_reject_counts={"iv_z_bounds": 4},
            ),
        ],
        candidate_handoff_root_cause={
            "top_drop_reasons": {"confidence_raw_gate": 22, "iv_z_bounds": 4},
        },
        phase2_rejection={
            "top_non_executable_reasons": {"no_viable_candidates": 9},
        },
    )

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["market_data_symbol_count"] == 2
    assert payload["regime_unstable_symbol_count"] == 2
    assert payload["regime_unstable_reason_counts"]["prob_too_low"] == 2
    assert payload["raw_candidate_count"] == 26
    assert payload["post_scan_survivor_count"] == 0
    assert payload["post_soft_reject_count"] == 0
    assert payload["post_real_filter_count"] == 0
    assert payload["post_executable_filter_count"] == 0
    assert payload["survivor_count"] == 0
    assert payload["first_zero_stage"] == "post_scan_survivor_zero"
    assert payload["top_reject_reasons"]["confidence_raw_gate"] == 22
    assert payload["top_reject_reasons"]["iv_z_bounds"] == 4
    assert payload["blocker_counts"]["REGIME_UNSTABLE"] == 162
    assert payload["blocker_counts"]["PHASE2_NO_INPUT"] == 28
    assert payload["top_blockers"][0] == {"reason": "REGIME_UNSTABLE", "count": 162}
    assert payload["reject_reason_details"]["confidence_raw_gate"]["count"] == 22
    assert payload["reject_reason_details"]["iv_z_bounds"]["count"] == 4
    assert payload["reject_reason_details"]["no_viable_candidates"]["count"] == 9
    assert payload["feed_truth"]["ws_connected"] is True
    assert payload["feed_truth"]["runtime_state"] == "RUNNING"
    assert payload["feed_truth"]["option_feed_block_reason"] == "OK"
    assert payload["quote_health_state"] == "OK"
    assert payload["ltp_age_sec"] == 0.4
    assert payload["by_symbol"]["BANKNIFTY"]["regime"]["regime_entropy"] == 1.62
    assert payload["by_symbol"]["BANKNIFTY"]["regime"]["regime_entropy_max"] == 1.3
    assert payload["by_symbol"]["BANKNIFTY"]["regime"]["regime_prob_max"] == 0.41
    assert payload["by_symbol"]["BANKNIFTY"]["regime"]["regime_prob_min"] == 0.45

    logs_path = logs_root / "candidate_starvation_trace_latest.json"
    runtime_path = runtime_root / "candidate_starvation_trace_latest.json"
    runtime_logs_path = runtime_root / "logs" / "candidate_starvation_trace_latest.json"
    p_logs, p_runtime, p_runtime_logs = write_candidate_starvation_trace_latest(
        payload=payload,
        logs_path=logs_path,
        runtime_path=runtime_path,
        runtime_logs_path=runtime_logs_path,
    )
    assert p_logs == logs_path
    assert p_runtime == runtime_path
    assert p_runtime_logs == runtime_logs_path
    assert logs_path.exists()
    assert runtime_path.exists()
    assert runtime_logs_path.exists()
    assert _read_json(logs_path)["raw_candidate_count"] == 26
    assert _read_json(runtime_path)["top_reject_reasons"]["confidence_raw_gate"] == 22
    assert _read_json(runtime_logs_path)["feed_truth"]["runtime_state"] == "RUNNING"


def test_candidate_starvation_trace_writes_all_fanout_paths(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    payload = build_candidate_starvation_trace_payload(
        execution_mode="SIM",
        market_open=False,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={},
        feed_runtime={"ws_connected": True, "runtime_state": "RUNNING", "option_feed_block_reason": "OK"},
        candidate_starvation_snapshots=[],
        candidate_handoff_root_cause={"top_drop_reasons": {}},
        phase2_rejection={"top_non_executable_reasons": {}},
    )
    write_candidate_starvation_trace_latest(payload=payload)
    assert (logs_root / "candidate_starvation_trace_latest.json").exists()
    assert (runtime_root / "candidate_starvation_trace_latest.json").exists()
    assert (runtime_root / "logs" / "candidate_starvation_trace_latest.json").exists()
    assert _read_json(logs_root / "candidate_starvation_trace_latest.json")["read_only"] is True
    assert _read_json(runtime_root / "candidate_starvation_trace_latest.json")["append"] is False
    assert _read_json(runtime_root / "logs" / "candidate_starvation_trace_latest.json")["is_order_action"] is False


def test_candidate_starvation_trace_includes_latency_guard_blockers_and_fails_closed(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    payload = build_candidate_starvation_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={
            "LATENCY_GUARD_COOLDOWN_PREBUILD_SKIP": 3,
            "LATENCY_GUARD_DEGRADE_EXIT_ONLY_PREBUILD_SKIP": 2,
        },
        feed_runtime={
            "ws_connected": True,
            "runtime_state": "RUNNING",
            "option_feed_block_reason": "OK",
            "feed_fresh": True,
            "option_tick_fresh": True,
            "underlying_tick_fresh": True,
            "depth_fresh": True,
            "stale_reason": [],
        },
        candidate_starvation_snapshots=[
            _symbol_snapshot(
                symbol="SENSEX",
                primary_regime="TREND",
                regime_entropy=0.25,
                regime_prob_max=0.91,
                unstable_reasons=[],
                raw_candidate_count=0,
                scan_reject_counts={"no_viable_candidates": 5},
            )
        ],
        candidate_handoff_root_cause={"top_drop_reasons": {"no_viable_candidates": 5}},
        phase2_rejection={"top_non_executable_reasons": {"no_viable_candidates": 5}},
    )

    assert payload["blocker_counts"]["LATENCY_GUARD_COOLDOWN_PREBUILD_SKIP"] == 3
    assert payload["blocker_counts"]["LATENCY_GUARD_DEGRADE_EXIT_ONLY_PREBUILD_SKIP"] == 2
    assert payload["top_blockers"][0]["reason"] == "LATENCY_GUARD_COOLDOWN_PREBUILD_SKIP"
    assert payload["top_blockers"][0]["count"] == 3
    assert payload["by_symbol"]["SENSEX"]["reject_reason"] == "no_viable_candidates"
    assert payload["by_symbol"]["SENSEX"]["scan_reject_counts"]["no_viable_candidates"] == 5
    assert payload["by_symbol"]["SENSEX"]["candidate_funnel_stage"] == "no_raw_candidates"
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False

    write_candidate_starvation_trace_latest(payload=payload)
    assert (logs_root / "candidate_starvation_trace_latest.json").exists()
    assert (runtime_root / "candidate_starvation_trace_latest.json").exists()


def test_candidate_starvation_trace_preserves_symbol_traces_when_later_global_risk_halt_overwrites_cycle(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    first_payload = build_candidate_starvation_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "BANKNIFTY"}, {"symbol": "SENSEX"}],
        cycle_blockers={"REGIME_UNSTABLE": 162},
        feed_runtime={
            "ws_connected": True,
            "runtime_state": "RUNNING",
            "option_feed_block_reason": "OK",
            "feed_fresh": True,
            "option_tick_fresh": True,
            "underlying_tick_fresh": True,
            "depth_fresh": True,
            "stale_reason": [],
        },
        candidate_starvation_snapshots=[
            _symbol_snapshot(
                symbol="BANKNIFTY",
                primary_regime="CHOP",
                regime_entropy=1.55,
                regime_prob_max=0.42,
                unstable_reasons=["prob_too_low"],
                raw_candidate_count=26,
                post_scan_survivor_count=13,
                post_soft_reject_count=13,
                post_real_filter_count=13,
                post_executable_filter_count=1,
                final_emit_block_reason="premium_sanity",
                scan_reject_counts={"confidence_raw_gate": 13},
            ),
            _symbol_snapshot(
                symbol="SENSEX",
                primary_regime="RANGE",
                regime_entropy=1.32,
                regime_prob_max=0.51,
                unstable_reasons=["entropy_too_high"],
                raw_candidate_count=18,
                post_scan_survivor_count=9,
                post_soft_reject_count=9,
                post_real_filter_count=9,
                post_executable_filter_count=8,
                final_emit_block_reason="STALE_OPTION_LTP",
                scan_reject_counts={"iv_z_bounds": 4},
            ),
        ],
        candidate_handoff_root_cause={"top_drop_reasons": {"confidence_raw_gate": 13, "iv_z_bounds": 4}},
        phase2_rejection={"top_non_executable_reasons": {"no_viable_candidates": 2}},
    )
    first_payload["latest_global_blocker"] = ["REGIME_UNSTABLE", 162]

    later_payload = build_candidate_starvation_trace_payload(
        execution_mode="LIVE",
        market_open=False,
        market_data_list=[],
        cycle_blockers={"RISK_HALT": 1},
        feed_runtime={
            "ws_connected": False,
            "runtime_state": "RUNNING",
            "option_feed_block_reason": "OK",
            "feed_fresh": False,
            "option_tick_fresh": False,
            "underlying_tick_fresh": False,
            "depth_fresh": False,
            "stale_reason": ["ws_disconnected"],
        },
        candidate_starvation_snapshots=[],
        candidate_handoff_root_cause={"top_drop_reasons": {}},
        phase2_rejection={"top_non_executable_reasons": {}},
        previous_payload=first_payload,
    )

    assert later_payload["latest_global_blocker"] == "RISK_HALT"
    assert later_payload["latest_global_blocker_count"] == 1
    assert later_payload["latest_global_blocker_counts"]["RISK_HALT"] == 1
    assert later_payload["blocker_counts"]["RISK_HALT"] == 1
    assert later_payload["top_blockers"][0] == {"reason": "RISK_HALT", "count": 1}
    assert later_payload["had_symbol_candidates_this_session_or_cycle"] is True
    assert later_payload["symbol_traces"]["BANKNIFTY"]["raw_candidate_count"] == 26
    assert later_payload["symbol_traces"]["BANKNIFTY"]["post_scan_survivor_count"] == 13
    assert later_payload["symbol_traces"]["BANKNIFTY"]["post_soft_reject_count"] == 13
    assert later_payload["symbol_traces"]["BANKNIFTY"]["post_real_filter_count"] == 13
    assert later_payload["symbol_traces"]["BANKNIFTY"]["post_executable_filter_count"] == 1
    assert later_payload["symbol_traces"]["BANKNIFTY"]["final_emit_block_reason"] == "premium_sanity"
    assert later_payload["symbol_traces"]["SENSEX"]["raw_candidate_count"] == 18
    assert later_payload["symbol_traces"]["SENSEX"]["post_scan_survivor_count"] == 9
    assert later_payload["symbol_traces"]["SENSEX"]["post_soft_reject_count"] == 9
    assert later_payload["symbol_traces"]["SENSEX"]["post_real_filter_count"] == 9
    assert later_payload["symbol_traces"]["SENSEX"]["post_executable_filter_count"] == 8
    assert later_payload["symbol_traces"]["SENSEX"]["final_emit_block_reason"] == "STALE_OPTION_LTP"
    assert later_payload["last_candidate_funnel_by_symbol"]["BANKNIFTY"]["raw_candidate_count"] == 26
    assert later_payload["last_candidate_funnel_by_symbol"]["SENSEX"]["raw_candidate_count"] == 18
    assert later_payload["read_only"] is True
    assert later_payload["append"] is False
    assert later_payload["is_order_action"] is False
    assert later_payload["broker_api_called"] is False

    write_candidate_starvation_trace_latest(
        payload=later_payload,
        logs_path=logs_root / "candidate_starvation_trace_latest.json",
        runtime_path=runtime_root / "candidate_starvation_trace_latest.json",
        runtime_logs_path=runtime_root / "logs" / "candidate_starvation_trace_latest.json",
    )
    persisted = _read_json(logs_root / "candidate_starvation_trace_latest.json")
    assert persisted["latest_global_blocker"] == "RISK_HALT"
    assert persisted["latest_global_blocker_count"] == 1
    assert persisted["symbol_traces"]["BANKNIFTY"]["raw_candidate_count"] == 26
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_scan_survivor_count"] == 13
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_executable_filter_count"] == 1
    assert persisted["symbol_traces"]["BANKNIFTY"]["final_emit_block_reason"] == "premium_sanity"
    assert persisted["symbol_traces"]["SENSEX"]["raw_candidate_count"] == 18
    assert persisted["symbol_traces"]["SENSEX"]["post_scan_survivor_count"] == 9
    assert persisted["symbol_traces"]["SENSEX"]["post_executable_filter_count"] == 8
    assert persisted["symbol_traces"]["SENSEX"]["final_emit_block_reason"] == "STALE_OPTION_LTP"
    assert persisted["last_candidate_funnel_by_symbol"]["BANKNIFTY"]["post_executable_filter_count"] == 1


def test_candidate_starvation_trace_merges_existing_disk_symbol_traces_on_global_only_overwrite(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    initial_payload = build_candidate_starvation_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "BANKNIFTY"}],
        cycle_blockers={"REGIME_UNSTABLE": 162},
        feed_runtime={
            "ws_connected": True,
            "runtime_state": "RUNNING",
            "option_feed_block_reason": "OK",
            "feed_fresh": True,
            "option_tick_fresh": True,
            "underlying_tick_fresh": True,
            "depth_fresh": True,
            "stale_reason": [],
        },
        candidate_starvation_snapshots=[
            _symbol_snapshot(
                symbol="BANKNIFTY",
                primary_regime="CHOP",
                regime_entropy=1.55,
                regime_prob_max=0.42,
                unstable_reasons=["prob_too_low"],
                raw_candidate_count=26,
                post_scan_survivor_count=13,
                post_soft_reject_count=13,
                post_real_filter_count=13,
                post_executable_filter_count=1,
                final_emit_block_reason="premium_sanity",
                scan_reject_counts={"confidence_raw_gate": 13},
            )
        ],
        candidate_handoff_root_cause={"top_drop_reasons": {"confidence_raw_gate": 13}},
        phase2_rejection={"top_non_executable_reasons": {"no_viable_candidates": 1}},
    )
    write_candidate_starvation_trace_latest(payload=initial_payload)

    global_only_payload = build_candidate_starvation_trace_payload(
        execution_mode="LIVE",
        market_open=False,
        market_data_list=[],
        cycle_blockers={"RISK_HALT": 1},
        feed_runtime={
            "ws_connected": False,
            "runtime_state": "RUNNING",
            "option_feed_block_reason": "OK",
            "feed_fresh": False,
            "option_tick_fresh": False,
            "underlying_tick_fresh": False,
            "depth_fresh": False,
            "stale_reason": ["ws_disconnected"],
        },
        candidate_starvation_snapshots=[],
        candidate_handoff_root_cause={"top_drop_reasons": {}},
        phase2_rejection={"top_non_executable_reasons": {}},
    )
    write_candidate_starvation_trace_latest(payload=global_only_payload)

    persisted = _read_json(logs_root / "candidate_starvation_trace_latest.json")
    assert persisted["latest_global_blocker"] == "RISK_HALT"
    assert persisted["latest_global_blocker_count"] == 1
    assert persisted["latest_global_blocker_counts"]["RISK_HALT"] == 1
    assert persisted["had_symbol_candidates_this_session_or_cycle"] is True
    assert persisted["symbol_count"] >= 1
    assert "BANKNIFTY" in persisted["symbol_traces"]
    assert persisted["symbol_traces"]["BANKNIFTY"]["raw_candidate_count"] == 26
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_scan_survivor_count"] == 13
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_soft_reject_count"] == 13
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_real_filter_count"] == 13
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_executable_filter_count"] == 1
    assert persisted["symbol_traces"]["BANKNIFTY"]["final_emit_block_reason"] == "premium_sanity"
    assert persisted["last_candidate_funnel_by_symbol"]["BANKNIFTY"]["raw_candidate_count"] == 26
    assert persisted["last_candidate_funnel_by_symbol"]["BANKNIFTY"]["post_executable_filter_count"] == 1
    assert persisted["blocker_counts"]["RISK_HALT"] == 1
    assert persisted["top_blockers"][0] == {"reason": "RISK_HALT", "count": 1}
    assert persisted["read_only"] is True
    assert persisted["append"] is False
    assert persisted["is_order_action"] is False
    assert persisted["broker_api_called"] is False


def test_candidate_starvation_trace_prefers_richer_symbol_rows_when_global_only_overwrite_occurs(_artifact_dirs):
    runtime_root, logs_root = _artifact_dirs
    initial_payload = build_candidate_starvation_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "BANKNIFTY"}, {"symbol": "SENSEX"}],
        cycle_blockers={"REGIME_UNSTABLE": 162},
        feed_runtime={
            "ws_connected": True,
            "runtime_state": "RUNNING",
            "option_feed_block_reason": "OK",
            "feed_fresh": True,
            "option_tick_fresh": True,
            "underlying_tick_fresh": True,
            "depth_fresh": True,
            "stale_reason": [],
        },
        candidate_starvation_snapshots=[
            _symbol_snapshot(
                symbol="BANKNIFTY",
                primary_regime="CHOP",
                regime_entropy=1.55,
                regime_prob_max=0.42,
                unstable_reasons=["prob_too_low"],
                raw_candidate_count=26,
                post_scan_survivor_count=13,
                post_soft_reject_count=13,
                post_real_filter_count=13,
                post_executable_filter_count=1,
                final_emit_block_reason="premium_sanity",
                scan_reject_counts={"confidence_raw_gate": 13},
            ),
            _symbol_snapshot(
                symbol="SENSEX",
                primary_regime="RANGE",
                regime_entropy=1.32,
                regime_prob_max=0.51,
                unstable_reasons=["entropy_too_high"],
                raw_candidate_count=18,
                post_scan_survivor_count=9,
                post_soft_reject_count=9,
                post_real_filter_count=9,
                post_executable_filter_count=8,
                final_emit_block_reason="STALE_OPTION_LTP",
                scan_reject_counts={"iv_z_bounds": 4},
            ),
        ],
        candidate_handoff_root_cause={"top_drop_reasons": {"confidence_raw_gate": 13, "iv_z_bounds": 4}},
        phase2_rejection={"top_non_executable_reasons": {"no_viable_candidates": 2}},
    )
    write_candidate_starvation_trace_latest(payload=initial_payload)

    global_only_payload = build_candidate_starvation_trace_payload(
        execution_mode="LIVE",
        market_open=False,
        market_data_list=[],
        cycle_blockers={"RISK_HALT": 1},
        feed_runtime={
            "ws_connected": False,
            "runtime_state": "RUNNING",
            "option_feed_block_reason": "OK",
            "feed_fresh": False,
            "option_tick_fresh": False,
            "underlying_tick_fresh": False,
            "depth_fresh": False,
            "stale_reason": ["ws_disconnected"],
        },
        candidate_starvation_snapshots=[],
        candidate_handoff_root_cause={"top_drop_reasons": {}},
        phase2_rejection={"top_non_executable_reasons": {}},
    )
    write_candidate_starvation_trace_latest(payload=global_only_payload)

    persisted = _read_json(logs_root / "candidate_starvation_trace_latest.json")
    assert persisted["latest_global_blocker"] == "RISK_HALT"
    assert persisted["latest_global_blocker_counts"] == {"RISK_HALT": 1}
    assert persisted["had_symbol_candidates_this_session_or_cycle"] is True
    assert persisted["symbol_count"] >= 2
    assert persisted["symbol_traces"]["BANKNIFTY"]["raw_candidate_count"] == 26
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_scan_survivor_count"] == 13
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_soft_reject_count"] == 13
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_real_filter_count"] == 13
    assert persisted["symbol_traces"]["BANKNIFTY"]["post_executable_filter_count"] == 1
    assert persisted["symbol_traces"]["BANKNIFTY"]["final_emit_block_reason"] == "premium_sanity"
    assert persisted["symbol_traces"]["SENSEX"]["raw_candidate_count"] == 18
    assert persisted["symbol_traces"]["SENSEX"]["post_scan_survivor_count"] == 9
    assert persisted["symbol_traces"]["SENSEX"]["post_soft_reject_count"] == 9
    assert persisted["symbol_traces"]["SENSEX"]["post_real_filter_count"] == 9
    assert persisted["symbol_traces"]["SENSEX"]["post_executable_filter_count"] == 8
    assert persisted["symbol_traces"]["SENSEX"]["final_emit_block_reason"] == "STALE_OPTION_LTP"
    assert persisted["last_candidate_funnel_by_symbol"]["BANKNIFTY"]["post_executable_filter_count"] == 1
    assert persisted["last_candidate_funnel_by_symbol"]["SENSEX"]["post_executable_filter_count"] == 8
    assert persisted["read_only"] is True
    assert persisted["append"] is False
    assert persisted["is_order_action"] is False
    assert persisted["broker_api_called"] is False
