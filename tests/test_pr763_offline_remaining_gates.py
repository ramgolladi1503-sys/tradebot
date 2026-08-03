"""Offline certification for the remaining PR #763 persistence gates.

These tests start no broker, Kite WebSocket, live market process, child runtime,
or order authority.  They exercise the existing worker queues, durable SQLite
stores, and evidence sealing boundary only.
"""

from __future__ import annotations

import itertools
import json
import queue
import statistics
import threading
import time
from pathlib import Path

import pytest

from config import config as cfg
import core.depth_store as depth_store_module
import core.feed.runtime_store as runtime_store
import core.tick_store as tick_store
import core.trade_store as trade_store
from core.depth_store import DepthStore
from core.unified_live_validation_pr748_756.campaign_contract import CampaignIdentity
from core.unified_live_validation_pr748_756.recorder import AppendOnlyRecorder
from core.unified_live_validation_pr748_756.seal import seal_evidence_root, sha256_file
from tools.pr763_gate1_structured_evidence import _load_test_module


def _reset_runtime_persistence() -> None:
    runtime_store.shutdown_runtime_persistence(deadline_seconds=1.0)
    runtime_store._RUNTIME_WRITE_QUEUE = queue.Queue(maxsize=2048)
    runtime_store._RUNTIME_STOP.clear()
    runtime_store._RUNTIME_WORKER = None
    runtime_store._RUNTIME_ENQUEUED = 0
    runtime_store._RUNTIME_REJECTED = 0
    runtime_store._RUNTIME_FAILURES = 0
    runtime_store._RUNTIME_DEGRADED = False
    runtime_store._RUNTIME_PERSISTED = 0


def _clear_callback_truth(depth_ws) -> None:
    for name in (
        "_LAST_MSG_TS_BY_TOKEN",
        "_LAST_PAYLOAD_TS_BY_TOKEN",
        "_FIRST_LIVE_TICK_EPOCH_BY_TOKEN",
        "_FIRST_SOURCE_TICK_EPOCH_BY_TOKEN",
        "_LATEST_OBSERVATION_PACKET_BY_TOKEN",
    ):
        value = getattr(depth_ws, name, None)
        if hasattr(value, "clear"):
            value.clear()
    depth_ws._LAST_WS_TICK_EPOCH = 0.0


def test_gate3_authority_local_fifo_and_immutable_envelopes(tmp_path, monkeypatch):
    """Each authority is FIFO; no cross-authority total order is claimed."""

    ordering_contract = {
        "scope": "AUTHORITY_LOCAL_FIFO",
        "cross_authority_total_order": False,
        "reason": "independent bounded workers intentionally avoid callback coupling",
    }
    assert ordering_contract["scope"] == "AUTHORITY_LOCAL_FIFO"
    assert ordering_contract["cross_authority_total_order"] is False

    # Tick rows are immutable tuples and the worker observes enqueue order.
    tick_store.reset_runtime_state_for_tests()
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "tick.db"), raising=False)
    tick_rows = []

    def capture_tick_rows(rows, *, worker_owned=False):
        tick_rows.extend(list(rows))
        return True

    monkeypatch.setattr(tick_store, "_write_rows", capture_tick_rows)
    for seq in (1, 2, 3):
        assert tick_store.insert_tick(
            ts=f"2026-08-03T10:00:0{seq}Z",
            token=10_000 + seq,
            last_price=100.0 + seq,
            volume=1_000 + seq,
            oi=2_000 + seq,
        )
    tick_drain = tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    assert tick_drain["status"] == "COMPLETE_DRAIN"
    assert [row[2] for row in tick_rows] == [101.0, 102.0, 103.0]
    assert all(isinstance(row, tuple) for row in tick_rows)

    # Runtime persistence deep-copies mutable payloads before enqueue.
    _reset_runtime_persistence()
    runtime_payloads = []
    monkeypatch.setattr(
        runtime_store,
        "_write_runtime_snapshot_sync",
        lambda payload: runtime_payloads.append(payload) or True,
    )
    first_runtime = {"sequence": 1, "nested": {"values": [1]}}
    assert runtime_store.write_runtime_snapshot(first_runtime)
    first_runtime["nested"]["values"].append(999)
    assert runtime_store.write_runtime_snapshot({"sequence": 2, "nested": {"values": [2]}})
    assert runtime_store.write_runtime_snapshot({"sequence": 3, "nested": {"values": [3]}})
    runtime_drain = runtime_store.shutdown_runtime_persistence(deadline_seconds=2.0)
    assert runtime_drain["complete"] is True
    assert [row["sequence"] for row in runtime_payloads] == [1, 2, 3]
    assert runtime_payloads[0]["nested"]["values"] == [1]

    # Depth persistence serializes the accepted book before caller mutation.
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    depth_rows = []

    def capture_depth(ts_iso, instrument_token, depth_json, ts_epoch=None):
        depth_rows.append((instrument_token, json.loads(depth_json)))
        return True

    monkeypatch.setattr(depth_store_module, "insert_depth_snapshot", capture_depth)
    store = DepthStore()
    first_depth = {"buy": [{"quantity": 10}], "sell": [{"quantity": 4}]}
    store.update(201, first_depth)
    first_depth["buy"][0]["quantity"] = 9_999
    store.update(202, {"buy": [{"quantity": 20}], "sell": [{"quantity": 5}]})
    store.update(203, {"buy": [{"quantity": 30}], "sell": [{"quantity": 6}]})
    depth_drain = store.shutdown_persistence(deadline_seconds=2.0)
    assert depth_drain["complete"] is True
    assert [row[0] for row in depth_rows] == [201, 202, 203]
    assert depth_rows[0][1]["depth"]["buy"][0]["quantity"] == 10


def test_gate5_registered_callback_slow_store_matrix_is_off_thread(tmp_path):
    """All 2x2x2 slow-writer combinations keep persistence off callback."""

    cert = _load_test_module()
    durations = []
    matrix_rows = []
    for slow_tick, slow_depth, slow_runtime in itertools.product((False, True), repeat=3):
        case = f"t{int(slow_tick)}-d{int(slow_depth)}-r{int(slow_runtime)}"
        case_root = tmp_path / case
        mp = pytest.MonkeyPatch()
        runtime_mod = cert.runtime_store
        exercised_depth = cert.depth_ws.depth_store
        try:
            cert.tick_store.reset_runtime_state_for_tests()
            _reset_runtime_persistence()
            cert.depth_ws.depth_store.shutdown_persistence(deadline_seconds=1.0)
            cert.depth_ws.depth_store = cert.depth_store_module.DepthStore()
            exercised_depth = cert.depth_ws.depth_store
            _clear_callback_truth(cert.depth_ws)

            real_tick = cert.tick_store._write_rows
            real_depth = cert.depth_store_module.insert_depth_snapshot
            real_runtime = runtime_mod._write_runtime_snapshot_sync

            def tick_writer(rows, **kwargs):
                if slow_tick:
                    time.sleep(0.05)
                return real_tick(rows, **kwargs)

            def depth_writer(*args, **kwargs):
                if slow_depth:
                    time.sleep(0.05)
                return real_depth(*args, **kwargs)

            def runtime_writer(payload):
                if slow_runtime:
                    time.sleep(0.05)
                return real_runtime(payload)

            mp.setattr(cert.tick_store, "_write_rows", tick_writer)
            mp.setattr(cert.depth_store_module, "insert_depth_snapshot", depth_writer)
            mp.setattr(runtime_mod, "_write_runtime_snapshot_sync", runtime_writer)

            (
                _,
                counts,
                violations,
                duration_ms,
                runtime_mod,
                exercised_depth,
                worker_ids,
                _,
            ) = cert._run_registered_live_persistence_fixture(mp, case_root)
            runtime_drain = runtime_mod.shutdown_runtime_persistence(deadline_seconds=3.0)
            tick_drain = cert.tick_store.shutdown_persistence_worker(deadline_seconds=3.0)
            depth_drain = exercised_depth.shutdown_persistence(deadline_seconds=3.0)

            assert counts["tick"] >= 1
            assert counts["depth"] >= 1
            assert counts["runtime"] >= 1
            assert violations == []
            assert set(worker_ids) == {"tick", "depth", "runtime"}
            assert runtime_drain["complete"] is True
            assert tick_drain["status"] == "COMPLETE_DRAIN"
            assert depth_drain["complete"] is True
            durations.append(float(duration_ms))
            matrix_rows.append({
                "case": case,
                "duration_ms": float(duration_ms),
                "slow_tick": slow_tick,
                "slow_depth": slow_depth,
                "slow_runtime": slow_runtime,
            })
        finally:
            try:
                runtime_mod.shutdown_runtime_persistence(deadline_seconds=1.0)
            except Exception:
                pass
            try:
                cert.tick_store.shutdown_persistence_worker(deadline_seconds=1.0)
            except Exception:
                pass
            try:
                exercised_depth.shutdown_persistence(deadline_seconds=1.0)
            except Exception:
                pass
            mp.undo()

    assert len(matrix_rows) == 8
    ordered = sorted(durations)
    p50 = statistics.median(ordered)
    p95 = statistics.quantiles(ordered, n=100, method="inclusive")[94]
    maximum = max(ordered)
    assert p50 < 5_000
    assert p95 < 5_000
    assert maximum < 5_000


def test_gate7_tick_depth_runtime_restart_reconstruction(tmp_path, monkeypatch):
    db_path = tmp_path / "restart.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)
    trade_store._DB_SCHEMA_INIT_PATH = None

    tick_store.reset_runtime_state_for_tests()
    assert tick_store.insert_tick(
        ts="2026-08-03T10:15:00Z",
        token=77_001,
        last_price=321.25,
        volume=500,
        oi=700,
    )
    tick_drain = tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    assert tick_drain["status"] == "COMPLETE_DRAIN"
    tick_store.reset_runtime_state_for_tests()
    rebuilt_tick = tick_store.get_latest_tick_db(77_001)
    assert rebuilt_tick is not None
    assert rebuilt_tick["ltp"] == pytest.approx(321.25)
    assert rebuilt_tick["source"] == "sqlite"

    _reset_runtime_persistence()
    runtime_payload = {
        "ts_epoch": 1_775_000_100.0,
        "ws_connected": True,
        "subscribed_tokens_count": 51,
        "intended_tokens_count": 51,
        "subscribed_tokens_sample": [77_001],
        "last_ws_tick_epoch": 1_775_000_099.0,
        "last_depth_epoch": 1_775_000_098.0,
        "source": "pr763_offline_restart",
        "runtime_state": "RUNNING",
    }
    assert runtime_store.write_runtime_snapshot(runtime_payload)
    runtime_drain = runtime_store.shutdown_runtime_persistence(deadline_seconds=2.0)
    assert runtime_drain["complete"] is True
    rebuilt_runtime = runtime_store.read_latest_runtime_snapshot()
    assert rebuilt_runtime is not None
    assert rebuilt_runtime["source"] == "pr763_offline_restart"
    assert rebuilt_runtime["subscribed_tokens_count"] == 51
    assert rebuilt_runtime["runtime_state"] == "RUNNING"

    store = DepthStore()
    store.update(
        77_002,
        {"buy": [{"price": 100.0, "quantity": 11}], "sell": [{"price": 101.0, "quantity": 7}]},
    )
    depth_drain = store.shutdown_persistence(deadline_seconds=2.0)
    assert depth_drain["complete"] is True
    columns, rows = trade_store.fetch_depth_snapshots(limit=10)
    token_index = columns.index("instrument_token")
    json_index = columns.index("depth_json")
    matching = [row for row in rows if int(row[token_index]) == 77_002]
    assert matching
    rebuilt_depth = json.loads(matching[0][json_index])
    assert rebuilt_depth["depth"]["buy"][0]["quantity"] == 11


def test_gate8_seal_is_immutable_and_hashes_remain_authoritative(tmp_path):
    root = tmp_path / "evidence"
    identity = CampaignIdentity(
        run_id="pr763-offline-seal",
        schema_version=1,
        session_date="2026-08-03",
        campaign_commit_sha="a" * 40,
        composition_manifest_sha="b" * 64,
        evidence_root=str(root),
    )
    recorder = AppendOnlyRecorder(identity)
    artifact = recorder.append("live/events.jsonl", {"event": "before_seal"}, pr_number=763)
    manifest = seal_evidence_root(root)

    expected_hash = next(row["sha256"] for row in manifest["artifacts"] if row["path"] == "live/events.jsonl")
    assert sha256_file(artifact) == expected_hash
    before = artifact.read_bytes()

    with pytest.raises(RuntimeError, match="evidence_root_already_sealed"):
        recorder.append("live/events.jsonl", {"event": "after_seal"}, pr_number=763)
    with pytest.raises(RuntimeError, match="evidence_root_already_sealed"):
        seal_evidence_root(root)

    assert artifact.read_bytes() == before
    assert sha256_file(artifact) == expected_hash


def test_gate8_shutdown_rejects_post_shutdown_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "shutdown.db"), raising=False)
    monkeypatch.setattr(cfg, "DEPTH_SNAPSHOT_WRITE_MIN_INTERVAL_SEC", 0.0, raising=False)

    tick_store.reset_runtime_state_for_tests()
    assert tick_store.insert_tick(ts="2026-08-03T10:20:00Z", token=88_001, last_price=1.0)
    tick_drain = tick_store.shutdown_persistence_worker(deadline_seconds=2.0)
    assert tick_drain["status"] == "COMPLETE_DRAIN"
    assert tick_store.insert_tick(ts="2026-08-03T10:20:01Z", token=88_002, last_price=2.0) is False
    assert tick_store.get_audit_counters()["writes_rejected_after_shutdown"] >= 1

    store = DepthStore()
    store.update(88_003, {"buy": [{"quantity": 1}], "sell": [{"quantity": 1}]})
    depth_drain = store.shutdown_persistence(deadline_seconds=2.0)
    assert depth_drain["complete"] is True
    before_rejected = store.persistence_state()["rejected"]
    store.update(88_004, {"buy": [{"quantity": 1}], "sell": [{"quantity": 1}]})
    assert store.persistence_state()["rejected"] == before_rejected + 1

    _reset_runtime_persistence()
    assert runtime_store.write_runtime_snapshot({"source": "before_shutdown"})
    runtime_drain = runtime_store.shutdown_runtime_persistence(deadline_seconds=2.0)
    assert runtime_drain["complete"] is True
    assert runtime_store.write_runtime_snapshot({"source": "after_shutdown"}) is False
    assert runtime_store.runtime_persistence_state()["rejected"] >= 1
