import re

with open("tests/test_feed_reconnect_safety.py", "r") as f:
    c = f.read()

c = c.replace("""def ticker_callbacks(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: {}, raising=False)""",
"""def ticker_callbacks(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: {}, raising=False)
    import core.auth_health as auth_health
    monkeypatch.setattr(auth_health, "get_kite_auth_health", lambda force=False: {"ok": True, "user_id": "ABCD1234"}, raising=False)""")

with open("tests/test_feed_reconnect_safety.py", "w") as f:
    f.write(c)

with open("tests/test_kite_auth_consistency.py", "r") as f:
    c = f.read()

c = c.replace("""def test_profile_ok_persists_and_ticker_allowed(monkeypatch):
    import config.config as cfg
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    mod = _load_generate_module()""",
"""def test_profile_ok_persists_and_ticker_allowed(monkeypatch):
    import config.config as cfg
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    import core.feed.runtime_store as runtime_store
    monkeypatch.setattr(runtime_store, "read_latest_runtime_snapshot", lambda: {}, raising=False)
    mod = _load_generate_module()""")

with open("tests/test_kite_auth_consistency.py", "w") as f:
    f.write(c)
