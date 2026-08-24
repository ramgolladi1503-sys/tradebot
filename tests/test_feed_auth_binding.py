import core.kite_depth_ws as ws


def test_start_depth_ws_uses_canonical_auth_health_not_legacy_config_key(monkeypatch):
    monkeypatch.setattr(ws.cfg, "KITE_API_KEY", "", raising=False)
    monkeypatch.setattr(ws.cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(ws, "KiteTicker", object(), raising=False)
    monkeypatch.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True})
    monkeypatch.setattr(ws.kite_client, "ensure", lambda: object(), raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_api_key", "canonical-key", raising=False)
    monkeypatch.setattr(ws.kite_client, "_active_access_token", "canonical-token", raising=False)
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **kwargs: None)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    assert ws.start_depth_ws([], skip_lock=True, skip_guard=True) is False
    assert ws._LAST_RUNTIME_ERROR == "no_instrument_tokens"


def test_start_depth_ws_still_fails_closed_when_canonical_auth_health_fails(monkeypatch):
    monkeypatch.setattr(ws.cfg, "KITE_USE_DEPTH", True, raising=False)
    monkeypatch.setattr(ws, "KiteTicker", object(), raising=False)
    monkeypatch.setattr(
        ws,
        "get_kite_auth_health",
        lambda force=True: {"ok": False, "error": "missing_canonical_auth"},
    )
    monkeypatch.setattr(ws, "_persist_runtime_snapshot_row", lambda **kwargs: None)
    monkeypatch.setattr(ws, "_log_ws", lambda *args, **kwargs: None)

    assert ws.start_depth_ws([101], skip_lock=True, skip_guard=True) is False
    assert ws._RUNTIME_STATE == "AUTH_BLOCKED"
    assert ws._LAST_RUNTIME_ERROR == "missing_canonical_auth"
