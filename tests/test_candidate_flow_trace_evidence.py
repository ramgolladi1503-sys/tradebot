from __future__ import annotations

import json
from pathlib import Path

from core.runtime_candidate_flow_trace import (
    build_candidate_flow_trace_payload,
    write_candidate_flow_trace_latest,
)


def test_candidate_flow_trace_no_market_data_classifies_first_zero_stage(tmp_path: Path):
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[],
        cycle_blockers={},
        indicator_readiness={},
        regime_truth={},
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["schema_version"] == 1
    assert payload["writer_schema_version"] == payload["schema_version"]
    assert payload["writer_name"] == "runtime_candidate_flow_trace"
    assert payload["market_data_symbol_count"] == 0
    assert payload["first_zero_stage"] == "no_market_data"


def test_candidate_flow_trace_indicators_blocked_when_all_symbols_not_ready(tmp_path: Path):
    indicator = {"by_symbol": {"SENSEX": {"ready": False}}}
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={"INDICATORS_MISSING": 1},
        indicator_readiness=indicator,
        regime_truth={"by_symbol": {}},
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    assert payload["market_data_symbol_count"] == 1
    assert payload["indicator_blocked_symbol_count"] == 1
    assert payload["indicator_ready_symbol_count"] == 0
    assert payload["first_zero_stage"] == "indicators_blocked"
    assert payload["gate_reasons"]["INDICATORS_MISSING"] == 1
    assert payload["by_symbol"]["SENSEX"]["indicator_ready"] is False


def test_candidate_flow_trace_indicators_ok_counts_as_ready_even_without_ready_key(tmp_path: Path):
    indicator = {"by_symbol": {"SENSEX": {"indicators_ok": True, "indicator_missing_inputs": []}}}
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={},
        indicator_readiness=indicator,
        regime_truth={"by_symbol": {}},
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    assert payload["indicator_ready_symbol_count"] == 1
    assert payload["indicator_blocked_symbol_count"] == 0
    assert payload["by_symbol"]["SENSEX"]["indicator_ready"] is True


def test_candidate_flow_trace_present_flags_with_empty_missing_list_counts_as_ready(tmp_path: Path):
    indicator = {
        "by_symbol": {
            "SENSEX": {
                "rsi_present": True,
                "ema_present": True,
                "atr_present": True,
                "vwap_present": True,
                "indicator_missing_inputs": [],
            }
        }
    }
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={},
        indicator_readiness=indicator,
        regime_truth={"by_symbol": {}},
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    assert payload["indicator_ready_symbol_count"] == 1
    assert payload["indicator_blocked_symbol_count"] == 0
    assert payload["by_symbol"]["SENSEX"]["indicator_ready"] is True


def test_candidate_flow_trace_missing_rsi_ema_counts_as_indicator_blocked(tmp_path: Path):
    indicator = {
        "by_symbol": {
            "SENSEX": {
                "atr_present": True,
                "vwap_present": True,
                "rsi_present": False,
                "ema_present": False,
                "indicator_missing_inputs": ["rsi", "ema"],
            }
        }
    }
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={"INDICATORS_MISSING": 1},
        indicator_readiness=indicator,
        regime_truth={"by_symbol": {}},
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    assert payload["indicator_ready_symbol_count"] == 0
    assert payload["indicator_blocked_symbol_count"] == 1
    assert payload["by_symbol"]["SENSEX"]["indicator_ready"] is False


def test_candidate_flow_trace_drops_stale_indicator_missing_gate_when_all_current_symbols_are_ready(tmp_path: Path):
    indicator = {
        "by_symbol": {
            "NIFTY": {"indicators_ok": True, "indicator_missing_inputs": []},
            "BANKNIFTY": {"ready": True, "indicator_missing_inputs": []},
            "SENSEX": {
                "rsi_present": True,
                "ema_present": True,
                "atr_present": True,
                "vwap_present": True,
                "indicator_missing_inputs": [],
            },
        }
    }
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "NIFTY"}, {"symbol": "BANKNIFTY"}, {"symbol": "SENSEX"}],
        cycle_blockers={"INDICATORS_MISSING": 3},
        indicator_readiness=indicator,
        regime_truth={"by_symbol": {}},
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    assert payload["indicator_ready_symbol_count"] == 3
    assert payload["indicator_blocked_symbol_count"] == 0
    assert "INDICATORS_MISSING" not in payload["gate_reasons"]
    assert payload["first_zero_stage"] == "strategy_generation_zero"


def test_candidate_flow_trace_regime_blocked_when_indicators_ready_but_all_symbols_unstable(tmp_path: Path):
    indicator = {"by_symbol": {"SENSEX": {"ready": True}}}
    regime = {"by_symbol": {"SENSEX": {"unstable_reasons": ["x"]}}, "gate_reasons": {"REGIME_UNSTABLE": 1}}
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={"REGIME_UNSTABLE": 1},
        indicator_readiness=indicator,
        regime_truth=regime,
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    assert payload["indicator_ready_symbol_count"] == 1
    assert payload["regime_blocked_symbol_count"] == 1
    assert payload["regime_ready_symbol_count"] == 0
    assert payload["first_zero_stage"] == "regime_blocked"
    assert payload["by_symbol"]["SENSEX"]["regime_blocked"] is True


def test_candidate_flow_trace_nonempty_regime_payload_without_unstable_reasons_is_not_blocked(tmp_path: Path):
    indicator = {"by_symbol": {"SENSEX": {"indicators_ok": True}}}
    regime = {"by_symbol": {"SENSEX": {"primary_regime": "RANGE"}}, "gate_reasons": {}}
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={},
        indicator_readiness=indicator,
        regime_truth=regime,
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    assert payload["by_symbol"]["SENSEX"]["regime_blocked"] is False
    assert payload["regime_blocked_symbol_count"] == 0


def test_candidate_flow_trace_regime_blocked_when_decision_gate_reason_is_regime_unstable(tmp_path: Path):
    # The trace should not mark regime blocked just because regime payload exists; it needs explicit evidence.
    indicator = {"by_symbol": {"SENSEX": {"indicators_ok": True}}}
    regime = {"by_symbol": {}, "gate_reasons": {}}
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={"REGIME_UNSTABLE": 1},
        indicator_readiness=indicator,
        regime_truth=regime,
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
        decision_gate_reason_by_symbol={"SENSEX": "REGIME_UNSTABLE"},
    )
    assert payload["by_symbol"]["SENSEX"]["regime_blocked"] is True
    assert payload["first_zero_stage"] == "regime_blocked"


def test_candidate_flow_trace_strategy_generation_zero_when_raw_candidates_zero(tmp_path: Path):
    indicator = {"by_symbol": {"SENSEX": {"ready": True}}}
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={},
        indicator_readiness=indicator,
        regime_truth={"by_symbol": {}},
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    assert payload["first_zero_stage"] == "strategy_generation_zero"


def test_candidate_flow_trace_phase2_adapter_empty_when_raw_candidates_exist_but_phase2_empty(tmp_path: Path):
    indicator = {"by_symbol": {"SENSEX": {"ready": True}}}
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={},
        indicator_readiness=indicator,
        regime_truth={"by_symbol": {}},
        raw_candidate_count=3,
        phase2_input_candidate_count=0,
    )
    assert payload["raw_candidate_count"] == 3
    assert payload["phase2_input_candidate_count"] == 0
    assert payload["first_zero_stage"] == "phase2_adapter_empty"


def test_candidate_flow_trace_not_starved_when_phase2_input_nonzero(tmp_path: Path):
    indicator = {"by_symbol": {"SENSEX": {"ready": True}}}
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={},
        indicator_readiness=indicator,
        regime_truth={"by_symbol": {}},
        raw_candidate_count=3,
        phase2_input_candidate_count=1,
    )
    assert payload["first_zero_stage"] == "not_starved"


def test_candidate_flow_trace_includes_latency_guard_evidence_fields(tmp_path: Path):
    indicator = {"by_symbol": {"SENSEX": {"ready": True}}}
    latency_guard = {
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
    }
    payload = build_candidate_flow_trace_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=[{"symbol": "SENSEX"}],
        cycle_blockers={"LATENCY_GUARD_DEGRADE_EXIT_ONLY_PREBUILD_SKIP": 1},
        indicator_readiness=indicator,
        regime_truth={"by_symbol": {}},
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
        latency_guard=latency_guard,
    )
    assert payload["latency_guard_triggered"] is True
    assert payload["latency_guard_action"] == "DEGRADE_EXIT_ONLY"
    assert payload["latency_guard_metric"] == "total_loop.p95_ms"
    assert payload["latency_guard_value"] == 180.0
    assert payload["latency_guard_threshold"] == 120.0
    assert payload["starvation_summary"]["latency_guard"]["reason"] == "latency_sustained_breach"


def test_candidate_flow_trace_writer_writes_both_logs_and_runtime(tmp_path: Path):
    logs_path = tmp_path / "logs" / "candidate_flow_trace_latest.json"
    runtime_path = tmp_path / ".runtime" / "candidate_flow_trace_latest.json"
    payload = build_candidate_flow_trace_payload(
        execution_mode="SIM",
        market_open=False,
        market_data_list=[{"symbol": "NIFTY"}],
        cycle_blockers={},
        indicator_readiness={"by_symbol": {"NIFTY": {"ready": True}}},
        regime_truth={"by_symbol": {}},
        raw_candidate_count=0,
        phase2_input_candidate_count=0,
    )
    p_logs, p_runtime = write_candidate_flow_trace_latest(payload=payload, logs_path=logs_path, runtime_path=runtime_path)
    assert p_logs == logs_path
    assert p_runtime == runtime_path
    assert logs_path.exists()
    assert runtime_path.exists()
    written = json.loads(logs_path.read_text())
    assert written["schema_version"] == 1
    assert written["writer_name"] == "runtime_candidate_flow_trace"
