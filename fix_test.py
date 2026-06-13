import pytest
import sys

def test_debug():
    import core.kite_depth_ws as ws
    from _pytest.monkeypatch import MonkeyPatch
    import json
    
    mp = MonkeyPatch()
    mp.setattr(ws, "_log_ws", lambda *args, **kwargs: None)
    mp.setattr(ws, "_RECONNECT_BLOCKED_REASON", "", raising=False)
    mp.setattr(ws, "_STOP_REQUESTED", False, raising=False)
    mp.setattr(ws, "_WATCHDOG_STOP", None, raising=False)
    mp.setattr(ws, "_use_internal_reconnect", lambda: True, raising=False)
    mp.setattr(ws, "is_market_open_ist", lambda: True)
    
    # We will print inside our soft_resubscribe
    def mock_soft(reason):
        print("MOCK SOFT CALLED")
        return False
    mp.setattr(ws, "_soft_resubscribe_current", mock_soft, raising=False)

    mp.setattr(ws, "feed_breaker_tripped", lambda: False, raising=False)

    calls = {"schedule": 0}
    def mock_sched(**kwargs):
        print("MOCK SCHED CALLED")
        calls["schedule"] += 1
        return True
    mp.setattr(ws, "_schedule_restart_depth_ws", mock_sched)

    class _FakeTicker:
        def connect(self, threaded=True):
            self.on_error(self, 1006, "connection was closed uncleanly (peer dropped)")

    fake_ticker = _FakeTicker()
    mp.setattr(ws, "KiteTicker", object(), raising=False)
    mp.setattr(ws, "get_kite_ticker", lambda **kwargs: fake_ticker, raising=False)
    mp.setattr(ws, "get_kite_auth_health", lambda force=True: {"ok": True}, raising=False)
    
    mp.setattr(ws.cfg, "KITE_API_KEY", "kite_test_key", raising=False)
    mp.setattr(ws.cfg, "KITE_ACCESS_TOKEN", "token1234", raising=False)
    mp.setattr(ws.kite_client, "_active_api_key", "kite_test_key", raising=False)
    mp.setattr(ws.kite_client, "_active_access_token", "token1234", raising=False)
    ws.kite_client.ensure = lambda: type("_RestClient", (), {"profile": lambda self: {"user_id": "ABCD1234"}})()
    mp.setattr(ws, "_ensure_depth_ws_lock", lambda: True, raising=False)

    ws.start_depth_ws([101, 202], skip_lock=True, skip_guard=True)
    print("SCHEDULE CALLS:", calls["schedule"])
    mp.undo()

test_debug()
