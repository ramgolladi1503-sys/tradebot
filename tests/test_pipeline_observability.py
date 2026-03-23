import json
from pathlib import Path

from config import config as cfg
from core.orchestrator import _build_pipeline_funnel_payload
from core.observability import pipeline


def test_pipeline_funnel_contains_expected_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(cfg, "PIPELINE_OBSERVABILITY_ENABLE", True, raising=False)
    funnel_path = tmp_path / "observability" / "pipeline_funnel.json"
    pipeline.write_pipeline_funnel(
        {
            "timestamp": "2026-03-15T10:00:00+00:00",
            "universe": 5,
            "candidates": 3,
            "scored": 3,
            "ready": 1,
            "executable": 1,
            "emitted": 1,
        }
    )
    payload = json.loads(funnel_path.read_text())
    for key in ("timestamp", "universe", "candidates", "scored", "ready", "executable", "emitted"):
        assert key in payload


def test_trade_lifecycle_events_append_for_blocked_and_emitted(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(cfg, "PIPELINE_OBSERVABILITY_ENABLE", True, raising=False)
    pipeline.append_trade_lifecycle_event(
        trade_id="T-BLOCKED",
        symbol="NIFTY",
        strategy="CORE",
        stage="readiness_gating",
        status="blocked",
        reason="missing_entry",
    )
    pipeline.append_trade_lifecycle_event(
        trade_id="T-EMITTED",
        symbol="NIFTY",
        strategy="CORE",
        stage="emission_projection",
        status="emitted",
        reason="suggestions",
    )
    lifecycle_path = tmp_path / "observability" / "trade_lifecycle.jsonl"
    rows = [json.loads(line) for line in lifecycle_path.read_text().splitlines() if line.strip()]
    blocked = [row for row in rows if row.get("trade_id") == "T-BLOCKED"]
    emitted = [row for row in rows if row.get("trade_id") == "T-EMITTED"]
    assert blocked
    assert emitted


def test_pipeline_funnel_separates_candidate_creation_from_execution_counts():
    payload = _build_pipeline_funnel_payload(
        universe=3,
        candidates=7,
        scored=2,
        visible_counts={
            "visible_advisory_count": 1,
            "visible_queue_only_count": 1,
            "visible_ready_count": 0,
            "visible_executable_status_count": 0,
        },
        emitted=1,
        returned=1,
    )

    assert payload["candidates"] == 7
    assert payload["scored"] == 2
    assert payload["advisory"] == 1
    assert payload["queue_only"] == 1
    assert payload["executable"] == 0
    assert payload["returned"] == 1
