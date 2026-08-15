from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

from core.advisory_schema import deserialize_advisory_row, serialize_advisory_row
from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot
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
