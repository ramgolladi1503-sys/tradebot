import re

with open("tests/test_feed_reconnect_safety.py", "r") as f:
    c = f.read()

c = c.replace("""def ticker_callbacks(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: {}, raising=False)
    import core.auth_health as auth_health
    monkeypatch.setattr(auth_health, "get_kite_auth_health", lambda force=False: {"ok": True, "user_id": "ABCD1234"}, raising=False)""",
"""def ticker_callbacks(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: {}, raising=False)
    import core.auth_health as auth_health
    monkeypatch.setattr(auth_health, "get_kite_auth_health", lambda force=False: {"ok": True, "user_id": "ABCD1234"}, raising=False)
    import core.kite_client as kite_client
    class DummyKite:
        def profile(self): return {"user_id": "ABCD1234"}
    monkeypatch.setattr(kite_client, "kite", DummyKite(), raising=False)""")

with open("tests/test_feed_reconnect_safety.py", "w") as f:
    f.write(c)
