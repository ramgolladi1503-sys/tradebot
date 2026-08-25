from __future__ import annotations

import json
from pathlib import Path

import core.canonical_cycle_coordinator as coordinator_module
from core.canonical_cycle_coordinator import CanonicalCycleCoordinator, COMPLETE, FAILED


def test_trigger_classes_and_cadence_are_deterministic(tmp_path: Path):
    owner = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha="a" * 40, cadence_seconds=10)
    assert owner.should_request(market_open=True, feed_live=True) == "MARKET_OPEN_INITIAL"
    owner.request("MARKET_OPEN_INITIAL")
    owner._last_started = 1
    assert owner.should_request(market_open=True, feed_live=True, now=9) is None
    assert owner.should_request(market_open=True, feed_live=True, now=11) == "NORMAL_CADENCE"
    assert owner.should_request(market_open=True, feed_live=True, feed_recovered=True, now=11) == "FEED_RECOVERY"
    assert owner.should_request(market_open=True, feed_live=True, feed_recovered=True, now=2) is None


def test_request_binds_cutoff_and_identity(tmp_path: Path):
    owner = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha="a" * 40)
    request = owner.request("FEED_RECOVERY")
    assert request.cycle_id.startswith("s:1:")
    assert request.source_sha == "a" * 40
    assert request.causal_data_cutoff.endswith("+00:00")


def test_failed_overlap_is_explicit_and_no_order_calls(tmp_path: Path):
    owner = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha="a" * 40)
    first = owner.request("MARKET_OPEN_INITIAL")
    assert owner._lock.acquire(False)
    try:
        failed = owner.run(first)
    finally:
        owner._lock.release()
    assert failed["state"] == FAILED
    assert failed["failure_class"] == "OVERLAPPING_CYCLE"
    assert failed["broker_order_calls"] == 0


def test_zero_trade_result_is_successful(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(coordinator_module, "produce_and_store_runtime_snapshots", lambda **_: {})
    monkeypatch.setattr(coordinator_module, "run_consumer_cycle", lambda **_: {"consumers": {}, "rejected_count": 0})
    owner = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha="a" * 40)
    result = owner.run(owner.request("MARKET_OPEN_INITIAL"))
    assert result["state"] == COMPLETE
    assert result["cycle_ok"] is True
    assert result["cycle_outcome"] == "NO_ELIGIBLE_CANDIDATE"
    history = json.loads((tmp_path / "canonical_cycle_latest.json").read_text())
    assert history["causal_data_cutoff"]
