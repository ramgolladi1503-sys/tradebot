import importlib


def test_subscription_lifecycle_requires_post_request_tick_and_full_payload(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    ws._FEED_SESSION_ID = "session-test"
    ws._FEED_RECONNECT_GENERATION = 3
    ws._FEED_CONNECTION_START_EPOCH = 1000.0
    ws._reset_market_event_graph_generation_evidence()

    epochs = iter([10.0, 11.0, 12.0, 13.0, 14.0])
    monkeypatch.setattr(ws, "now_utc_epoch", lambda: next(epochs))
    ws._record_subscription_requested([101])
    ws._record_subscription_request_succeeded([101])
    ws._record_mode_request_succeeded([101])
    ws._LAST_MSG_TS_BY_TOKEN[101] = 10.5
    evidence = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": 101})

    lifecycle = evidence["token_lifecycle"]["101"]
    assert lifecycle["subscribe_call_succeeded_epoch"] == 11.0
    assert lifecycle["first_live_tick_epoch"] is None
    assert lifecycle["first_full_payload_epoch"] is None
    assert evidence["subscription_generation_id"] == evidence["subscription_evidence_id"]

    ws._FIRST_LIVE_TICK_EPOCH_BY_TOKEN[101] = 13.0
    ws._record_full_payload_observed(101)
    updated = ws.market_event_graph_subscription_evidence_for_tokens({"NIFTY": 101})

    assert updated["subscription_generation_id"] == evidence["subscription_generation_id"]
    assert updated["evidence_snapshot_sha256"] != evidence["evidence_snapshot_sha256"]
    assert updated["token_lifecycle"]["101"]["first_full_payload_epoch"] == 13.0


def test_already_running_start_does_not_rotate_generation_or_clear_evidence(monkeypatch):
    ws = importlib.import_module("core.kite_depth_ws")
    ws._FEED_SESSION_ID = "session-running"
    ws._FEED_RECONNECT_GENERATION = 5
    ws._FEED_CONNECTION_START_EPOCH = 1234.0
    ws._reset_market_event_graph_generation_evidence()
    ws._SUBSCRIPTION_REQUESTED_TOKENS.add(101)
    ws._SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN[101] = 10.0
    ws._KITE_TICKER = object()
    monkeypatch.setattr(ws.cfg, "DEPTH_WS_SINGLETON", True)
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **kwargs: None)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    try:
        assert ws.start_depth_ws([101], skip_lock=True, skip_guard=False) is True
    finally:
        ws._KITE_TICKER = None

    assert ws._FEED_RECONNECT_GENERATION == 5
    assert ws._FEED_CONNECTION_START_EPOCH == 1234.0
    assert ws._SUBSCRIPTION_REQUESTED_TOKENS == {101}
    assert ws._SUBSCRIPTION_REQUESTED_EPOCH_BY_TOKEN[101] == 10.0
