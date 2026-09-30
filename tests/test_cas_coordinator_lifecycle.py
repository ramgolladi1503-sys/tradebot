from core.canonical_cycle_coordinator import CanonicalCycleCoordinator

def test_cas_coordinator_lifecycle_admission_is_single_owner(tmp_path):
    c = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha="x", cadence_seconds=60)
    assert c.should_request(market_open=False, feed_live=True, now=100) is None
    assert c.should_request(market_open=True, feed_live=False, now=100) is None
    assert c.should_request(market_open=True, feed_live=True, now=100) == "MARKET_OPEN_INITIAL"
    c._last_started = 100
    assert c.should_request(market_open=True, feed_live=True, feed_recovered=False, now=101) is None
    assert c.should_request(market_open=True, feed_live=True, feed_recovered=True, now=102) == "FEED_RECOVERY"
    assert c.should_request(market_open=True, feed_live=True, feed_recovered=True, now=103) is None
    assert c.should_request(market_open=True, feed_live=False, feed_recovered=True, now=104) is None

def test_cas_coordinator_requests_are_identity_bound(tmp_path):
    c = CanonicalCycleCoordinator(output_root=tmp_path, session_id="s", source_sha="x")
    req = c.request("MARKET_OPEN_INITIAL")
    assert (req.session_id, req.source_sha) == ("s", "x")
    assert req.cycle_id.startswith("s:1:")


def test_canonical_cycle_forwards_verified_heritage_to_snapshot_producer(tmp_path, monkeypatch):
    import core.canonical_cycle_coordinator as module

    seen = {}
    references = {"0915": {"lineage": {"lineage_status": "INHERITED_VERIFIED"}}}
    session = {"trading_date": "2026-09-29", "venue": "NSE",
        "calendar_id": "NSE-HIST", "calendar_version": "v1"}
    cas_path = tmp_path / "run" / "cas.json"
    coordinator = CanonicalCycleCoordinator(output_root=tmp_path,
        session_id="run-b", source_sha="a" * 40,
        inherited_cas_references=references,
        trading_session_identity=session,
        cas_primitive_path=cas_path)

    def produce(**kwargs):
        seen.update(kwargs)
        return {}

    monkeypatch.setattr(module, "produce_and_store_runtime_snapshots", produce)
    monkeypatch.setattr(module, "run_consumer_cycle",
        lambda **_: (_ for _ in ()).throw(RuntimeError("stop-after-producer")))
    result = coordinator.run(coordinator.request("MARKET_OPEN_INITIAL"))
    assert result["state"] == "FAILED"
    assert seen["inherited_cas_references"] == references
    assert seen["trading_session_identity"] == session
    assert seen["cas_primitive_path"] == cas_path

def test_lifecycle_passes_one_sink_to_feed_and_sink_receives_event():
    seen = {}
    class Feed:
        def start_depth_ws(self, tokens, **kwargs):
            seen["tokens"] = tokens
            seen["sink"] = kwargs["tick_sink"]
            kwargs["tick_sink"]({"instrument_token": 1, "last_price": 100.0,
                                  "timestamp_epoch": 10.0,
                                  "timestamp_authority": "EXCHANGE_TIMESTAMP"})
            return True
        def stop_depth_ws(self, **kwargs):
            return None
    from core.kite_read_only_observation_runtime import ObservationLifecycle
    received = []
    lifecycle = ObservationLifecycle(Feed())
    lifecycle.start([1], tick_sink=received.append)
    assert seen["tokens"] == [1]
    assert seen["sink"] is received.append or callable(seen["sink"])
    assert received[0]["last_price"] == 100.0
    lifecycle.request_stop()
