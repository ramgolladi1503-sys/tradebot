"""Deterministic V23 harness for the real CAS production call graph.

Only external filesystem/time boundaries are redirected. The snapshot producer,
coordinator, consumer, CAS evaluator, and readiness writer are production code.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.cas_primitive_producer import CASPrimitiveStore
from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot

SHA = "57e8717af1a2ddf06d443459b0f9797ea3b3f53f"


class ControlledRuntimeHarness:
    def __init__(self, tmp_path, monkeypatch, *, first_price: float, second_price: float, capture_0915: bool = True, capture_1000: bool = True, late: str | None = None, authority: str = "EXCHANGE_TIMESTAMP", risk_halt: bool = False):
        self.root = Path(tmp_path)
        self.logs = self.root / "logs"
        self.logs.mkdir(parents=True)
        self.session_id = "v23-session"
        self.first_price = first_price
        self.second_price = second_price
        self.capture_0915 = capture_0915
        self.capture_1000 = capture_1000
        self.late = late
        self.authority = authority
        self.risk_halt = risk_halt
        self.feed_healthy = True
        self._wire_external_boundaries(monkeypatch)

    def _wire_external_boundaries(self, monkeypatch):
        import core.canonical_cycle_coordinator as coordinator
        import core.read_only_consumer_cycle as consumer
        import core.runtime_snapshot_producer as producer
        import core.runtime_snapshot_store as store

        self.producer = producer
        self.consumer = consumer
        self.coordinator_module = coordinator
        self.runtime_root = self.root / "runtime"
        self.runtime_root.mkdir(exist_ok=True)
        monkeypatch.setattr(producer, "logs_dir", lambda: self.logs)
        monkeypatch.setattr(producer, "canonical_suggestions_log_path", lambda: self.logs / "suggestions.jsonl")
        monkeypatch.setattr(producer, "_build_advisory_latest_payload", lambda limit=200: {"rows": [], "row_count": 0, "source_path": "", "notes": []})
        monkeypatch.setattr(producer, "read_market_snapshot", lambda _: self.market_snapshot)
        monkeypatch.setattr(producer, "now_ist", lambda: datetime(2026, 9, 5, 15, 14, tzinfo=timezone.utc))
        monkeypatch.setattr(producer, "MARKET_SNAPSHOT_PATH", self.runtime_root / "market.json")
        monkeypatch.setattr(producer, "ADVISORY_LATEST_PATH", self.runtime_root / "advisory.json")
        monkeypatch.setattr(producer, "FEED_RUNTIME_LATEST_PATH", self.logs / "feed_runtime_latest.json")
        monkeypatch.setattr(producer, "load_current_feed_runtime", lambda *_args, **_kwargs: {
            "valid": self.feed_healthy,
            "payload": {"ws_connected": self.feed_healthy, "effective_ws_connected": self.feed_healthy}
            if self.feed_healthy else None,
            "reason_code": "VALID_CURRENT_ARTIFACT" if self.feed_healthy else "FEED_UNHEALTHY",
        })
        monkeypatch.setattr(producer, "TOKEN_RESOLUTION_LATEST_PATH", self.runtime_root / "token.json")
        monkeypatch.setattr(store, "RANKED_PIPELINE_LATEST_PATH", self.runtime_root / "ranked_pipeline_latest.json")
        monkeypatch.setattr(store, "RANKED_VS_LEGACY_LATEST_PATH", self.runtime_root / "ranked_vs_legacy_latest.json")
        class DecisionClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 9, 5, 15, 14, tzinfo=tz or timezone.utc)
        monkeypatch.setattr(consumer, "datetime", DecisionClock)
        monkeypatch.setattr(consumer.risk_halt.cfg, "RISK_HALT_FILE", str(self.root / "risk_halt.json"), raising=False)
        monkeypatch.setattr(coordinator, "produce_and_store_runtime_snapshots", producer.produce_and_store_runtime_snapshots)

    def start_preopen(self):
        self.market_snapshot = build_market_snapshot(
            generated_at="2026-09-05T10:01:00+05:30",
            market_open=True,
            symbols_payload={"NIFTY": build_symbol_market_snapshot(spot=25000.0, ltp=25001.0)},
            warnings=[], compute_ms=1.0, loop_id=self.session_id,
        )
        (self.logs / "feed_runtime_latest.json").write_text(json.dumps({
            "ws_connected": True, "effective_ws_connected": True,
            "runtime_state": "RUNNING", "feed_runtime_state": "LIVE",
        }))
        (self.logs / "token_resolution.json").write_text(json.dumps({"NIFTY": {"instrument_token": 1}}))
        if self.risk_halt:
            (self.root / "risk_halt.json").write_text(json.dumps({"halted": True, "reason": "V23_TEST_RISK_HALT", "timestamp_ist": "2026-09-05T12:00:00+05:30"}))
        self.store = CASPrimitiveStore(self.logs / f"cas_short_horizon_primitives_{self.session_id}.json", session_id=self.session_id, source_sha=SHA, underlying_token=1)
        self.cas_targets = {"0915": 100.0, "1000": 200.0}
        self.lifecycle_ticks = []
        def tick(price, epoch, **overrides):
            return {"underlying_symbol": "NIFTY", "instrument_token": 1, "last_price": price, "timestamp_epoch": epoch, "timestamp_authority": "EXCHANGE_TIMESTAMP", "timestamp_source_field": "exchange_timestamp", "source_timestamp_epoch": epoch, "receive_timestamp_epoch": epoch, "timestamp_fallback_used": False, **overrides}
        class Feed:
            def __init__(self): self.tick_sink = None
            def start_depth_ws(self, tokens, **kwargs): self.tick_sink = kwargs.get("tick_sink"); return True
            def stop_depth_ws(self, **kwargs): self.tick_sink = None
            def emit(self, value):
                if self.tick_sink is not None: self.tick_sink(value)
        from core.kite_read_only_observation_runtime import ObservationLifecycle
        self.feed = Feed()
        self.lifecycle = ObservationLifecycle(self.feed)
        def lifecycle_sink(value):
            self.lifecycle_ticks.append(dict(value))
            if value.get("underlying_symbol") != "NIFTY" or int(value.get("instrument_token") or 0) != 1:
                return
            for name, target in self.cas_targets.items():
                if name not in self.store.rows and value.get("timestamp_epoch") is not None and float(value["timestamp_epoch"]) >= target:
                    self.store.capture(name, target, value, capture_timestamp_ist="2026-09-05T09:15:00+05:30" if name == "0915" else "2026-09-05T10:00:00+05:30")
        self.lifecycle.start([1], tick_sink=lifecycle_sink)
        if self.capture_0915:
            timestamp = 102.001 if self.late == "0915" else 100.5
            self.emit_normalized_tick(tick(self.first_price, timestamp))
        if self.capture_1000:
            timestamp = 202.001 if self.late == "1000" else 200.5
            self.emit_normalized_tick(tick(self.second_price, timestamp, timestamp_authority=self.authority))

    def emit_normalized_tick(self, tick):
        self.feed.emit(dict(tick))

    def request_cycle(self):
        coordinator = self.coordinator_module.CanonicalCycleCoordinator(output_root=self.root / "out", session_id=self.session_id, source_sha=SHA)
        return coordinator.run(coordinator.request("MARKET_OPEN_INITIAL"))

    def inspect(self):
        consumer_path = self.root / "out" / "consumer_cycle_latest.json"
        consumer = json.loads(consumer_path.read_text())
        readiness = json.loads((self.root / "out" / "cas_readiness_latest.json").read_text())
        return consumer, readiness


def _tick(price=100.0, timestamp=100.5, **extra):
    return {
        "underlying_symbol": "NIFTY", "last_price": price,
        "timestamp_epoch": timestamp, "timestamp_authority": "EXCHANGE_TIMESTAMP",
        "timestamp_source_field": "exchange_timestamp",
        "source_timestamp_epoch": timestamp, "receive_timestamp_epoch": timestamp,
        "timestamp_fallback_used": False, **extra,
    }


def _store(tmp_path, *, session_id="s", source_sha=SHA, token=1):
    return CASPrimitiveStore(tmp_path / "primitives.json", session_id=session_id, source_sha=source_sha, underlying_token=token)


def test_v23_d_missing_0915_fails_closed(tmp_path):
    store = _store(tmp_path)
    store.capture("1000", 200, _tick(110, 200.5), capture_timestamp_ist="2026-09-05T10:00:00+05:30")
    assert store.rows["1000"]["capture_status"] == "CAPTURED"
    assert not store.rows.get("0915")


def test_v23_e_missing_1000_fails_closed(tmp_path):
    store = _store(tmp_path)
    store.capture("0915", 100, _tick(), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    assert store.rows["0915"]["capture_status"] == "CAPTURED"
    assert store.rows.get("1000") is None


def test_v23_f_late_tick_is_blocked(tmp_path):
    store = _store(tmp_path)
    row = store.capture("0915", 100, _tick(timestamp=102.001), capture_timestamp_ist="2026-09-05T09:15:02+05:30")
    assert row["capture_status"] == "BLOCKED"
    assert row["admissible_for_prospective_campaign"] is False


def test_v23_g_ineligible_timestamp_authority_is_blocked(tmp_path):
    store = _store(tmp_path)
    row = store.capture("0915", 100, _tick(timestamp_authority="GOVERNED_RECEIVE_TIMESTAMP"), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    assert row["capture_status"] == "BLOCKED"


def test_v23_h_duplicate_capture_is_immutable(tmp_path):
    store = _store(tmp_path)
    first = store.capture("0915", 100, _tick(100), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    second = store.capture("0915", 100, _tick(999), capture_timestamp_ist="2026-09-05T09:15:01+05:30")
    assert second == first


def test_v23_p_q_r_s_identity_and_hash_controls(tmp_path):
    store = _store(tmp_path)
    row = store.capture("0915", 100, _tick(), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    assert store.rows["0915"] == row
    assert store.rows["0915"]["source_sha"] == SHA
    assert store.rows["0915"]["session_id"] == "s"
    assert store.rows["0915"]["underlying_token"] == 1
    corrupted = dict(row, price=101.0)
    from core.cas_primitive_producer import verify_primitive
    assert verify_primitive(corrupted, session_id="s", source_sha=SHA, underlying_token=1)[0] is False


def test_v23_o_restart_reloads_without_recapture(tmp_path):
    store = _store(tmp_path)
    first = store.capture("0915", 100, _tick(), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    reloaded = CASPrimitiveStore(tmp_path / "primitives.json", session_id="s", source_sha=SHA, underlying_token=1)
    assert reloaded.rows["0915"] == first
    assert reloaded.capture("0915", 100, _tick(999), capture_timestamp_ist="2026-09-05T09:15:01+05:30") == first


def test_v23_t_malformed_input_fails_closed(tmp_path):
    from core.read_only_consumer_cycle import run_consumer_cycle
    with __import__("pytest").raises(ValueError, match="CURRENT_CYCLE_RANKED_REPORTS_MISSING"):
        run_consumer_cycle(runtime_outputs={"cas_short_horizon_inputs": {}}, output_root=tmp_path, session_id="s", source_sha=SHA, cycle_context={"cycle_id": "s:1:x"})


def test_v23_i_late_reconnect_does_not_recapture(tmp_path):
    store = _store(tmp_path)
    first = store.capture("0915", 100, _tick(), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    assert store.capture("0915", 100, _tick(999, 101), capture_timestamp_ist="2026-09-05T09:16:00+05:30") == first


def test_v23_j_risk_halt_provenance_is_read_only(monkeypatch, tmp_path):
    import core.read_only_consumer_cycle as consumer
    halt = tmp_path / "risk_halt.json"
    halt.write_text(json.dumps({"halted": True, "reason": "RISK_LIMIT", "timestamp_ist": "2026-09-05T12:00:00+05:30"}))
    monkeypatch.setattr(consumer.risk_halt.cfg, "RISK_HALT_FILE", str(halt), raising=False)
    evidence = consumer._risk_halt_evidence()
    assert evidence == {"risk_halt": True, "risk_halt_reason": "RISK_LIMIT", "risk_halt_timestamp": "2026-09-05T12:00:00+05:30"}
    assert json.loads(halt.read_text())["halted"] is True


def test_v23_k_unhealthy_feed_does_not_create_admissible_primitive(tmp_path):
    store = _store(tmp_path)
    row = store.capture("0915", 100, _tick(timestamp_authority="UNKNOWN"), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    assert row["capture_status"] == "BLOCKED"
    assert row["admissible_for_prospective_campaign"] is False


def test_v23_l_m_feed_recovery_request_is_single_owner(tmp_path):
    from core.canonical_cycle_coordinator import CanonicalCycleCoordinator
    c = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha=SHA)
    c._initial_requested = True
    c._last_started = 1
    assert c.should_request(market_open=True, feed_live=True, feed_recovered=True, now=1) == "FEED_RECOVERY"
    assert c.should_request(market_open=True, feed_live=True, feed_recovered=True, now=2) is None
    assert c.should_request(market_open=True, feed_live=True, feed_recovered=False, now=3) is None


def test_v23_n_shutdown_lifecycle_rejects_late_input(monkeypatch):
    from core.kite_read_only_observation_runtime import ObservationLifecycle
    class Feed:
        def __init__(self): self.tick_sink = None
        def start_depth_ws(self, *args, **kwargs):
            self.tick_sink = kwargs.get("tick_sink")
            return True
        def stop_depth_ws(self, **kwargs): return None
        def emit(self, tick):
            if self.tick_sink is not None: self.tick_sink(tick)
    seen = []
    lifecycle = ObservationLifecycle(Feed())
    lifecycle.start([1], tick_sink=seen.append)
    lifecycle.request_stop()
    assert lifecycle.accepting is False
    assert lifecycle.should_stop() is True


def test_v23_k_unhealthy_feed_suppresses_canonical_cycle(tmp_path):
    from core.canonical_cycle_coordinator import CanonicalCycleCoordinator
    coordinator = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha=SHA)
    assert coordinator.should_request(market_open=True, feed_live=False, now=1) is None


def test_v23_l_m_recovery_is_single_request_without_storm(tmp_path):
    from core.canonical_cycle_coordinator import CanonicalCycleCoordinator
    coordinator = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha=SHA)
    coordinator._initial_requested = True
    coordinator._last_started = 1
    assert coordinator.should_request(market_open=True, feed_live=True, feed_recovered=True, now=1) == "FEED_RECOVERY"
    assert [coordinator.should_request(market_open=True, feed_live=True, feed_recovered=True, now=t) for t in (2, 3, 4)] == [None, None, None]


def test_v23_u_preopen_arms_before_targets(tmp_path):
    store = _store(tmp_path)
    assert store.rows == {}
    store.capture("0915", 100, _tick(), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    assert store.rows["0915"]["capture_status"] == "CAPTURED"


def test_v23_v_late_start_cannot_backfill_0915(tmp_path):
    store = _store(tmp_path)
    row = store.capture("0915", 100, _tick(timestamp=103), capture_timestamp_ist="2026-09-05T09:16:00+05:30")
    assert row["capture_status"] == "BLOCKED"


def test_v23_w_start_after_both_windows_has_no_admission(tmp_path):
    store = _store(tmp_path)
    for name, target in (("0915", 100), ("1000", 200)):
        row = store.capture(name, target, _tick(timestamp=target + 2.001), capture_timestamp_ist="2026-09-05T15:00:00+05:30")
        assert row["admissible_for_prospective_campaign"] is False


def test_v23_x_restart_preserves_0915_and_allows_distinct_1000(tmp_path):
    store = _store(tmp_path)
    first = store.capture("0915", 100, _tick(100), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    restarted = CASPrimitiveStore(tmp_path / "primitives.json", session_id="s", source_sha=SHA, underlying_token=1)
    second = restarted.capture("1000", 200, _tick(110, 200.5), capture_timestamp_ist="2026-09-05T10:00:00+05:30")
    assert restarted.rows["0915"] == first
    assert second["capture_status"] == "CAPTURED"


def test_v23_m_continued_healthy_feed_has_no_recovery_storm(tmp_path):
    from core.canonical_cycle_coordinator import CanonicalCycleCoordinator
    c = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha=SHA)
    c._initial_requested = True
    c._last_started = 1
    assert c.should_request(market_open=True, feed_live=True, feed_recovered=True, now=1) == "FEED_RECOVERY"
    assert [c.should_request(market_open=True, feed_live=True, feed_recovered=True, now=n) for n in (2, 3, 4)] == [None, None, None]


def test_v23_q_wrong_session_is_rejected(tmp_path):
    store = _store(tmp_path)
    row = store.capture("0915", 100, _tick(), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    from core.cas_primitive_producer import verify_primitive
    assert verify_primitive(row, session_id="other", source_sha=SHA, underlying_token=1)[0] is False


def test_v23_r_wrong_token_is_rejected(tmp_path):
    store = _store(tmp_path)
    row = store.capture("0915", 100, _tick(), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    from core.cas_primitive_producer import verify_primitive
    assert verify_primitive(row, session_id="s", source_sha=SHA, underlying_token=2)[0] is False


def test_v23_s_corrupted_record_is_rejected(tmp_path):
    store = _store(tmp_path)
    row = store.capture("0915", 100, _tick(), capture_timestamp_ist="2026-09-05T09:15:00+05:30")
    from core.cas_primitive_producer import verify_primitive
    assert verify_primitive(dict(row, price=101.0), session_id="s", source_sha=SHA, underlying_token=1)[0] is False


def test_v23_a_valid_down_uses_real_coordinator_to_cas(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    result = h.request_cycle()
    consumer, readiness = h.inspect()
    assert result["state"] == "COMPLETE"
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PASS"
    assert json.loads((tmp_path / "out" / "cas_v2_artifact.json").read_text())["decision"]["direction"] == "DOWN"
    assert readiness["readiness_state"] == "READY"


def test_v23_b_valid_up_uses_real_coordinator_to_cas(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=110, second_price=100)
    h.start_preopen()
    h.request_cycle()
    consumer, _ = h.inspect()
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PASS"
    assert json.loads((tmp_path / "out" / "cas_v2_artifact.json").read_text())["decision"]["direction"] == "UP"


def test_v23_c_exact_zero_uses_real_coordinator_to_cas(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=100)
    h.start_preopen()
    h.request_cycle()
    consumer, readiness = h.inspect()
    artifact = json.loads((tmp_path / "out" / "cas_v2_artifact.json").read_text())
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PASS"
    assert artifact["decision"]["direction"] == "NO_SIGNAL"
    assert readiness["readiness_state"] == "NO_SIGNAL"


def test_v23_independent_verifier_reopens_emitted_evidence(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    h.request_cycle()
    consumer = json.loads((tmp_path / "out" / "consumer_cycle_latest.json").read_text())
    readiness = json.loads((tmp_path / "out" / "cas_readiness_latest.json").read_text())
    cas = json.loads((tmp_path / "out" / "cas_v2_artifact.json").read_text())
    ranked = json.loads((tmp_path / "runtime" / "ranked_pipeline_latest.json").read_text())["payload"]
    assert ranked["cycle_provenance"]["session_id"] == h.session_id
    assert ranked["cycle_provenance"]["source_sha"] == SHA
    assert consumer["session_id"] == h.session_id
    assert consumer["source_sha"] == SHA
    assert readiness["session_id"] == h.session_id
    assert readiness["source_sha"] == SHA
    assert cas["source_sha"] == SHA
    assert cas["decision"]["direction"] == "DOWN"
    assert cas["execution_status"] == "advisory_only"
    assert cas["broker_write_authority"] is False
    assert cas["order_authority"] is False
    assert cas["broker_order_calls"] == 0


def test_v23_d_missing_0915_uses_real_consumer_path(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110, capture_0915=False)
    h.start_preopen()
    h.request_cycle()
    consumer, readiness = h.inspect()
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PENDING"
    assert readiness["cas_short_horizon_inputs_present"] is False
    assert readiness["cas_invoked"] is False


def test_v23_e_missing_1000_uses_real_consumer_path(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110, capture_1000=False)
    h.start_preopen()
    h.request_cycle()
    consumer, readiness = h.inspect()
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PENDING"
    assert readiness["cas_short_horizon_inputs_present"] is False


def test_v23_f_late_0915_uses_real_producer_rejection(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110, late="0915")
    h.start_preopen()
    h.request_cycle()
    consumer, readiness = h.inspect()
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PENDING"
    assert readiness["cas_short_horizon_inputs_present"] is False


def test_v23_g_ineligible_1000_uses_real_producer_rejection(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110, authority="GOVERNED_RECEIVE_TIMESTAMP")
    h.start_preopen()
    h.request_cycle()
    _, readiness = h.inspect()
    assert readiness["cas_short_horizon_inputs_present"] is False


def test_v23_j_active_risk_halt_blocks_readiness_without_clearing(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110, risk_halt=True)
    h.start_preopen()
    h.request_cycle()
    _, readiness = h.inspect()
    assert readiness["readiness_state"] == "BLOCKED"
    assert readiness["risk_halt"] is True
    assert readiness["risk_halt_reason"] == "V23_TEST_RISK_HALT"
    assert json.loads((tmp_path / "risk_halt.json").read_text())["halted"] is True


def test_v23_k_unhealthy_feed_suppresses_cas_through_coordinator(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.feed_healthy = False
    h.start_preopen()
    h.request_cycle()
    consumer, readiness = h.inspect()
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PENDING"
    assert readiness["cas_short_horizon_inputs_present"] is False
    assert not (tmp_path / "out" / "cas_v2_artifact.json").exists()


def test_v23_l_feed_recovery_runs_one_real_cycle(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    coordinator = h.coordinator_module.CanonicalCycleCoordinator(
        output_root=tmp_path / "recovery-out", session_id=h.session_id, source_sha=SHA
    )
    calls = []
    original_run = coordinator.run
    monkeypatch.setattr(coordinator, "run", lambda request: calls.append(original_run(request)) or calls[-1])
    assert coordinator.should_request(market_open=True, feed_live=True, feed_recovered=True, now=1) == "FEED_RECOVERY"
    coordinator.run(coordinator.request("FEED_RECOVERY"))
    assert coordinator.should_request(market_open=True, feed_live=True, feed_recovered=True, now=2) is None
    assert len(calls) == 1
    assert calls[0]["state"] == "COMPLETE"


def test_v23_m_healthy_feed_has_no_recovery_storm_after_real_cycle(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    coordinator = h.coordinator_module.CanonicalCycleCoordinator(
        output_root=tmp_path / "recovery-out", session_id=h.session_id, source_sha=SHA
    )
    assert coordinator.should_request(market_open=True, feed_live=True, feed_recovered=True, now=1) == "FEED_RECOVERY"
    coordinator.run(coordinator.request("FEED_RECOVERY"))
    assert [coordinator.should_request(market_open=True, feed_live=True, feed_recovered=True, now=t) for t in (2, 3, 4)] == [None, None, None]


def test_v23_n_shutdown_lifecycle_prevents_new_cycle_and_capture(monkeypatch, tmp_path):
    from core.kite_read_only_observation_runtime import ObservationLifecycle

    class Feed:
        def __init__(self): self.tick_sink = None
        def start_depth_ws(self, *args, **kwargs):
            self.tick_sink = kwargs.get("tick_sink")
            return True
        def stop_depth_ws(self, **kwargs): return None
        def emit(self, tick):
            if self.tick_sink is not None: self.tick_sink(tick)

    feed = Feed()
    lifecycle = ObservationLifecycle(feed)
    captured = []
    lifecycle.start([1], tick_sink=captured.append)
    lifecycle.request_stop("v23_shutdown")
    # A callback arriving after shutdown must be rejected by the lifecycle.
    feed.emit(_tick())
    assert lifecycle.accepting is False
    assert lifecycle.should_stop() is True
    assert captured == []


def test_v23_readiness_transition_pending_to_ready_uses_same_cycle_path(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110, capture_0915=False, capture_1000=False)
    h.start_preopen()
    h.request_cycle()
    assert h.inspect()[1]["readiness_state"] == "PENDING"
    h.emit_normalized_tick(_tick(100, 100.5, instrument_token=1))
    h.emit_normalized_tick(_tick(110, 200.5, instrument_token=1))
    h.request_cycle()
    assert h.inspect()[1]["readiness_state"] == "READY"


def test_v23_i_reconnect_cycle_reuses_existing_primitive(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    first = json.loads((h.logs / f"cas_short_horizon_primitives_{h.session_id}.json").read_text())
    h.request_cycle()
    second = json.loads((h.logs / f"cas_short_horizon_primitives_{h.session_id}.json").read_text())
    assert second == first
    assert h.inspect()[0]["consumers"]["cas_v2"]["verdict"] == "PASS"


def test_v23_o_restart_cycle_reaches_cas_without_recapture(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    h.request_cycle()
    primitive_before = json.loads((h.logs / f"cas_short_horizon_primitives_{h.session_id}.json").read_text())
    h.request_cycle()
    primitive_after = json.loads((h.logs / f"cas_short_horizon_primitives_{h.session_id}.json").read_text())
    assert primitive_after == primitive_before
    assert h.inspect()[1]["readiness_state"] == "READY"


def test_v23_x_restart_between_targets_preserves_first_capture(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    h.request_cycle()
    store = CASPrimitiveStore(h.logs / f"cas_short_horizon_primitives_{h.session_id}.json", session_id=h.session_id, source_sha=SHA, underlying_token=1)
    first = store.rows["0915"]
    assert store.capture("0915", 100, _tick(999), capture_timestamp_ist="2026-09-05T09:16:00+05:30") == first
    assert h.inspect()[0]["consumers"]["cas_v2"]["verdict"] == "PASS"


def test_v23_h_duplicate_capture_reaches_coordinator_with_original_record(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    path = h.logs / f"cas_short_horizon_primitives_{h.session_id}.json"
    before = json.loads(path.read_text())["primitives"]["0915"]
    store = CASPrimitiveStore(path, session_id=h.session_id, source_sha=SHA, underlying_token=1)
    assert store.capture("0915", 100, _tick(999), capture_timestamp_ist="2026-09-05T09:16:00+05:30") == before
    h.request_cycle()
    assert h.inspect()[0]["consumers"]["cas_v2"]["verdict"] == "PASS"


def test_v23_u_preopen_armed_run_reaches_coordinator(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    h.request_cycle()
    assert h.inspect()[1]["readiness_state"] == "READY"


def test_v23_v_late_start_reaches_coordinator_without_backfill(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110, late="0915")
    h.start_preopen()
    h.request_cycle()
    consumer, readiness = h.inspect()
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PENDING"
    assert readiness["cas_short_horizon_inputs_present"] is False


def test_v23_w_late_start_both_targets_reaches_coordinator_without_admission(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110, late="0915")
    h.capture_1000 = False
    h.start_preopen()
    h.request_cycle()
    _, readiness = h.inspect()
    assert readiness["cas_short_horizon_inputs_present"] is False


def test_v23_x_restart_preserves_first_and_reaches_coordinator(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    path = h.logs / f"cas_short_horizon_primitives_{h.session_id}.json"
    first = json.loads(path.read_text())["primitives"]["0915"]
    restarted = CASPrimitiveStore(path, session_id=h.session_id, source_sha=SHA, underlying_token=1)
    assert restarted.rows["0915"] == first
    h.request_cycle()
    assert h.inspect()[1]["readiness_state"] == "READY"


def test_v23_p_q_r_s_corrupt_primitive_identity_fails_closed_at_coordinator(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    path = h.logs / f"cas_short_horizon_primitives_{h.session_id}.json"
    payload = json.loads(path.read_text())
    payload["primitives"]["0915"]["session_id"] = "wrong-session"
    path.write_text(json.dumps(payload))
    h.request_cycle()
    consumer, readiness = h.inspect()
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PENDING"
    assert readiness["cas_short_horizon_inputs_present"] is False
    assert not (tmp_path / "out" / "cas_v2_artifact.json").exists()


def test_v23_t_malformed_cas_input_fails_closed_through_coordinator(monkeypatch, tmp_path):
    h = ControlledRuntimeHarness(tmp_path, monkeypatch, first_price=100, second_price=110)
    h.start_preopen()
    original = h.coordinator_module.produce_and_store_runtime_snapshots

    def malformed(*args, **kwargs):
        outputs = original(*args, **kwargs)
        outputs["cas_short_horizon_inputs"] = {"symbol": "NIFTY", "morning_return": "not-a-number"}
        return outputs

    monkeypatch.setattr(h.coordinator_module, "produce_and_store_runtime_snapshots", malformed)
    h.request_cycle()
    consumer, readiness = h.inspect()
    assert consumer["consumers"]["cas_v2"]["verdict"] == "PENDING"
    assert readiness["readiness_state"] == "PENDING"
    assert not (tmp_path / "out" / "cas_v2_artifact.json").exists()
