import re

with open("tests/test_kite_auth_consistency.py", "r") as f:
    c = f.read()

c = c.replace("""def test_start_depth_ws_does_not_seed_ohlc(monkeypatch):
    import config.config as cfg""",
"""def test_start_depth_ws_does_not_seed_ohlc(monkeypatch):
    import config.config as cfg
    import core.orchestrator as orchestrator_mod
    monkeypatch.setattr(orchestrator_mod, "read_latest_runtime_snapshot", lambda: {})""")

with open("tests/test_kite_auth_consistency.py", "w") as f:
    f.write(c)

with open("tests/test_feed_reconnect_safety.py", "r") as f:
    c = f.read()

c = c.replace("""def ticker_callbacks(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)""",
"""def ticker_callbacks(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    import core.orchestrator as orchestrator_mod
    monkeypatch.setattr(orchestrator_mod, "read_latest_runtime_snapshot", lambda: {}, raising=False)""")

with open("tests/test_feed_reconnect_safety.py", "w") as f:
    f.write(c)
