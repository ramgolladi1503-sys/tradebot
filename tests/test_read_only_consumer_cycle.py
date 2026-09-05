import json
import pytest
from core.read_only_consumer_cycle import run_consumer_cycle, _evaluate_cas
from core.cas_primitive_producer import CASPrimitiveStore, build_cas_input
from datetime import datetime, timezone

SHA = "a" * 40

def ranked(*, cycle_id="s:1:x", session_id="s", source_sha=SHA, candidates=None):
    return {"cycle_provenance": {"cycle_id": cycle_id, "session_id": session_id, "source_sha": source_sha, "session_date": "2026-08-27"}, "reports": [{"candidate_pool": {"regime": {"primary_regime": "RANGE"}, "candidates": list(candidates or [])}}]}

def run(tmp_path, pipeline):
    return run_consumer_cycle(runtime_outputs={"ranked_pipeline_latest": pipeline, "advisory_latest": {"rows": [{"stale": True}]}}, output_root=tmp_path, session_id="s", source_sha=SHA, cycle_context={"cycle_id": "s:1:x", "causal_data_cutoff": "2026-08-27T09:15:00Z"})

def test_current_cycle_reports_are_the_only_input(tmp_path):
    result = run(tmp_path, ranked())
    assert result["current_cycle_input"]["stale_advisory_fallback_used"] is False
    assert result["consumers"]["regime"]["verdict"] == "PASS"
    assert result["consumers"]["strategies"]["candidate_count"] == 0
    assert result["broker_order_calls"] == 0

def test_missing_current_reports_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="CURRENT_CYCLE_RANKED_REPORTS_MISSING"):
        run(tmp_path, {"cycle_provenance": ranked()["cycle_provenance"], "reports": []})

def test_provenance_mismatch_fails_closed(tmp_path):
    with pytest.raises(ValueError, match="CURRENT_CYCLE_PROVENANCE_MISMATCH"):
        run(tmp_path, ranked(source_sha="b" * 40))

def test_stale_advisory_rows_are_not_used(tmp_path):
    result = run(tmp_path, ranked())
    assert result["consumers"]["candidate_pool"]["candidate_count"] == 0
    assert not (tmp_path / "advisory_queue.jsonl").exists()
    stored = json.loads((tmp_path / "consumer_cycle_latest.json").read_text())
    assert stored["current_cycle_input"]["report_count"] == 1

def test_cas_uses_short_horizon_causal_input_as_advisory(tmp_path):
    result = _evaluate_cas(runtime_outputs={"cas_short_horizon_inputs": {"symbol": "NIFTY", "morning_return": -0.01, "observation_timestamp": "2026-08-31T15:14:00+00:00", "signal_input_09_15": 100, "signal_input_10_00": 99}}, output_root=tmp_path, session_id="s", source_sha=SHA, now=datetime(2026, 8, 31, 15, 14, tzinfo=timezone.utc))
    assert result["verdict"] == "PASS"
    assert result["decision"]["execution_status"] == "advisory_only"
    assert (tmp_path / "cas_v2_artifact.json").exists()

def test_cas_rejects_stale_entry_without_writing_artifact(tmp_path):
    result = _evaluate_cas(runtime_outputs={"cas_short_horizon_inputs": {"symbol": "NIFTY", "morning_return": -0.01, "observation_timestamp": "2026-08-31T15:14:00+00:00", "received_timestamp": "2026-08-31T15:14:02.001000+00:00"}}, output_root=tmp_path, session_id="s", source_sha=SHA, now=datetime(2026, 8, 31, 15, 14, tzinfo=timezone.utc))
    assert result["verdict"] == "PENDING"
    assert "late" in result["reason"]
    assert not (tmp_path / "cas_v2_artifact.json").exists()

def test_real_producer_input_reaches_real_cas_evaluator(tmp_path):
    store = CASPrimitiveStore(tmp_path / "primitives.json", session_id="s", source_sha=SHA, underlying_token=1)
    def tick(price, epoch):
        return {"underlying_symbol": "NIFTY", "last_price": price, "timestamp_epoch": epoch,
                "timestamp_authority": "EXCHANGE_TIMESTAMP", "timestamp_source_field": "exchange_timestamp",
                "source_timestamp_epoch": epoch, "receive_timestamp_epoch": epoch + 1,
                "timestamp_fallback_used": False}
    a = store.capture("0915", 100, tick(100, 100.5), capture_timestamp_ist="2026-08-31T15:14:00+00:00")
    b = store.capture("1000", 200, tick(110, 200.5), capture_timestamp_ist="2026-08-31T15:14:00+00:00")
    cas_input = build_cas_input(store.rows, session_id="s", source_sha=SHA, cycle_id="s:1:x")
    result = _evaluate_cas(runtime_outputs={"cas_short_horizon_inputs": cas_input}, output_root=tmp_path,
                           session_id="s", source_sha=SHA, now=datetime(2026, 8, 31, 15, 14, tzinfo=timezone.utc))
    assert result["verdict"] == "PASS"
    assert result["decision"]["direction"] == "DOWN"
    assert json.loads((tmp_path / "cas_readiness_latest.json").read_text())["cycle_id"] == "s:1:x"
