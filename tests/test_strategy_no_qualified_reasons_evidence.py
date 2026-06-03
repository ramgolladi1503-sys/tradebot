from __future__ import annotations

import json
from pathlib import Path

from core.runtime_strategy_no_qualified_reasons import (
    build_strategy_attempt_from_gate,
    build_strategy_attempt_from_trade_builder,
    build_strategy_no_qualified_reasons_payload,
    write_strategy_no_qualified_reasons_latest,
)


READY_INDICATORS = {
    "by_symbol": {
        "NIFTY": {"indicators_ok": True, "indicator_missing_inputs": []},
        "SENSEX": {"indicators_ok": True, "indicator_missing_inputs": []},
    }
}

READY_REGIME = {
    "by_symbol": {
        "NIFTY": {"primary_regime": "RANGE"},
        "SENSEX": {"primary_regime": "TREND"},
    },
    "gate_reasons": {},
}


def test_strategy_no_qualified_payload_emitted_for_no_strategy_qualified_zero_raw_candidates():
    attempts = [
        build_strategy_attempt_from_gate(
            symbol="SENSEX",
            strategy_id=None,
            gate_reasons=["NO_STRATEGY_QUALIFIED"],
            telemetry={"qual_fail_codes": ["vwap"], "qual_fail_reasons_raw": ["price below vwap setup"]},
        )
    ]

    payload = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={"NO_STRATEGY_QUALIFIED": 1},
        indicator_readiness={"by_symbol": {"SENSEX": {"indicators_ok": True, "indicator_missing_inputs": []}}},
        regime_truth={"by_symbol": {"SENSEX": {"primary_regime": "TREND"}}, "gate_reasons": {}},
        strategy_attempts=attempts,
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )

    assert payload["schema_version"] == 1
    assert payload["writer_name"] == "runtime_strategy_no_qualified_reasons"
    assert payload["strategy_no_qualified_applicable"] is True
    assert payload["not_applicable_reason"] is None
    assert payload["symbols_evaluated"] == ["SENSEX"]
    assert payload["strategies_attempted"] == ["unknown"]
    assert payload["raw_candidate_count"] == 0
    assert payload["phase2_input_candidate_count"] == 0
    assert payload["no_setup_qualified_count"] == 1
    assert payload["candidate_generated_then_dropped_count"] == 0
    assert payload["by_symbol"]["SENSEX"]["attempt_count"] == 1
    assert payload["by_symbol"]["SENSEX"]["attempts"][0]["trade_builder_ran"] is False
    assert payload["by_symbol"]["SENSEX"]["attempts"][0]["no_setup_reason"] == "price below vwap setup"
    assert payload["by_symbol"]["SENSEX"]["attempts"][0]["reason_category"] == "vwap"
    assert payload["by_strategy"]["unknown"]["attempt_count"] == 1


def test_strategy_no_qualified_payload_does_not_mislabel_feed_indicator_or_regime_blocks():
    attempts = [
        build_strategy_attempt_from_gate(
            symbol="NIFTY",
            strategy_id=None,
            gate_reasons=["NO_STRATEGY_QUALIFIED"],
            telemetry={"qual_fail_codes": ["breakout"]},
        )
    ]

    feed_blocked = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={"FEED_LTP_STALE": 1, "NO_STRATEGY_QUALIFIED": 1},
        indicator_readiness={"by_symbol": {"NIFTY": {"indicators_ok": True, "indicator_missing_inputs": []}}},
        regime_truth={"by_symbol": {"NIFTY": {"primary_regime": "RANGE"}}, "gate_reasons": {}},
        strategy_attempts=attempts,
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    indicator_blocked = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={"INDICATORS_MISSING": 1, "NO_STRATEGY_QUALIFIED": 1},
        indicator_readiness={"by_symbol": {"NIFTY": {"indicators_ok": False, "indicator_missing_inputs": ["rsi"]}}},
        regime_truth={"by_symbol": {"NIFTY": {"primary_regime": "RANGE"}}, "gate_reasons": {}},
        strategy_attempts=attempts,
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    regime_blocked = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={"REGIME_UNSTABLE": 1, "NO_STRATEGY_QUALIFIED": 1},
        indicator_readiness={"by_symbol": {"NIFTY": {"indicators_ok": True, "indicator_missing_inputs": []}}},
        regime_truth={"by_symbol": {"NIFTY": {"unstable_reasons": ["high_entropy"]}}, "gate_reasons": {"REGIME_UNSTABLE": 1}},
        strategy_attempts=attempts,
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )

    assert feed_blocked["strategy_no_qualified_applicable"] is False
    assert feed_blocked["not_applicable_reason"] == "feed_blocked"
    assert indicator_blocked["strategy_no_qualified_applicable"] is False
    assert indicator_blocked["not_applicable_reason"] == "indicator_blocked"
    assert regime_blocked["strategy_no_qualified_applicable"] is False
    assert regime_blocked["not_applicable_reason"] == "regime_blocked"


def test_strategy_no_qualified_payload_records_per_symbol_and_per_strategy_attempts():
    attempts = [
        build_strategy_attempt_from_gate(
            symbol="NIFTY",
            strategy_id="MEAN_REVERT",
            gate_reasons=["NO_STRATEGY_QUALIFIED"],
            telemetry={"qual_fail_codes": ["volume"], "qual_fail_reasons_raw": ["low volume confirmation"]},
        ),
        build_strategy_attempt_from_gate(
            symbol="SENSEX",
            strategy_id="TREND",
            gate_reasons=["NO_STRATEGY_QUALIFIED"],
            telemetry={"qual_fail_codes": ["breakout"], "qual_fail_reasons_raw": ["breakout not confirmed"]},
        ),
    ]

    payload = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}, {"symbol": "SENSEX"}],
        cycle_blockers={"NO_STRATEGY_QUALIFIED": 2},
        indicator_readiness=READY_INDICATORS,
        regime_truth=READY_REGIME,
        strategy_attempts=attempts,
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )

    assert payload["strategy_generation_attempt_count"] == 2
    assert payload["by_symbol"]["NIFTY"]["attempts"][0]["strategy_id"] == "MEAN_REVERT"
    assert payload["by_symbol"]["SENSEX"]["attempts"][0]["strategy_id"] == "TREND"
    assert payload["by_strategy"]["MEAN_REVERT"]["reason_categories"]["volume"] == 1
    assert payload["by_strategy"]["TREND"]["reason_categories"]["breakout"] == 1


def test_strategy_no_qualified_payload_preserves_read_only_safety_flags():
    payload = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={"NO_STRATEGY_QUALIFIED": 1},
        indicator_readiness={"by_symbol": {"SENSEX": {"indicators_ok": True, "indicator_missing_inputs": []}}},
        regime_truth={"by_symbol": {"SENSEX": {"primary_regime": "TREND"}}, "gate_reasons": {}},
        strategy_attempts=[],
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_allowed"] is False


def test_strategy_no_qualified_payload_distinguishes_no_setup_from_generated_then_dropped():
    attempts = [
        build_strategy_attempt_from_gate(
            symbol="NIFTY",
            strategy_id="MEAN_REVERT",
            gate_reasons=["NO_STRATEGY_QUALIFIED"],
            telemetry={"qual_fail_codes": ["vwap"]},
        ),
        build_strategy_attempt_from_trade_builder(
            symbol="SENSEX",
            strategy_id="TREND",
            raw_candidate_count=2,
            post_scan_survivor_count=0,
            trade_generated=False,
            reject_reason="spread too wide",
            reject_gate_reasons=["SPREAD_TOO_WIDE"],
        ),
    ]

    payload = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}, {"symbol": "SENSEX"}],
        cycle_blockers={"NO_STRATEGY_QUALIFIED": 1, "SPREAD_TOO_WIDE": 1},
        indicator_readiness=READY_INDICATORS,
        regime_truth=READY_REGIME,
        strategy_attempts=attempts,
        raw_candidate_count=2,
        phase2_input_candidate_count=0,
    )

    assert payload["no_setup_qualified_count"] == 1
    assert payload["candidate_generated_then_dropped_count"] == 1
    assert payload["by_symbol"]["NIFTY"]["attempts"][0]["candidate_generated_then_dropped"] is False
    assert payload["by_symbol"]["SENSEX"]["attempts"][0]["candidate_generated_then_dropped"] is True
    assert payload["by_symbol"]["SENSEX"]["attempts"][0]["reason_category"] == "spread"


def test_strategy_no_qualified_payload_marks_empty_predicate_facts_as_no_candidate_constructed():
    attempt = build_strategy_attempt_from_gate(
        symbol="NIFTY",
        strategy_id=None,
        gate_reasons=["NO_STRATEGY_QUALIFIED"],
        telemetry={},
    )

    assert attempt["strategy_id"] == "unknown"
    assert attempt["no_setup_reason"] == "no_strategy_candidate_constructed_before_gate"
    assert attempt["reason_category"] == "unknown"
    assert attempt["trade_builder_ran"] is False
    assert attempt["candidate_produced"] is False
    assert attempt["no_candidate_constructed"] is True


def test_strategy_no_qualified_payload_promotes_all_candidates_reasons_into_summary_fields():
    attempt = build_strategy_attempt_from_gate(
        symbol="SENSEX",
        strategy_id=None,
        gate_reasons=["NO_STRATEGY_QUALIFIED"],
        telemetry={
            "qual_fail_codes": ["no_candidates"],
            "qual_fail_reasons_raw": [],
            "all_candidates": [
                {
                    "family": None,
                    "allowed": False,
                    "manual_review_required": False,
                    "reasons": ["indicators_missing_or_stale"],
                    "candidate_summary": {},
                }
            ],
        },
    )

    assert attempt["qual_fail_reasons_raw"] == ["indicators_missing_or_stale"]
    assert attempt["no_setup_reason"] == "indicators_missing_or_stale"
    assert attempt["reason_category"] == "indicator_gate"
    assert attempt["no_candidate_constructed"] is True


def test_strategy_no_qualified_payload_marks_latency_guard_as_non_applicable():
    payload = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={"LATENCY_GUARD_COOLDOWN_PREBUILD_SKIP": 1, "NO_STRATEGY_QUALIFIED": 1},
        indicator_readiness=READY_INDICATORS,
        regime_truth=READY_REGIME,
        strategy_attempts=[],
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )

    assert payload["strategy_no_qualified_applicable"] is False
    assert payload["not_applicable_reason"] == "latency_guard"


def test_strategy_no_qualified_payload_includes_latency_guard_evidence_fields():
    payload = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={"LATENCY_GUARD_DEGRADE_EXIT_ONLY_PREBUILD_SKIP": 1},
        indicator_readiness=READY_INDICATORS,
        regime_truth=READY_REGIME,
        strategy_attempts=[],
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
        latency_guard={
            "latency_guard_triggered": True,
            "latency_guard_mode": "LIVE",
            "latency_guard_action": "DEGRADE_EXIT_ONLY",
            "latency_guard_source": "latency_monitor.stages.total_loop.p95_ms",
            "latency_guard_reason": "latency_sustained_breach",
            "latency_guard_metric": "total_loop.p95_ms",
            "latency_guard_value": 180.0,
            "latency_guard_threshold": 120.0,
            "latency_guard_age_sec": 4.0,
            "latency_guard_last_ok_at": 100.0,
            "latency_guard_last_bad_at": 104.0,
            "latency_guard_recovery_required": True,
        },
    )

    assert payload["latency_guard_triggered"] is True
    assert payload["latency_guard_action"] == "DEGRADE_EXIT_ONLY"
    assert payload["latency_guard_metric"] == "total_loop.p95_ms"
    assert payload["latency_guard_threshold"] == 120.0
    assert payload["latency_guard_reason"] == "latency_sustained_breach"


def test_strategy_no_qualified_payload_does_not_change_candidate_counts_or_strategy_decisions():
    attempts = [
        build_strategy_attempt_from_trade_builder(
            symbol="NIFTY",
            strategy_id="TREND",
            raw_candidate_count=3,
            post_scan_survivor_count=1,
            trade_generated=True,
            reject_reason="",
            reject_gate_reasons=[],
        )
    ]

    payload = build_strategy_no_qualified_reasons_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={},
        indicator_readiness={"by_symbol": {"NIFTY": {"indicators_ok": True, "indicator_missing_inputs": []}}},
        regime_truth={"by_symbol": {"NIFTY": {"primary_regime": "TREND"}}, "gate_reasons": {}},
        strategy_attempts=attempts,
        raw_candidate_count=3,
        phase2_input_candidate_count=1,
    )

    assert payload["strategy_no_qualified_applicable"] is False
    assert payload["not_applicable_reason"] == "candidates_reached_phase2"
    assert payload["raw_candidate_count"] == 3
    assert payload["phase2_input_candidate_count"] == 1
    assert payload["by_symbol"]["NIFTY"]["attempts"][0]["candidate_produced"] is True


def test_strategy_no_qualified_writer_writes_logs_runtime_and_runtime_logs(tmp_path: Path):
    logs_path = tmp_path / "logs" / "strategy_no_qualified_reasons_latest.json"
    runtime_path = tmp_path / ".runtime" / "strategy_no_qualified_reasons_latest.json"
    runtime_logs_path = tmp_path / ".runtime" / "logs" / "strategy_no_qualified_reasons_latest.json"
    payload = build_strategy_no_qualified_reasons_payload(
        execution_mode="SIM",
        market_open=False,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={"NO_STRATEGY_QUALIFIED": 1},
        indicator_readiness={"by_symbol": {"NIFTY": {"ready": True}}},
        regime_truth={"by_symbol": {"NIFTY": {"primary_regime": "RANGE"}}, "gate_reasons": {}},
        strategy_attempts=[
            build_strategy_attempt_from_gate(
                symbol="NIFTY",
                strategy_id="MEAN_REVERT",
                gate_reasons=["NO_STRATEGY_QUALIFIED"],
                telemetry={"qual_fail_codes": ["option_chain_confirmation"]},
            )
        ],
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )

    p_logs, p_runtime, p_runtime_logs = write_strategy_no_qualified_reasons_latest(
        payload=payload,
        logs_path=logs_path,
        runtime_path=runtime_path,
        runtime_logs_path=runtime_logs_path,
    )

    assert p_logs == logs_path
    assert p_runtime == runtime_path
    assert p_runtime_logs == runtime_logs_path
    assert json.loads(logs_path.read_text())["writer_name"] == "runtime_strategy_no_qualified_reasons"
    assert json.loads(runtime_path.read_text())["schema_version"] == 1
    assert json.loads(runtime_logs_path.read_text())["broker_api_called"] is False


def test_strategy_no_qualified_writer_default_paths_fan_out_to_all_three_locations(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "core.runtime_strategy_no_qualified_reasons.repo_logs_dir",
        lambda: tmp_path / "logs",
    )
    monkeypatch.setattr(
        "core.runtime_strategy_no_qualified_reasons.runtime_dir",
        lambda: tmp_path / ".runtime",
    )
    monkeypatch.setattr(
        "core.runtime_strategy_no_qualified_reasons.logs_dir",
        lambda: tmp_path / ".runtime" / "logs",
    )

    payload = build_strategy_no_qualified_reasons_payload(
        execution_mode="SIM",
        market_open=False,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={"NO_STRATEGY_QUALIFIED": 1},
        indicator_readiness={"by_symbol": {"NIFTY": {"ready": True}}},
        regime_truth={"by_symbol": {"NIFTY": {"primary_regime": "RANGE"}}, "gate_reasons": {}},
        strategy_attempts=[],
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )

    write_strategy_no_qualified_reasons_latest(payload=payload)

    logs_path = tmp_path / "logs" / "strategy_no_qualified_reasons_latest.json"
    runtime_path = tmp_path / ".runtime" / "strategy_no_qualified_reasons_latest.json"
    runtime_logs_path = tmp_path / ".runtime" / "logs" / "strategy_no_qualified_reasons_latest.json"

    assert logs_path.exists()
    assert runtime_path.exists()
    assert runtime_logs_path.exists()
    assert json.loads(logs_path.read_text())["read_only"] is True
    assert json.loads(runtime_path.read_text())["append"] is False
    assert json.loads(runtime_logs_path.read_text())["live_order_allowed"] is False
