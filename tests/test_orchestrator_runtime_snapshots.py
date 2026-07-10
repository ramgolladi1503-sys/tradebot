from __future__ import annotations

import core.orchestrator as orch_mod


def test_produce_and_store_runtime_snapshots_is_engine_owned_and_writes(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        orch_mod,
        "produce_and_store_runtime_snapshots",
        lambda **kwargs: captured.setdefault("kwargs", dict(kwargs)),
    )

    orch_mod.produce_and_store_runtime_snapshots(
        market_snapshot={"source": "engine", "symbols": {}},
        producer="orchestrator_cycle",
        loop_id="loop-9",
    )

    assert captured["kwargs"]["producer"] == "orchestrator_cycle"
    assert captured["kwargs"]["market_snapshot"]["source"] == "engine"
    assert "cycle_feed_truth_payload" not in captured["kwargs"]


def test_orchestrator_threads_cycle_feed_truth_into_runtime_snapshots(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        orch_mod,
        "produce_and_store_runtime_snapshots",
        lambda **kwargs: captured.setdefault("kwargs", dict(kwargs)),
    )

    orch_mod.produce_and_store_runtime_snapshots(
        market_snapshot={"source": "engine", "symbols": {}},
        producer="orchestrator_cycle",
        loop_id="loop-9",
        cycle_feed_truth_payload={"feed_truth_state": "OK"},
    )

    assert captured["kwargs"]["cycle_feed_truth_payload"]["feed_truth_state"] == "OK"
