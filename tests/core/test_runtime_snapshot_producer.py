from __future__ import annotations

import json
from datetime import datetime, timezone

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
    assert json.loads((runtime_root / "feed_runtime_latest.json").read_text(encoding="utf-8"))["payload"]["ws_connected"] is True


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
