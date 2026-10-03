import json
import hashlib
import pytest
from core import read_only_consumer_cycle
from core.read_only_consumer_cycle import run_consumer_cycle, _evaluate_cas
from core.cas_primitive_producer import CASPrimitiveStore, build_cas_input
from datetime import datetime, timezone

SHA = "a" * 40
CAS_CLOSED_AUTHORITY = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "allowed_for_live_execution": False,
    "paper_authorized": False,
    "live_authorized": False,
    "append": False,
}

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
    readiness = json.loads((tmp_path / "cas_readiness_latest.json").read_text())
    artifact = json.loads((tmp_path / "cas_v2_artifact.json").read_text())
    assert {key: result[key] for key in CAS_CLOSED_AUTHORITY} == CAS_CLOSED_AUTHORITY
    assert {key: readiness[key] for key in CAS_CLOSED_AUTHORITY} == CAS_CLOSED_AUTHORITY
    assert {key: artifact[key] for key in CAS_CLOSED_AUTHORITY} == CAS_CLOSED_AUTHORITY

def test_cas_rejects_stale_entry_without_writing_artifact(tmp_path):
    result = _evaluate_cas(runtime_outputs={"cas_short_horizon_inputs": {"symbol": "NIFTY", "morning_return": -0.01, "observation_timestamp": "2026-08-31T15:14:00+00:00", "received_timestamp": "2026-08-31T15:14:02.001000+00:00"}}, output_root=tmp_path, session_id="s", source_sha=SHA, now=datetime(2026, 8, 31, 15, 14, tzinfo=timezone.utc))
    assert result["verdict"] == "PENDING"
    assert "late" in result["reason"]
    readiness = json.loads((tmp_path / "cas_readiness_latest.json").read_text())
    assert {key: result[key] for key in CAS_CLOSED_AUTHORITY} == CAS_CLOSED_AUTHORITY
    assert {key: readiness[key] for key in CAS_CLOSED_AUTHORITY} == CAS_CLOSED_AUTHORITY
    assert not (tmp_path / "cas_v2_artifact.json").exists()

def test_real_producer_input_reaches_real_cas_evaluator(tmp_path):
    store = CASPrimitiveStore(tmp_path / "primitives.json", session_id="s", source_sha=SHA, underlying_token=1)
    def tick(price, epoch):
        event_payload = {"instrument_token": 1, "underlying_symbol": "NIFTY", "last_price": price,
                         "volume": None, "oi": None, "source_timestamp_field": "exchange_timestamp",
                         "source_timestamp_epoch": epoch}
        event_sha = hashlib.sha256(json.dumps(event_payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
        return {"underlying_symbol": "NIFTY", "last_price": price, "timestamp_epoch": epoch,
                "timestamp_authority": "EXCHANGE_TIMESTAMP", "timestamp_source_field": "exchange_timestamp",
                "source_timestamp_epoch": epoch, "receive_timestamp_epoch": epoch,
                "timestamp_fallback_used": False, "instrument_token": 1,
                "source_event_id": f"fixture-feed:1:1:{event_sha[:16]}",
                "source_event_sha256": event_sha, "source_event_payload": event_payload}
    a = store.capture("0915", 100, tick(100, 100.5), capture_timestamp_ist="2026-08-31T15:14:00+00:00")
    b = store.capture("1000", 200, tick(110, 200.5), capture_timestamp_ist="2026-08-31T15:14:00+00:00")
    cas_input = build_cas_input(store.rows, session_id="s", source_sha=SHA, cycle_id="s:1:x")
    result = _evaluate_cas(runtime_outputs={"cas_short_horizon_inputs": cas_input}, output_root=tmp_path,
                           session_id="s", source_sha=SHA, now=datetime(2026, 8, 31, 15, 14, tzinfo=timezone.utc))
    assert result["verdict"] == "PASS"
    assert result["decision"]["direction"] == "DOWN"
    readiness = json.loads((tmp_path / "cas_readiness_latest.json").read_text())
    artifact = json.loads((tmp_path / "cas_v2_artifact.json").read_text())
    assert readiness["cycle_id"] == "s:1:x"
    assert {key: result[key] for key in CAS_CLOSED_AUTHORITY} == CAS_CLOSED_AUTHORITY
    assert {key: readiness[key] for key in CAS_CLOSED_AUTHORITY} == CAS_CLOSED_AUTHORITY
    assert {key: artifact[key] for key in CAS_CLOSED_AUTHORITY} == CAS_CLOSED_AUTHORITY


def test_completed_cas_source_event_pair_is_not_evaluated_again_after_restart(tmp_path, monkeypatch):
    from core.cas_primitive_producer import SPEC_SHA

    session_identity = {"trading_date": "2026-08-31", "venue": "NSE",
        "calendar_id": "fixture-calendar", "calendar_version": "v1"}
    events = ["b" * 64, "c" * 64]
    identity = hashlib.sha256(json.dumps({
        "strategy_id": "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1",
        "spec_sha": SPEC_SHA, "source_sha": SHA,
        "session_identity": session_identity,
        "source_event_sha256s": events,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    raw = {"strategy_id": "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1",
        "session_id": "run-a", "source_sha": SHA, "cycle_id": "run-a:1",
        "symbol": "NIFTY", "morning_return": -0.01,
        "observation_timestamp": "2026-08-31T15:14:00+00:00",
        "received_timestamp": "2026-08-31T15:14:00+00:00",
        "signal_input_09_15": 100.0, "signal_input_10_00": 99.0,
        "source_event_sha256s": events, "session_identity": session_identity,
        "evaluation_identity_sha256": identity}
    eval_calls = {"count": 0}
    real_evaluate = read_only_consumer_cycle.evaluate

    def count_evaluation(**kwargs):
        eval_calls["count"] += 1
        return real_evaluate(**kwargs)

    monkeypatch.setattr(read_only_consumer_cycle, "evaluate", count_evaluation)
    ledger_root = tmp_path / "session-heritage" / "cas-evaluations"
    first_root = tmp_path / "run-a"
    first = _evaluate_cas(runtime_outputs={"cas_short_horizon_inputs": raw},
        output_root=first_root, session_id="run-a", source_sha=SHA,
        now=datetime(2026, 8, 31, 15, 14, tzinfo=timezone.utc),
        evaluation_ledger_root=ledger_root)
    assert first["verdict"] == "PASS"

    second_root = tmp_path / "run-b"
    raw_b = {**raw, "session_id": "run-b", "cycle_id": "run-b:1"}
    second = _evaluate_cas(runtime_outputs={"cas_short_horizon_inputs": raw_b},
        output_root=second_root, session_id="run-b", source_sha=SHA,
        now=datetime(2026, 8, 31, 15, 14, 1, tzinfo=timezone.utc),
        evaluation_ledger_root=ledger_root)

    assert second["verdict"] == "PENDING"
    assert second["reason"] == "DUPLICATE_CAS_EVALUATION"
    closed_authority = CAS_CLOSED_AUTHORITY
    assert {key: second[key] for key in closed_authority} == closed_authority
    assert eval_calls["count"] == 1
    assert not (second_root / "cas_v2_artifact.json").exists()
    readiness = json.loads((second_root / "cas_readiness_latest.json").read_text())
    assert readiness["cas_invoked"] is False
    assert {key: readiness[key] for key in closed_authority} == closed_authority


@pytest.mark.parametrize("completion_mode", ["raise", "blocked"])
def test_cas_completion_failure_returns_closed_authority_without_artifact(
    tmp_path, monkeypatch, completion_mode,
):
    from core.cas_evaluation_ledger import CASEvaluationLedger
    from core.cas_primitive_producer import SPEC_SHA

    session_identity = {
        "trading_date": "2026-08-31", "venue": "NSE",
        "calendar_id": "fixture-calendar", "calendar_version": "v1",
    }
    events = ["d" * 64, "e" * 64]
    identity = hashlib.sha256(json.dumps({
        "strategy_id": "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1",
        "spec_sha": SPEC_SHA,
        "source_sha": SHA,
        "session_identity": session_identity,
        "source_event_sha256s": sorted(events),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    raw = {
        "strategy_id": "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1",
        "session_id": "run-a", "source_sha": SHA, "cycle_id": "run-a:1",
        "symbol": "NIFTY", "morning_return": -0.01,
        "observation_timestamp": "2026-08-31T15:14:00+00:00",
        "received_timestamp": "2026-08-31T15:14:00+00:00",
        "signal_input_09_15": 100.0, "signal_input_10_00": 99.0,
        "source_event_sha256s": events, "session_identity": session_identity,
        "evaluation_identity_sha256": identity,
    }

    def fail_completion(self, **_kwargs):
        if completion_mode == "raise":
            raise OSError("injected_completion_receipt_failure")
        return {"status": "BLOCKED", "reason": "injected_completion_receipt_block"}

    monkeypatch.setattr(CASEvaluationLedger, "complete", fail_completion)
    output_root = tmp_path / completion_mode
    result = _evaluate_cas(
        runtime_outputs={"cas_short_horizon_inputs": raw},
        output_root=output_root,
        session_id="run-a",
        source_sha=SHA,
        now=datetime(2026, 8, 31, 15, 14, tzinfo=timezone.utc),
        evaluation_ledger_root=tmp_path / "shared-ledger",
    )

    closed_authority = {
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "paper_authorized": False,
        "live_authorized": False,
        "append": False,
    }
    assert result["verdict"] == "PENDING"
    assert {key: result[key] for key in closed_authority} == closed_authority
    if completion_mode == "raise":
        assert result["reason"] == "CAS_EVALUATION_RECEIPT_WRITE_FAILED:OSError"
    else:
        assert result["reason"] == "injected_completion_receipt_block"
    assert not (output_root / "cas_readiness_latest.json").exists()
    assert not (output_root / "cas_v2_artifact.json").exists()
