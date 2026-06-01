from __future__ import annotations

import json
from pathlib import Path

from core.runtime_live_workload_evidence import (
    build_live_workload_payload,
    write_live_workload_latest,
)


def test_live_workload_payload_includes_strike_config_and_chain_counts(tmp_path: Path, monkeypatch):
    feed_runtime = {"subscribed_tokens_count": 10, "subscribed_option_tokens_count": 7}
    market_data_list = [
        {"symbol": "NIFTY", "option_chain": [{"strike": 1}, {"strike": 2}]},
        {"symbol": "BANKNIFTY", "option_chain": [{"strike": 1}]},
        {"symbol": "SENSEX", "option_chain": []},
    ]
    payload = build_live_workload_payload(
        execution_mode="LIVE",
        market_open=True,
        market_data_list=market_data_list,
        feed_runtime=feed_runtime,
        timing={"live_cycle_ms": 123.0, "fetch_live_market_data_ms": 7.0},
    )
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["execution_mode"] == "LIVE"
    assert payload["timing_detail_available"] is True
    assert payload["live_cycle_ms"] == 123.0
    assert payload["writer_schema_version"] == payload["schema_version"]
    assert payload["writer_name"] == "runtime_live_workload_evidence"
    assert "candidate_generation_ms" in payload
    assert "fetch_option_chain_ms" in payload
    assert "db_tick_read_query_count" in payload
    assert payload["option_chain_total_rows"] == 3
    assert payload["option_chain_rows_by_symbol"]["NIFTY"] == 2
    assert payload["option_chain_rows_by_symbol"]["BANKNIFTY"] == 1
    assert "configured_strikes_around_by_symbol" in payload
    assert payload["wide_live_universe_warning"] in (True, False)


def test_live_workload_writer_writes_both_logs_and_runtime(tmp_path: Path):
    logs_path = tmp_path / "logs" / "live_workload_latest.json"
    runtime_path = tmp_path / ".runtime" / "live_workload_latest.json"
    payload = build_live_workload_payload(
        execution_mode="SIM",
        market_open=False,
        market_data_list=[],
        feed_runtime={"subscribed_tokens_count": 0, "subscribed_option_tokens_count": 0},
    )
    assert payload["timing_detail_available"] is False
    assert payload["timing_detail_missing_reason"] == "orchestrator_timing_not_provided"
    assert "live_cycle_ms" in payload
    assert "fetch_option_chain_ms" in payload
    p_logs, p_runtime = write_live_workload_latest(payload=payload, logs_path=logs_path, runtime_path=runtime_path)
    assert p_logs == logs_path
    assert p_runtime == runtime_path
    assert logs_path.exists()
    assert runtime_path.exists()
    assert json.loads(logs_path.read_text())["schema_version"] == payload["schema_version"]
    assert json.loads(runtime_path.read_text())["schema_version"] == payload["schema_version"]
