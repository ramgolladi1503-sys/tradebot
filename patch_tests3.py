import re
with open("tests/test_feed_reconnect_safety.py", "r") as f:
    c = f.read()

c = c.replace("""def ticker_callbacks():
    with patch("core.kite_depth_ws.KiteTicker") as mock_ticker_cls:""",
"""def ticker_callbacks(monkeypatch):
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)
    with patch("core.kite_depth_ws.KiteTicker") as mock_ticker_cls:""")

with open("tests/test_feed_reconnect_safety.py", "w") as f:
    f.write(c)

with open("tests/test_kite_auth_consistency.py", "r") as f:
    c = f.read()

c = c.replace("""def test_profile_fail_blocks_persist_and_ticker_start(monkeypatch):""",
"""def test_profile_fail_blocks_persist_and_ticker_start(monkeypatch):
    import config.config as cfg
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)""")
c = c.replace("""def test_start_depth_ws_does_not_seed_ohlc(monkeypatch):""",
"""def test_start_depth_ws_does_not_seed_ohlc(monkeypatch):
    import config.config as cfg
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)""")
c = c.replace("""def test_profile_ok_persists_and_ticker_allowed(monkeypatch):""",
"""def test_profile_ok_persists_and_ticker_allowed(monkeypatch):
    import config.config as cfg
    monkeypatch.setattr(cfg, "KITE_API_KEY", "mock_key", raising=False)
    monkeypatch.setattr(cfg, "KITE_ACCESS_TOKEN", "mock_token", raising=False)""")

with open("tests/test_kite_auth_consistency.py", "w") as f:
    f.write(c)
