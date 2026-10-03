from __future__ import annotations

import json
import hashlib
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.advisory_schema import deserialize_advisory_row, serialize_advisory_row
from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot
from core.time_utils import now_ist
import core.runtime_snapshot_producer as producer


def _sample_advisory(*, trade_id: str = "ADV-1", timestamp: str = "2026-04-22T06:30:00Z") -> dict:
    return serialize_advisory_row(
        {
            "trade_id": trade_id,
            "strategy_id": "core",
            "advisory_id": trade_id,
            "symbol": "NIFTY",
            "strategy_name": "CORE",
            "timestamp": timestamp,
            "instrument_type": "OPT",
            "execution_entry": 72.8,
            "execution_entry_source": "ask",
            "execution_entry_status": "executable",
            "display_entry": 72.8,
            "display_entry_source": "ask",
            "display_entry_status": "displayable",
            "entry_reason": "execution_from_ask",
            "entry_clear_reason": None,
            "entry": 72.8,
            "entry_status": "displayable",
            "entry_source": "ask",
            "confidence": 0.71,
            "confidence_raw": 0.71,
            "confidence_model_raw": 0.77,
            "confidence_model_component": 0.77,
            "confidence_micro_component": 0.66,
            "confidence_micro_blend_method": "bounded_overlay",
            "confidence_after_micro": 0.75,
            "confidence_after_alpha": 0.73,
            "confidence_after_latency": 0.72,
            "confidence_before_soft_veto": 0.72,
            "confidence_after_soft_veto": 0.71,
            "confidence_penalty_soft_veto_total": 0.06,
            "confidence_penalty_soft_veto_reasons": ["premium_out_of_band"],
            "confidence_gate_threshold": 0.30,
            "confidence_raw_gate_threshold": 0.55,
            "confidence_final_gate_threshold": 0.30,
            "confidence_rejection_stage": "final_gate",
            "confidence_penalty": 0.0,
            "confidence_final": 0.71,
            "readiness": "QUEUE_ONLY",
            "blockers": ["DISPLAY_ENTRY_FALLBACK"],
            "hard_blockers": [],
            "soft_penalties": [],
            "warnings": ["DISPLAY_ENTRY_FALLBACK"],
            "quote_source": "tick_store",
            "quote_age_sec": 1.2,
            "decision_explain": ["unit_test_snapshot"],
            "market_open": True,
            "advisory_visible": True,
            "is_executable": False,
            "execution_status": "queue_only",
            "validation_issue_code": None,
            "display_max_age_sec": None,
            "execution_max_age_sec": None,
        }
    )


def _run_cas_spot_dependency_cycle(
    tmp_path, monkeypatch, *, spot: dict, stale_option: bool = True,
    generated_at: datetime | None = None,
):
    from core.cas_primitive_producer import CASPrimitiveStore

    eval_time = datetime(2026, 10, 2, 15, 14, tzinfo=timezone.utc)
    eval_epoch = eval_time.timestamp()
    source_sha = "a" * 40
    session_id = "cas-spot-dependency-test"
    store_path = tmp_path / "cas_primitives.json"
    store = CASPrimitiveStore(
        store_path, session_id=session_id, source_sha=source_sha, underlying_token=256265
    )

    def tick(price: float, event_epoch: float) -> dict:
        payload = {
            "instrument_token": 256265,
            "underlying_symbol": "NIFTY",
            "last_price": price,
            "volume": None,
            "oi": None,
            "source_timestamp_field": "exchange_timestamp",
            "source_timestamp_epoch": event_epoch,
        }
        digest = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        ).encode()).hexdigest()
        return {
            **payload,
            "timestamp_epoch": event_epoch,
            "timestamp_authority": "EXCHANGE_TIMESTAMP",
            "timestamp_source_field": "exchange_timestamp",
            "receive_timestamp_epoch": event_epoch,
            "timestamp_fallback_used": False,
            "source_event_id": f"fixture:cas:{256265}:{digest[:16]}",
            "source_event_sha256": digest,
            "source_event_payload": payload,
        }

    for name, target, price in (
        ("0915", datetime(2026, 10, 2, 9, 15, tzinfo=timezone(timedelta(hours=5, minutes=30))).timestamp(), 25000.0),
        ("1000", datetime(2026, 10, 2, 10, 0, tzinfo=timezone(timedelta(hours=5, minutes=30))).timestamp(), 25100.0),
    ):
        store.capture(name, target, tick(price, target + 0.5), capture_timestamp_ist=eval_time.isoformat())

    raw_age = spot.get("age", 0.2)
    safe_age = raw_age if isinstance(raw_age, (int, float)) and not isinstance(raw_age, bool) else 0.2
    nifty = build_symbol_market_snapshot(
        spot=25100.0,
        ltp=25100.0,
        feed_health={
            "status": spot.get("status", "HEALTHY"),
            "underlying_quote_age_sec": safe_age,
        },
        quote_truth={
            "symbol": spot.get("quote_symbol", "NIFTY"),
            "instrument_token": spot.get("token", 256265),
            "is_fresh": spot.get("fresh", True),
            "is_executable_quote": spot.get("executable", False),
        },
    )
    symbols = {"NIFTY": nifty}
    if stale_option:
        symbols["NIFTY26OCT25000CE"] = build_symbol_market_snapshot(
            spot=25100.0,
            ltp=100.0,
            feed_health={"status": "STALE", "underlying_quote_age_sec": 900.0},
            quote_truth={
                "symbol": "NIFTY26OCT25000CE",
                "instrument_token": 999001,
                "is_fresh": False,
                "is_executable_quote": False,
            },
        )
    market_snapshot = build_market_snapshot(
        generated_at=(generated_at or eval_time).isoformat(),
        market_open=True,
        symbols_payload=symbols,
        warnings=[],
        compute_ms=1.0,
        loop_id="cas-spot-dependency-test",
    )
    if spot.get("remove_quote_truth"):
        market_snapshot["symbols"]["NIFTY"].pop("quote_truth", None)
    if spot.get("remove_nifty"):
        market_snapshot["symbols"].pop("NIFTY", None)
    if spot.get("snapshot_timestamp_override") is not None:
        market_snapshot["generated_at"] = spot["snapshot_timestamp_override"]

    if "raw_age_override" in spot:
        # Keep deliberately malformed raw dependency evidence for the fail-closed gate.
        market_snapshot["symbols"]["NIFTY"]["feed_health"]["underlying_quote_age_sec"] = spot["raw_age_override"]
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", runtime_root / "market_snapshot.json")
    monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", runtime_root / "advisory_latest.json")
    monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", runtime_root / "feed_runtime_latest.json")
    monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", runtime_root / "token_resolution_latest.json")
    monkeypatch.setattr(producer, "_build_advisory_latest_payload", lambda **_: {
        "rows": [], "row_count": 0, "source_path": "", "notes": []
    })
    monkeypatch.setattr(producer, "_build_and_write_canonical_ranked_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(producer, "stages_build_feed_health_truth_latest_payload", lambda payload: (
        {"feed_ok": True, "feed_truth_state": "OK", "feed_truth_strict_live": True},
        type("Decision", (), {"to_payload": lambda self: {"feed_ok": True}})(),
    ))
    monkeypatch.setattr(producer, "load_current_feed_runtime", lambda path: {
        "valid": True,
        "payload": {
            "ws_connected": spot.get("transport", True),
            **(
                {}
                if spot.get("omit_effective_transport")
                else {
                    "effective_ws_connected": spot.get(
                        "effective_transport", spot.get("transport", True)
                    )
                }
            ),
        },
    })
    monkeypatch.setattr(producer.time, "time", lambda: eval_epoch)
    monkeypatch.setattr(producer, "now_ist", lambda: eval_time)

    outputs = producer.produce_and_store_runtime_snapshots(
        market_snapshot=market_snapshot,
        producer="unit_test",
        loop_id="cas-spot-dependency-test:1",
        session_id=session_id,
        source_sha=source_sha,
        trading_session_identity={
            "trading_date": "2026-10-02",
            "venue": "NSE",
            "calendar_id": "fixture-calendar",
            "calendar_version": "fixture-v1",
        },
        cas_primitive_path=store_path,
    )
    return outputs, eval_time, source_sha


def test_scenario_c_stale_option_does_not_block_fresh_nifty_cas_advisory(tmp_path, monkeypatch):
    from core.read_only_consumer_cycle import _evaluate_cas

    outputs, eval_time, source_sha = _run_cas_spot_dependency_cycle(
        tmp_path, monkeypatch, spot={"status": "HEALTHY", "age": 0.2, "fresh": True}
    )

    assert outputs["cas_input_gate"]["state"] == "READY"
    assert outputs["cas_input_gate"]["required_domain"] == "INDEX_SPOT"
    assert outputs["market_snapshot"]["symbols"]["NIFTY26OCT25000CE"]["feed_health"]["status"] == "STALE"
    result = _evaluate_cas(
        runtime_outputs=outputs,
        output_root=tmp_path / "consumer",
        session_id="cas-spot-dependency-test",
        source_sha=source_sha,
        now=eval_time,
    )

    assert result["verdict"] == "PASS"
    assert result["decision"]["execution_status"] == "advisory_only"
    artifact = json.loads((tmp_path / "consumer" / "cas_v2_artifact.json").read_text())
    assert artifact["read_only"] is True
    assert artifact["live_execution_authorized"] is False
    assert artifact["paper_authorized"] is False
    assert artifact["broker_order_calls"] == 0


@pytest.mark.parametrize(
    ("spot", "generated_at", "expected_reason"),
    [
        ({"status": "STALE", "age": 60.0, "fresh": False}, None, "cas_required_spot_unhealthy"),
        ({"status": "HEALTHY", "raw_age_override": True, "fresh": True}, None, "cas_required_spot_age_invalid"),
        ({"status": "HEALTHY", "raw_age_override": "0.2", "fresh": True}, None, "cas_required_spot_age_invalid"),
        ({"status": "HEALTHY", "age": 0.2, "fresh": True, "token": 256266}, None, "cas_required_spot_identity_mismatch"),
        ({"status": "HEALTHY", "age": 0.2, "fresh": False}, None, "cas_required_spot_unhealthy"),
        (
            {"status": "HEALTHY", "age": 0.2, "fresh": True},
            datetime(2026, 10, 2, 15, 13, 56, tzinfo=timezone.utc),
            "cas_spot_snapshot_stale",
        ),
    ],
)
def test_scenario_d_unhealthy_or_unbound_nifty_blocks_cas_evaluator(
    tmp_path, monkeypatch, spot, generated_at, expected_reason
):
    from core.read_only_consumer_cycle import _evaluate_cas

    outputs, eval_time, source_sha = _run_cas_spot_dependency_cycle(
        tmp_path, monkeypatch, spot=spot, generated_at=generated_at
    )

    assert "cas_short_horizon_inputs" not in outputs
    assert outputs["cas_input_gate"]["state"] == "BLOCKED"
    assert outputs["cas_input_gate"]["reason_code"] == expected_reason
    result = _evaluate_cas(
        runtime_outputs=outputs,
        output_root=tmp_path / "consumer",
        session_id="cas-spot-dependency-test",
        source_sha=source_sha,
        now=eval_time,
    )
    assert result["verdict"] == "PENDING"
    assert result["reason"] == "short_horizon_inputs_missing"
    assert not (tmp_path / "consumer" / "cas_v2_artifact.json").exists()


def test_runtime_snapshot_producer_classifies_feed_truth_once_per_cycle(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    market_snapshot = build_market_snapshot(
        generated_at="2026-03-10T12:00:00Z",
        market_open=True,
        symbols_payload={"NIFTY": build_symbol_market_snapshot(spot=22500.0, ltp=22510.0)},
        warnings=[],
        compute_ms=3.0,
        loop_id="loop-1",
    )
    (logs_root / "suggestions.jsonl").write_text(json.dumps(_sample_advisory()) + "\n", encoding="utf-8")
    (logs_root / "feed_runtime_latest.json").write_text(json.dumps({"ws_connected": True}), encoding="utf-8")
    (logs_root / "token_resolution.json").write_text(json.dumps({"NIFTY": {"instrument_token": 123}}), encoding="utf-8")

    calls = {"truth": 0}

    def _build_truth(feed_payload):
        calls["truth"] += 1
        payload = {"feed_ok": True, "feed_truth_state": "OK", "feed_truth_strict_live": True}
        return payload, SimpleNamespace(to_payload=lambda: dict(payload))

    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", runtime_root / "market_snapshot.json")
    monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", runtime_root / "advisory_latest.json")
    monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", runtime_root / "feed_runtime_latest.json")
    monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", runtime_root / "token_resolution_latest.json")
    monkeypatch.setattr(producer, "_build_advisory_latest_payload", lambda limit=200: {"rows": [], "row_count": 0, "source_path": "", "notes": []})
    monkeypatch.setattr(producer, "_build_and_write_canonical_ranked_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(producer, "stages_build_feed_health_truth_latest_payload", _build_truth)

    outputs = producer.produce_and_store_runtime_snapshots(
        market_snapshot=market_snapshot,
        producer="unit_test",
        loop_id="loop-1",
    )

    assert calls["truth"] == 1
    assert outputs["feed_health_truth_latest"]["feed_truth_state"] == "OK"


def test_runtime_snapshot_uses_verified_same_day_cas_reference_after_restart(tmp_path, monkeypatch):
    from core.cas_primitive_producer import CASPrimitiveStore
    from core.market_heritage_graph import (
        load_same_session_cas_references,
        publish_same_session_cas_manifest,
    )

    run_root = tmp_path / "run-a"
    run_root.mkdir()
    source_sha = "1" * 40
    session_date = (date.today() - timedelta(days=1)).isoformat()
    session = {"trading_date": session_date, "venue": "NSE",
        "calendar_id": "fixture-calendar", "calendar_version": "v1"}
    store = CASPrimitiveStore(run_root / "cas.json", session_id="run-a",
        source_sha=source_sha, underlying_token=256265)

    def tick(price, epoch, run_id="run-a"):
        payload = {"instrument_token": 256265, "underlying_symbol": "NIFTY",
            "last_price": price, "volume": 10, "oi": 20,
            "source_timestamp_field": "exchange_timestamp",
            "source_timestamp_epoch": epoch}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True,
            separators=(",", ":"), default=str).encode()).hexdigest()
        return {**payload, "timestamp_epoch": epoch,
            "timestamp_authority": "EXCHANGE_TIMESTAMP",
            "timestamp_source_field": "exchange_timestamp",
            "receive_timestamp_epoch": epoch, "timestamp_fallback_used": False,
            "source_event_id": f"feed:{run_id}:1:256265:{digest[:16]}",
            "source_event_sha256": digest, "source_event_payload": payload}

    target_0915 = datetime.fromisoformat(f"{session_date}T09:15:00+05:30").timestamp()
    target_1000 = datetime.fromisoformat(f"{session_date}T10:00:00+05:30").timestamp()
    store.capture("0915", target_0915, tick(25000.0, target_0915 + 0.5), capture_timestamp_ist="09:15")
    store.capture("1000", target_1000, tick(25100.0, target_1000 + 0.5), capture_timestamp_ist="10:00")
    heritage_root = tmp_path / "heritage"
    assert publish_same_session_cas_manifest(heritage_root=heritage_root,
        session_identity=session, run_id="run-a", source_sha=source_sha,
        underlying_token=256265, primitives=store.rows)["status"] == "PUBLISHED"
    inherited = load_same_session_cas_references(heritage_root=heritage_root,
        session_identity=session, current_run_id="run-b", source_sha=source_sha,
        underlying_token=256265)

    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    market_snapshot = build_market_snapshot(
        generated_at=now_ist().isoformat(), market_open=True,
        symbols_payload={"NIFTY": build_symbol_market_snapshot(
            spot=22500.0, ltp=22510.0,
            feed_health={"status": "HEALTHY", "underlying_quote_age_sec": 0.2},
            quote_truth={"symbol": "NIFTY", "instrument_token": 256265,
                         "is_fresh": True, "is_executable_quote": False},
        )},
        warnings=[], compute_ms=3.0, loop_id="loop-inherited")
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", runtime_root / "market_snapshot.json")
    monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", runtime_root / "advisory_latest.json")
    monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", runtime_root / "feed_runtime_latest.json")
    monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", runtime_root / "token_resolution_latest.json")
    monkeypatch.setattr(producer, "_build_advisory_latest_payload", lambda limit=200: {"rows": [], "row_count": 0, "source_path": "", "notes": []})
    monkeypatch.setattr(producer, "_build_and_write_canonical_ranked_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(producer, "stages_build_feed_health_truth_latest_payload", lambda payload: (
        {"feed_ok": True, "feed_truth_state": "OK", "feed_truth_strict_live": True},
        SimpleNamespace(to_payload=lambda: {"feed_ok": True})))
    monkeypatch.setattr(producer, "load_current_feed_runtime", lambda path: {
        "valid": True, "payload": {"ws_connected": True}})
    epoch_offset = time.time() - datetime.now(timezone.utc).timestamp()
    monkeypatch.setattr(producer.time, "time", lambda: datetime.now(timezone.utc).timestamp() + epoch_offset)
    monkeypatch.setattr(producer, "now_ist", lambda: datetime.now(timezone.utc))

    outputs = producer.produce_and_store_runtime_snapshots(
        market_snapshot=market_snapshot, producer="unit_test", loop_id="run-b:1",
        session_id="run-b", source_sha=source_sha,
        inherited_cas_references=inherited["primitives"],
        trading_session_identity=session)
    assert outputs["cas_short_horizon_inputs"]["lineage_status"] == "INHERITED_VERIFIED"
    assert outputs["cas_short_horizon_inputs"]["session_id"] == "run-b"
    assert outputs["cas_short_horizon_inputs"]["source_run_ids"] == ["run-a"]

    current_path = runtime_root / "cas_short_horizon_primitives_run-b.json"
    current_store = CASPrimitiveStore(current_path, session_id="run-b",
        source_sha=source_sha, underlying_token=256265)
    current_store.capture("1000", target_1000, tick(25100.0, target_1000 + 0.5, "run-b"), capture_timestamp_ist="10:00")
    current_store.persist()
    market_snapshot["generated_at"] = now_ist().isoformat()
    mixed_outputs = producer.produce_and_store_runtime_snapshots(
        market_snapshot=market_snapshot, producer="unit_test", loop_id="run-b:2",
        session_id="run-b", source_sha=source_sha,
        inherited_cas_references=inherited["primitives"],
        trading_session_identity=session, cas_primitive_path=current_path)
    assert mixed_outputs["cas_input_gate"]["state"] == "READY"
    mixed = mixed_outputs["cas_short_horizon_inputs"]
    assert mixed["lineage_status"] == "SAME_SESSION_HERITAGE_VERIFIED"
    assert mixed["source_run_ids"] == ["run-a", "run-b"]
    assert mixed["lineage"]["0915"]["source_run_id"] == "run-a"
    assert mixed["lineage"]["1000"]["source_run_id"] == "run-b"
    current_store = CASPrimitiveStore(current_path, session_id="run-b",
        source_sha=source_sha, underlying_token=256265)
    current_store.capture("0915", target_0915, tick(25000.0, target_0915 + 0.5, "run-b"), capture_timestamp_ist="09:15")
    current_store.persist()
    market_snapshot["generated_at"] = now_ist().isoformat()
    mixed_outputs = producer.produce_and_store_runtime_snapshots(
        market_snapshot=market_snapshot, producer="unit_test", loop_id="run-b:2-retry",
        session_id="run-b", source_sha=source_sha,
        inherited_cas_references=inherited["primitives"],
        trading_session_identity=session, cas_primitive_path=current_path)
    assert mixed_outputs["cas_input_gate"]["state"] == "READY"
    assert mixed_outputs["cas_short_horizon_inputs"]["lineage_status"] == "CURRENT_RUN_VERIFIED"

    market_snapshot["generated_at"] = now_ist().isoformat()
    current_outputs = producer.produce_and_store_runtime_snapshots(
        market_snapshot=market_snapshot, producer="unit_test", loop_id="run-b:3",
        session_id="run-b", source_sha=source_sha,
        cas_primitive_path=current_path)
    assert current_outputs["cas_input_gate"]["state"] == "READY"
    assert current_outputs["cas_short_horizon_inputs"]["session_id"] == "run-b"
    assert "lineage_status" not in current_outputs["cas_short_horizon_inputs"]


def test_tail_jsonl_rows_uses_cache_when_file_is_unchanged(tmp_path, monkeypatch):
    import core.jsonl_tail_cache as tail_cache

    path = tmp_path / "events.jsonl"
    path.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf-8")
    tail_cache._TAIL_CACHE.clear()
    reads = {"count": 0}
    real_read_text = producer.Path.read_text

    def _read_text(self, *args, **kwargs):
        reads["count"] += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(producer.Path, "read_text", _read_text, raising=False)

    first = producer._tail_jsonl_rows(path, limit=10)
    second = producer._tail_jsonl_rows(path, limit=10)

    assert first == second
    assert reads["count"] == 1


def test_tail_jsonl_rows_uses_sidecar_cache_after_memory_cache_clear(tmp_path, monkeypatch):
    import core.jsonl_tail_cache as tail_cache

    path = tmp_path / "events.jsonl"
    path.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf-8")
    monkeypatch.setattr(tail_cache, "runtime_dir", lambda: tmp_path / "runtime")
    tail_cache._TAIL_CACHE.clear()
    producer._tail_jsonl_rows(path, limit=10)
    tail_cache._TAIL_CACHE.clear()
    reads = {"count": 0}
    real_read_text = producer.Path.read_text

    def _read_text(self, *args, **kwargs):
        if self == path:
            reads["count"] += 1
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(producer.Path, "read_text", _read_text, raising=False)

    second = producer._tail_jsonl_rows(path, limit=10)

    assert second == ['{"id": 1}', '{"id": 2}']
    assert reads["count"] == 0


def test_runtime_snapshot_producer_accepts_shared_cycle_feed_truth(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    (logs_root / "suggestions.jsonl").write_text(json.dumps(_sample_advisory()) + "\n", encoding="utf-8")
    (logs_root / "feed_runtime_latest.json").write_text(json.dumps({"ws_connected": True}), encoding="utf-8")
    (logs_root / "token_resolution.json").write_text(json.dumps({"NIFTY": {"instrument_token": 123}}), encoding="utf-8")

    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", runtime_root / "market_snapshot.json")
    monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", runtime_root / "advisory_latest.json")
    monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", runtime_root / "feed_runtime_latest.json")
    monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", runtime_root / "token_resolution_latest.json")
    monkeypatch.setattr(producer, "stages_build_feed_health_truth_latest_payload", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not derive shared truth")))

    outputs = producer.produce_and_store_runtime_snapshots(
        market_snapshot={"source": "engine"},
        producer="unit_test",
        cycle_feed_truth_payload={"feed_truth_state": "OK", "feed_ok": True},
    )

    assert outputs["cycle_feed_truth_latest"]["feed_truth_state"] == "OK"
    assert outputs["runtime_cycle_context"]["feed_truth"]["feed_truth_state"] == "OK"


def test_runtime_snapshot_producer_writes_expected_structure(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    market_snapshot = build_market_snapshot(
        generated_at="2026-03-10T12:00:00Z",
        market_open=True,
        symbols_payload={"NIFTY": build_symbol_market_snapshot(spot=22500.0, ltp=22510.0)},
        warnings=[],
        compute_ms=3.0,
        loop_id="loop-1",
    )
    (logs_root / "suggestions.jsonl").write_text(json.dumps(_sample_advisory()) + "\n", encoding="utf-8")
    (logs_root / "feed_runtime_latest.json").write_text(json.dumps({"ws_connected": True}), encoding="utf-8")
    (logs_root / "token_resolution.json").write_text(json.dumps({"NIFTY": {"instrument_token": 123}}), encoding="utf-8")

    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", runtime_root / "market_snapshot.json")
    monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", runtime_root / "advisory_latest.json")
    monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", runtime_root / "feed_runtime_latest.json")
    monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", runtime_root / "token_resolution_latest.json")
    monkeypatch.setattr(producer.cfg, "UI_LIVE_ROW_REQUIRE_TODAY", False, raising=False)

    outputs = producer.produce_and_store_runtime_snapshots(
        market_snapshot=market_snapshot,
        producer="unit_test",
        loop_id="loop-1",
    )

    assert outputs["market_snapshot"]["source"] == "engine"
    assert outputs["ranked_pipeline_latest"]["source"] == "ranked_opportunity_pipeline_v1"
    advisory_wrapper = json.loads((runtime_root / "advisory_latest.json").read_text(encoding="utf-8"))
    assert advisory_wrapper["producer"] == "unit_test"
    assert advisory_wrapper["payload"]["row_count"] == 1
    assert advisory_wrapper["payload"]["rows"][0]["entry"] == 72.8
    assert advisory_wrapper["payload"]["rows"][0]["warnings"] == ["DISPLAY_ENTRY_FALLBACK"]
    # Invalid raw runtime input must not be exposed as an authoritative payload.
    assert json.loads((runtime_root / "feed_runtime_latest.json").read_text(encoding="utf-8"))["payload"] is None


def test_runtime_snapshot_producer_drops_stale_advisory_rows(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    current_row = _sample_advisory(trade_id="ADV-TODAY", timestamp="2026-04-22T06:30:00Z")
    stale_row = _sample_advisory(trade_id="ADV-STALE", timestamp="2026-04-09T07:13:15Z")
    (logs_root / "suggestions.jsonl").write_text(
        json.dumps(current_row) + "\n" + json.dumps(stale_row) + "\n",
        encoding="utf-8",
    )
    (logs_root / "feed_runtime_latest.json").write_text(json.dumps({"ws_connected": True}), encoding="utf-8")
    (logs_root / "token_resolution.json").write_text(json.dumps({"NIFTY": {"instrument_token": 123}}), encoding="utf-8")

    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", runtime_root / "market_snapshot.json")
    monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", runtime_root / "advisory_latest.json")
    monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", runtime_root / "feed_runtime_latest.json")
    monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", runtime_root / "token_resolution_latest.json")
    monkeypatch.setattr(producer, "now_ist", lambda: datetime(2026, 4, 22, 12, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(producer.cfg, "UI_LIVE_ROW_REQUIRE_TODAY", True, raising=False)

    producer.produce_and_store_runtime_snapshots(
        market_snapshot={"missing": True},
        producer="unit_test",
    )

    wrapped = json.loads((runtime_root / "advisory_latest.json").read_text(encoding="utf-8"))
    rows = wrapped["payload"]["rows"]
    assert [row["trade_id"] for row in rows] == ["ADV-TODAY"]
    assert wrapped["payload"]["row_count"] == 1
    assert any("stale_row_dropped:ADV-STALE" in note for note in wrapped["payload"]["notes"])


def test_runtime_snapshot_producer_falls_back_to_candidate_decisions_when_suggestions_are_stale(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    desk_log_root = logs_root / "desks" / "DEFAULT"
    desk_log_root.mkdir(parents=True, exist_ok=True)
    current_row = {
        "candidate_id": "LIVE-CAND-1",
        "ts_epoch": 1778047800.0,
        "ts_ist": "2026-05-06T12:00:00+05:30",
        "symbol": "NIFTY",
        "side": "BUY_CALL",
        "mode": "LIVE",
        "execution_allowed": False,
        "permission": "ADVISORY_ONLY",
        "permission_reason": "quote_not_ok",
        "first_blocking_gate": "premium_sanity",
        "entry_block_reason": "execution_from_ask",
        "gates_failed": ["premium_sanity", "stale_option_quote"],
        "soft_vetos": ["premium_sanity", "trade_score"],
        "entry": 123.45,
        "stop": 120.0,
        "target": 130.0,
        "confidence_score": 0.37,
        "quote_validation_status": "STALE_OPTION_LTP",
        "source_flags": {
            "ltp_source": "live",
            "quote_age_sec": 0.4,
            "market_open": True,
            "candidate_origin": {"setup_family": "breakout"},
        },
        "final_action": "QUEUE_ONLY",
        "rank_score": 0.48,
        "raw_rank_score": 0.48,
        "terminal_rank_score": 0.48,
        "liquidity_score": 0.79,
        "setup_score": 0.52,
        "trigger_score": 0.41,
    }
    (desk_log_root / "candidate_decisions.jsonl").write_text(json.dumps(current_row) + "\n", encoding="utf-8")
    stale_row = _sample_advisory(trade_id="ADV-STALE", timestamp="2026-04-09T07:13:15Z")
    (logs_root / "suggestions.jsonl").write_text(json.dumps(stale_row) + "\n", encoding="utf-8")
    (logs_root / "feed_runtime_latest.json").write_text(json.dumps({"ws_connected": True}), encoding="utf-8")
    (logs_root / "token_resolution.json").write_text(json.dumps({"NIFTY": {"instrument_token": 123}}), encoding="utf-8")

    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", runtime_root / "market_snapshot.json")
    monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", runtime_root / "advisory_latest.json")
    monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", runtime_root / "feed_runtime_latest.json")
    monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", runtime_root / "token_resolution_latest.json")
    monkeypatch.setattr(producer, "now_ist", lambda: datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc))
    monkeypatch.setattr(producer.cfg, "UI_LIVE_ROW_REQUIRE_TODAY", True, raising=False)
    monkeypatch.setattr(producer.cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE", True, raising=False)

    producer.produce_and_store_runtime_snapshots(
        market_snapshot={"missing": True},
        producer="unit_test",
    )

    wrapped = json.loads((runtime_root / "advisory_latest.json").read_text(encoding="utf-8"))
    rows = wrapped["payload"]["rows"]
    assert [row["trade_id"] for row in rows] == ["LIVE-CAND-1"]
    assert wrapped["payload"]["row_count"] == 1
    assert wrapped["payload"]["source_path"].endswith("candidate_decisions.jsonl")
    assert any("fallback_source:" in note for note in wrapped["payload"]["notes"])
    assert rows[0]["quote_source"] == "live"
    assert rows[0]["execution_status"] == "queue_only"
    assert wrapped["payload"]["source_state"] == "ROWS"
    assert wrapped["payload"]["primary_source_state"] == "PRESENT"


def test_runtime_snapshot_advisory_distinguishes_missing_and_empty_sources(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer.cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE", False, raising=False)

    missing = producer._build_advisory_latest_payload()
    assert missing["row_count"] == 0
    assert missing["source_state"] == "MISSING"

    primary = logs_root / "suggestions.jsonl"
    primary.parent.mkdir(parents=True)
    primary.write_text("\n", encoding="utf-8")
    empty = producer._build_advisory_latest_payload()
    assert empty["row_count"] == 0
    assert empty["source_state"] == "EMPTY"


def test_runtime_snapshot_advisory_reports_fallback_missing_separately(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    logs_root.mkdir()
    primary = logs_root / "suggestions.jsonl"
    primary.write_text("\n", encoding="utf-8")
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: primary)
    monkeypatch.setattr(producer.cfg, "DESK_ID", "DEFAULT", raising=False)
    monkeypatch.setattr(producer.cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE", True, raising=False)

    payload = producer._build_advisory_latest_payload()

    assert payload["row_count"] == 0
    assert payload["source_state"] == "MISSING"
    assert payload["primary_source_state"] == "EMPTY"
    assert payload["source_path"].endswith("desks/DEFAULT/candidate_decisions.jsonl")


def test_runtime_snapshot_advisory_does_not_route_unknown_desk_to_default(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    primary = logs_root / "suggestions.jsonl"
    primary.parent.mkdir(parents=True)
    primary.write_text("\n", encoding="utf-8")
    default_dir = logs_root / "desks" / "DEFAULT"
    default_dir.mkdir(parents=True)
    (default_dir / "candidate_decisions.jsonl").write_text(
        json.dumps({
            "candidate_id": "DEFAULT-ONLY",
            "symbol": "NIFTY",
            "entry": 100.0,
            "ts_epoch": 1790000000.0,
            "execution_allowed": False,
        }) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: primary)
    monkeypatch.setattr(producer.cfg, "DESK_ID", "UNREGISTERED_DESK", raising=False)
    monkeypatch.setattr(producer.cfg, "UI_LIVE_ROW_REQUIRE_TODAY", False, raising=False)
    monkeypatch.setattr(
        producer.cfg,
        "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE",
        True,
        raising=False,
    )

    payload = producer._build_advisory_latest_payload()

    assert payload["source_state"] == "MISSING"
    assert payload["row_count"] == 0
    assert payload["source_path"].endswith("desks/UNREGISTERED_DESK/candidate_decisions.jsonl")
    assert all(row.get("candidate_id") != "DEFAULT-ONLY" for row in payload["rows"])


def test_runtime_snapshot_advisory_reports_source_read_error(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    logs_root.mkdir()
    source = logs_root / "suggestions.jsonl"
    source.mkdir()
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: source)
    monkeypatch.setattr(producer.cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE", False, raising=False)

    payload = producer._build_advisory_latest_payload()

    assert payload["row_count"] == 0
    assert payload["source_state"] == "READ_ERROR"


def test_runtime_snapshot_advisory_reports_invalid_utf8_as_read_error(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    logs_root.mkdir()
    source = logs_root / "suggestions.jsonl"
    source.write_bytes(b"\xff\xfe\n")
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: source)
    monkeypatch.setattr(producer.cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE", False, raising=False)

    payload = producer._build_advisory_latest_payload()

    assert payload["row_count"] == 0
    assert payload["source_state"] == "READ_ERROR"


def test_runtime_snapshot_advisory_surfaces_truncated_jsonl_row(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    logs_root.mkdir()
    source = logs_root / "suggestions.jsonl"
    source.write_text('{"candidate_id":"partial"', encoding="utf-8")
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: source)
    monkeypatch.setattr(producer.cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE", False, raising=False)

    payload = producer._build_advisory_latest_payload()

    assert payload["row_count"] == 0
    assert payload["source_state"] == "PARTIAL"
    assert "incomplete_trailing_jsonl_record:primary" in payload["notes"]


def test_runtime_snapshot_advisory_uses_explicit_observer_decision_ledger(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    run_root = tmp_path / "sessions" / "run-1"
    run_root.mkdir(parents=True)
    observer_log = run_root / "candidate_decisions.jsonl"
    observer_log.write_text(json.dumps({
        "candidate_id": "RUN-CAND-1",
        "ts_epoch": 1778047800.0,
        "ts_ist": "2026-05-06T12:00:00+05:30",
        "symbol": "NIFTY",
        "entry": 123.45,
        "stop_loss": 120.0,
        "target": 130.0,
        "execution_allowed": False,
        "permission": "ADVISORY_ONLY",
        "final_action": "QUEUE_ONLY",
    }) + "\n", encoding="utf-8")
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer.cfg, "DESK_ID", "DEFAULT", raising=False)
    monkeypatch.setattr(producer.cfg, "UI_LIVE_ROW_REQUIRE_TODAY", False, raising=False)

    payload = producer._build_advisory_latest_payload(candidate_decisions_path=observer_log)

    assert [row["trade_id"] for row in payload["rows"]] == ["RUN-CAND-1"]
    assert payload["source_path"] == str(observer_log)
    assert payload["source_state"] == "ROWS"


def test_runtime_snapshot_advisory_excludes_unterminated_concurrent_tail(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    logs_root.mkdir()
    source = logs_root / "suggestions.jsonl"
    complete = _sample_advisory(trade_id="ADV-COMPLETE")
    partial = _sample_advisory(trade_id="ADV-PARTIAL")
    source.write_text(json.dumps(complete) + "\n" + json.dumps(partial), encoding="utf-8")
    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: source)
    monkeypatch.setattr(producer.cfg, "RUNTIME_SNAPSHOT_ADVISORY_FALLBACK_CANDIDATE_DECISIONS_ENABLE", False, raising=False)
    monkeypatch.setattr(producer.cfg, "UI_LIVE_ROW_REQUIRE_TODAY", False, raising=False)

    during_write = producer._build_advisory_latest_payload()
    with source.open("a", encoding="utf-8") as handle:
        handle.write("\n")
    after_write = producer._build_advisory_latest_payload()

    assert [row["trade_id"] for row in during_write["rows"]] == ["ADV-COMPLETE"]
    assert during_write["source_state"] == "ROWS_WITH_PARTIAL_TAIL"
    assert "incomplete_trailing_jsonl_record:primary" in during_write["notes"]
    assert [row["trade_id"] for row in after_write["rows"]] == ["ADV-COMPLETE", "ADV-PARTIAL"]
    assert after_write["source_state"] == "ROWS"


def test_runtime_snapshot_advisory_uses_one_snapshot_when_writer_appends_after_size_capture(tmp_path, monkeypatch):
    source = tmp_path / "candidate_decisions.jsonl"
    complete = _sample_advisory(trade_id="ADV-SNAPSHOT")
    appended = _sample_advisory(trade_id="ADV-APPENDED")
    source.write_text(json.dumps(complete) + "\n", encoding="utf-8")
    original_fstat = producer.os.fstat
    append_once = {"pending": True}

    def append_after_snapshot_size(fd):
        snapshot_stat = original_fstat(fd)
        if append_once["pending"]:
            append_once["pending"] = False
            with source.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(appended))
        return snapshot_stat

    monkeypatch.setattr(producer.os, "fstat", append_after_snapshot_size)
    rows, state = producer._read_advisory_source(source, limit=20)

    assert rows == []
    assert state == "READ_ERROR"
    next_rows, next_state = producer._read_advisory_source(source, limit=20)
    assert [json.loads(row)["trade_id"] for row in next_rows] == ["ADV-SNAPSHOT"]
    assert next_state == "PARTIAL"


def test_runtime_snapshot_advisory_fails_closed_on_in_place_rewrite_during_read(tmp_path, monkeypatch):
    source = tmp_path / "candidate_decisions.jsonl"
    source.write_bytes(b'{"id":"old"}\n')
    original_fstat = producer.os.fstat
    rewrite_once = {"pending": True}

    def rewrite_after_snapshot_size(fd):
        snapshot_stat = original_fstat(fd)
        if rewrite_once["pending"]:
            rewrite_once["pending"] = False
            source.write_bytes(b'{"id":"new"}\n')
        return snapshot_stat

    monkeypatch.setattr(producer.os, "fstat", rewrite_after_snapshot_size)

    rows, state = producer._read_advisory_source(source, limit=20)

    assert rows == []
    assert state == "READ_ERROR"


def test_runtime_snapshot_advisory_preserves_complete_rows_before_whitespace_tail(tmp_path):
    source = tmp_path / "candidate_decisions.jsonl"
    source.write_bytes(b'{"id":"complete"}\n ')

    rows, state = producer._read_advisory_source(source, limit=20)

    assert rows == ['{"id":"complete"}']
    assert state == "PARTIAL"


def test_runtime_snapshot_advisory_uses_lf_only_as_jsonl_record_delimiter(tmp_path):
    source = tmp_path / "candidate_decisions.jsonl"
    source.write_text('{"value":"left\u2028right"}\n', encoding="utf-8")

    rows, state = producer._read_advisory_source(source, limit=20)

    assert rows == ['{"value":"left\u2028right"}']
    assert json.loads(rows[0]) == {"value": "left\u2028right"}
    assert state == "PRESENT"


def test_runtime_snapshot_advisory_reports_overlong_single_record_as_truncated(tmp_path, monkeypatch):
    source = tmp_path / "candidate_decisions.jsonl"
    source.write_bytes((b"x" * 5000) + b"\n")
    monkeypatch.setattr(producer.cfg, "RUNTIME_SNAPSHOT_JSONL_TAIL_BYTES", 4096, raising=False)

    rows, state = producer._read_advisory_source(source, limit=20)

    assert rows == []
    assert state == "TRUNCATED"


def test_runtime_snapshot_advisory_roundtrip_preserves_required_fields(tmp_path, monkeypatch):
    runtime_root = tmp_path / "runtime"
    logs_root = runtime_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    advisory = _sample_advisory()
    (logs_root / "suggestions.jsonl").write_text(json.dumps(advisory) + "\n", encoding="utf-8")
    (logs_root / "feed_runtime_latest.json").write_text("{}", encoding="utf-8")
    (logs_root / "token_resolution.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(producer, "logs_dir", lambda: logs_root)
    monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: logs_root / "suggestions.jsonl")
    monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", runtime_root / "market_snapshot.json")
    monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", runtime_root / "advisory_latest.json")
    monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", runtime_root / "feed_runtime_latest.json")
    monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", runtime_root / "token_resolution_latest.json")
    monkeypatch.setattr(producer.cfg, "UI_LIVE_ROW_REQUIRE_TODAY", False, raising=False)

    producer.produce_and_store_runtime_snapshots(
        market_snapshot={"missing": True},
        producer="unit_test",
    )

    wrapped = json.loads((runtime_root / "advisory_latest.json").read_text(encoding="utf-8"))
    row = deserialize_advisory_row(wrapped["payload"]["rows"][0], allow_legacy=True)

    assert row["advisory_id"] == advisory["advisory_id"]
    assert row["entry"] == advisory["entry"]
    assert row["quote_source"] == advisory["quote_source"]
    assert row["warnings"] == advisory["warnings"]
    assert row["confidence_model_raw"] == advisory["confidence_model_raw"]
    assert row["confidence_model_component"] == advisory["confidence_model_component"]
    assert row["confidence_micro_component"] == advisory["confidence_micro_component"]
    assert row["confidence_micro_blend_method"] == advisory["confidence_micro_blend_method"]
    assert row["confidence_after_soft_veto"] == advisory["confidence_after_soft_veto"]
    assert row["confidence_penalty_soft_veto_total"] == advisory["confidence_penalty_soft_veto_total"]
    assert row["confidence_penalty_soft_veto_reasons"] == advisory["confidence_penalty_soft_veto_reasons"]
    assert row["confidence_gate_threshold"] == advisory["confidence_gate_threshold"]
    assert row["confidence_rejection_stage"] == advisory["confidence_rejection_stage"]
